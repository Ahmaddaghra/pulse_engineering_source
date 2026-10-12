"""Observed-only read API with a separate auditor capability for immutable seals."""

from __future__ import annotations

import hashlib
import json
import secrets
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine, select, text
from sqlalchemy.exc import SQLAlchemyError

from pulse.config import Settings
from pulse.db import engine_for, evidence_lock, transaction
from pulse.errors import PolicyBlocked
from pulse.models import Availability, Snapshot, SnapshotInvalidation, Source
from pulse.objects import LocalObjectStore
from pulse.policy import require_policy
from pulse.snapshots import (
    EvidenceView,
    SnapshotConflict,
    current_observations,
    iso,
    read_evidence,
    revalidate_evidence,
    seal_snapshot,
)

EvidenceStatus = Literal["AVAILABLE", "HEALTHY_EMPTY", "PARTIALLY_DEGRADED", "EVIDENCE_UNAVAILABLE"]


class HealthResponse(BaseModel):
    status: Literal["alive"] = "alive"


class ReadyResponse(BaseModel):
    status: Literal["ready"] = "ready"
    database: Literal["reachable"] = "reachable"
    migration: str


class ProvenanceRecord(BaseModel):
    id: str
    source_id: str
    feed_id: str
    receipt_id: str
    fetch_id: str
    policy_id: str
    publisher_id: str
    owner_id: str
    occurrence_id: str
    identity_version: str
    identity_confidence: str
    revision_id: str
    fingerprint: str
    ordinal: int
    fields: dict[str, Any]
    published_at: datetime | None
    published_precision: str
    received_at: datetime
    receipt_recorded_at: datetime
    recorded_at: datetime
    revision_recorded_at: datetime
    processing_available_at: datetime
    first_seen_at: datetime
    artifact_key: str
    artifact_sha256: str
    collection_parser_version: str
    parser_version: str
    normalization_version: str
    schema_version: str
    clock_quality: str
    timestamp_quality: str


class ObservationsResponse(BaseModel):
    mode: Literal["OBSERVED_ONLY"] = "OBSERVED_ONLY"
    evidence_status: EvidenceStatus
    as_of: datetime
    coverage_scope: Literal["authorized_enrolled_publishers_only"] = (
        "authorized_enrolled_publishers_only"
    )
    forecasts_available: Literal[False] = False
    records: list[ProvenanceRecord]
    offset: int
    limit: int
    total: int
    source_health: list[dict[str, Any]]
    source_gaps: list[dict[str, Any]]
    queue_lag: dict[str, Any]
    reason: str


class SourcesResponse(BaseModel):
    as_of: datetime
    sources: list[dict[str, Any]]
    offset: int
    limit: int
    total: int
    source_health: list[dict[str, Any]]
    source_gaps: list[dict[str, Any]]


class SourceHealthResponse(BaseModel):
    as_of: datetime
    source_health: list[dict[str, Any]]
    source_gaps: list[dict[str, Any]]
    queue_lag: dict[str, Any]


class SealRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str = Field(min_length=1, max_length=100, pattern=r"\S")
    source_ids: list[str] | None = Field(default=None, min_length=1, max_length=100)


class SnapshotResponse(BaseModel):
    id: str
    run_id: str
    kind: Literal["OBSERVED_ONLY"] = "OBSERVED_ONLY"
    cutoff_at: datetime
    panel_hash: str
    sha256: str
    manifest: str
    validity: Literal["PERMITTED", "REPLAY_UNAVAILABLE"]
    invalidations: list[dict[str, Any]]
    replay_unavailable_reasons: list[str]
    postcommit_observed_at: datetime | None
    payload: list[ProvenanceRecord] | None


def _auth(settings: Settings, scope: Literal["api", "audit"]) -> Callable[..., None]:
    bearer = HTTPBearer(
        auto_error=False, scheme_name="ObservedReader" if scope == "api" else "EvidenceAuditor"
    )
    credential_dependency = Depends(bearer)

    def authorize(credentials: HTTPAuthorizationCredentials | None = credential_dependency) -> None:
        expected = settings.api_token if scope == "api" else settings.audit_token
        # Missing or overlapping credentials cannot accidentally grant an audit capability.
        if not expected or (settings.api_token and settings.api_token == settings.audit_token):
            raise HTTPException(503, "Access token configuration unavailable")
        supplied = credentials.credentials if credentials is not None else ""
        if not supplied or not secrets.compare_digest(supplied.encode(), expected.encode()):
            raise HTTPException(
                401, "Bearer token required", headers={"WWW-Authenticate": "Bearer"}
            )

    return authorize


def _observed_response(
    view: EvidenceView, records: list[dict[str, Any]], offset: int, limit: int
) -> ObservationsResponse:
    reasons = {
        "AVAILABLE": "Persisted permitted observations available",
        "HEALTHY_EMPTY": "Healthy permitted parsed checkpoint contains no observed items",
        "PARTIALLY_DEGRADED": "Permitted evidence available with explicit gaps",
        "EVIDENCE_UNAVAILABLE": "No currently permitted recoverable parsed checkpoint",
    }
    return ObservationsResponse(
        evidence_status=view.evidence_status,  # type: ignore[arg-type]
        as_of=view.as_of,
        records=[ProvenanceRecord.model_validate(row) for row in records[offset : offset + limit]],
        offset=offset,
        limit=limit,
        total=len(records),
        source_health=view.health,
        source_gaps=view.gaps,
        queue_lag=view.queue_lag,
        reason=reasons[view.evidence_status],
    )


def _snapshot_response(
    engine: Engine, store: LocalObjectStore, snapshot_id: str
) -> SnapshotResponse:
    with transaction(engine) as session:
        evidence_lock(session)
        snapshot = session.get(Snapshot, snapshot_id)
        if snapshot is None:
            raise HTTPException(404, "Snapshot not found")
        invalidations = list(
            session.scalars(
                select(SnapshotInvalidation)
                .where(SnapshotInvalidation.snapshot_id == snapshot_id)
                .order_by(SnapshotInvalidation.recorded_at, SnapshotInvalidation.id)
            )
        )
        reasons: list[str] = []
        manifest = json.loads(snapshot.manifest)
        if hashlib.sha256(snapshot.manifest.encode()).hexdigest() != snapshot.sha256:
            reasons.append("MANIFEST_HASH_MISMATCH")
        if invalidations:
            reasons.append("APPEND_ONLY_INVALIDATION_PRESENT")
        view = read_evidence(session, store)
        panel_ids = {row["source_id"]: row["policy_id"] for row in view.panel}
        if any(panel_ids.get(row["source_id"]) != row["policy_id"] for row in manifest["panel"]):
            reasons.append("CURRENT_RIGHTS_UNAVAILABLE_OR_CHANGED")
        usable_receipts = {row["id"]: row for row in view.receipts}
        if any(
            row["id"] not in usable_receipts
            or usable_receipts[row["id"]]["artifact_sha256"] != row["artifact_sha256"]
            for row in manifest["receipts"]
        ):
            reasons.append("RECEIPT_ARTIFACT_EXPIRED_MISSING_OR_UNPERMITTED")
        by_id = {row["id"]: row for row in view.observations}
        for row in manifest["observations"]:
            if row["id"] not in by_id or by_id[row["id"]]["revision_id"] != row["revision_id"]:
                reasons.append("IMMUTABLE_REVISION_UNAVAILABLE")
                break
        witness = session.scalar(
            select(Availability).where(
                Availability.kind == "snapshot", Availability.entity_id == snapshot.id
            )
        )
        if witness is None:
            reasons.append("SNAPSHOT_POSTCOMMIT_WITNESS_PENDING")
        payload = None
        if not reasons:
            frozen_by_id = {row["id"]: row for row in manifest["observations"]}
            replay = []
            for observation_id in manifest["current_observation_ids"]:
                row = dict(by_id[observation_id])
                # Later arrivals may restate current first-seen; frozen replay must retain its seal.
                row["first_seen_at"] = frozen_by_id[observation_id]["first_seen_at"]
                replay.append(ProvenanceRecord.model_validate(row))
            payload = replay
        # Payload assembly itself may be slow. Recheck its exact frozen references
        # at a fresh DB-clock tick without rehashing the objects a second time.
        revalidate_evidence(session, view)
        final_panel = {row["source_id"]: row["policy_id"] for row in view.panel}
        final_receipts = {row["id"] for row in view.receipts}
        if any(
            final_panel.get(row["source_id"]) != row["policy_id"] for row in manifest["panel"]
        ) or any(row["id"] not in final_receipts for row in manifest["receipts"]):
            payload = None
            if "RIGHTS_OR_RETENTION_EXPIRED_DURING_REPLAY" not in reasons:
                reasons.append("RIGHTS_OR_RETENTION_EXPIRED_DURING_REPLAY")
        return SnapshotResponse(
            id=snapshot.id,
            run_id=snapshot.run_id,
            cutoff_at=snapshot.cutoff_at,
            panel_hash=snapshot.panel_hash,
            sha256=snapshot.sha256,
            manifest=snapshot.manifest,
            validity="REPLAY_UNAVAILABLE" if reasons else "PERMITTED",
            payload=payload,
            invalidations=[
                {
                    "id": row.id,
                    "reason": row.reason,
                    "reference_id": row.reference_id,
                    "recorded_at": iso(row.recorded_at),
                }
                for row in invalidations
            ],
            replay_unavailable_reasons=reasons,
            postcommit_observed_at=witness.postcommit_observed_at if witness else None,
        )


def _migration_heads() -> set[str]:
    repository = Path(__file__).resolve().parents[2]
    config = Config(str(repository / "alembic.ini"))
    config.set_main_option("script_location", str(repository / "migrations"))
    return set(ScriptDirectory.from_config(config).get_heads())


def create_app(settings: Settings, engine: Engine | None = None) -> FastAPI:
    database = engine or engine_for(settings.database_url)
    store = LocalObjectStore(settings.object_root)
    app = FastAPI(
        title="PULSE observed evidence API",
        version="0.1.0",
        description="Persisted metadata observations with rights, chronology and gaps. "
        "No event interpretation or forecasting capabilities.",
    )
    app.state.engine = database
    app.state.store = store
    read_access = Depends(_auth(settings, "api"))
    audit_access = Depends(_auth(settings, "audit"))

    @app.exception_handler(SQLAlchemyError)
    async def database_unavailable(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": "Evidence database unavailable"})

    @app.exception_handler(PolicyBlocked)
    async def permission_expired(request: Request, exc: PolicyBlocked) -> JSONResponse:
        return JSONResponse(
            status_code=503, content={"detail": "Current evidence permission unavailable"}
        )

    @app.get("/health", response_model=HealthResponse, tags=["health"])
    def health() -> HealthResponse:
        return HealthResponse()

    @app.get("/ready", response_model=ReadyResponse, dependencies=[read_access], tags=["health"])
    @app.get(
        "/v1/readiness", response_model=ReadyResponse, dependencies=[read_access], tags=["health"]
    )
    def readiness() -> ReadyResponse:
        try:
            expected = _migration_heads()
            with transaction(database) as session:
                session.execute(text("SELECT 1"))
                current = set(session.scalars(text("SELECT version_num FROM alembic_version")))
                if not expected or current != expected:
                    raise HTTPException(503, "Database migrations incomplete")
                # A reachable DB with missing application tables is not ready.
                session.scalar(select(Source.id).limit(1))
            return ReadyResponse(migration=",".join(sorted(current)))
        except (SQLAlchemyError, OSError, ValueError) as exc:
            raise HTTPException(503, "Database or migration metadata unavailable") from exc

    @app.get(
        "/v1/sources", response_model=SourcesResponse, dependencies=[read_access], tags=["sources"]
    )
    def sources(
        offset: Annotated[int, Query(ge=0, le=100000)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ) -> SourcesResponse:
        with transaction(database) as session:
            evidence_lock(session)
            view = read_evidence(session, store)
            records = []
            for row in view.panel:
                source = session.get(Source, row["source_id"])
                assert source is not None
                policy = require_policy(session, source.id, row["policy_id"])
                records.append(
                    {
                        **row,
                        "endpoint": policy.endpoint,
                        "allowed_host": policy.allowed_host,
                        "attribution": policy.attribution,
                    }
                )
            return SourcesResponse(
                as_of=view.as_of,
                sources=records[offset : offset + limit],
                offset=offset,
                limit=limit,
                total=len(records),
                source_health=view.health,
                source_gaps=view.gaps,
            )

    @app.get(
        "/v1/source-health",
        response_model=SourceHealthResponse,
        dependencies=[read_access],
        tags=["sources"],
    )
    def source_health() -> SourceHealthResponse:
        with transaction(database) as session:
            evidence_lock(session)
            view = read_evidence(session, store)
            return SourceHealthResponse(
                as_of=view.as_of,
                source_health=view.health,
                source_gaps=view.gaps,
                queue_lag=view.queue_lag,
            )

    @app.get(
        "/v1/sources/{source_id}/health",
        response_model=SourceHealthResponse,
        dependencies=[read_access],
        tags=["sources"],
    )
    def source_detail(source_id: str) -> SourceHealthResponse:
        with transaction(database) as session:
            evidence_lock(session)
            if session.get(Source, source_id) is None:
                raise HTTPException(404, "Source not found")
            view = read_evidence(session, store, source_ids=[source_id])
            return SourceHealthResponse(
                as_of=view.as_of,
                source_health=view.health,
                source_gaps=view.gaps,
                queue_lag=view.queue_lag,
            )

    def records(
        current: bool, source_id: str | None, offset: int, limit: int
    ) -> ObservationsResponse:
        with transaction(database) as session:
            evidence_lock(session)
            if source_id is not None and session.get(Source, source_id) is None:
                raise HTTPException(404, "Source not found")
            view = read_evidence(
                session, store, source_ids=[source_id] if source_id is not None else None
            )
            rows = current_observations(view) if current else list(reversed(view.observations))
            return _observed_response(view, rows, offset, limit)

    @app.get(
        "/v1/observations",
        response_model=ObservationsResponse,
        dependencies=[read_access],
        tags=["evidence"],
    )
    def observations(
        source_id: Annotated[str | None, Query(max_length=80)] = None,
        offset: Annotated[int, Query(ge=0, le=100000)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ) -> ObservationsResponse:
        return records(True, source_id, offset, limit)

    @app.get(
        "/v1/articles",
        response_model=ObservationsResponse,
        dependencies=[read_access],
        tags=["evidence"],
    )
    def articles(
        source_id: Annotated[str | None, Query(max_length=80)] = None,
        offset: Annotated[int, Query(ge=0, le=100000)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ) -> ObservationsResponse:
        # Every immutable observation is returned; revision reuse retains each receipt provenance.
        return records(False, source_id, offset, limit)

    @app.post(
        "/v1/snapshots",
        response_model=SnapshotResponse,
        dependencies=[audit_access],
        tags=["audit"],
    )
    def seal(request: SealRequest) -> SnapshotResponse:
        try:
            snapshot = seal_snapshot(database, store, request.run_id, source_ids=request.source_ids)
            return _snapshot_response(database, store, snapshot.id)
        except SnapshotConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except (PolicyBlocked, ValueError) as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get(
        "/v1/snapshots/{snapshot_id}/manifest",
        response_model=SnapshotResponse,
        dependencies=[audit_access],
        tags=["audit"],
    )
    @app.get(
        "/v1/snapshots/{snapshot_id}",
        response_model=SnapshotResponse,
        dependencies=[audit_access],
        tags=["audit"],
    )
    def snapshot(snapshot_id: str) -> SnapshotResponse:
        return _snapshot_response(database, store, snapshot_id)

    return app
