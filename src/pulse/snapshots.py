"""Seal a committed observed state now; retained manifests contain no publisher content.

A caller cannot manufacture an earlier cutoff. A seal freezes the exact permitted
identifiers, receipt chronology, versions, health and availability witnesses. Replay
loads those immutable revisions only while their current rights and retention allow.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from pulse.availability import mark_available
from pulse.db import db_now, evidence_lock, transaction
from pulse.errors import PolicyBlocked
from pulse.models import (
    Artifact,
    Availability,
    HealthInterval,
    Observation,
    Occurrence,
    Outbox,
    Policy,
    Receipt,
    Revision,
    Snapshot,
    Source,
)
from pulse.objects import LocalObjectStore
from pulse.policy import require_policy

MANIFEST_VERSION = "observed-manifest-v1"
LIST_VERSION = "observed-list-v1"


def implementation_hash() -> str:
    digest = hashlib.sha256()
    for path in sorted(Path(__file__).parent.glob("*.py")):
        digest.update(path.name.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


HEALTHY_STATES = {"OK", "NO_CHANGE_VALID_CACHE"}


class SnapshotConflict(ValueError):
    """An existing logical seal cannot be reused for a different requested panel."""


def canonical_json(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def iso(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat() if value is not None else None


def policy_panel(source: Source, policy: Policy) -> dict[str, Any]:
    # Permission audit is kept separately from publisher payload fields.
    return {
        "source_id": source.id,
        "feed_id": source.feed_id,
        "policy_id": policy.id,
        "policy_version": policy.version,
        "publisher_id": policy.publisher_id,
        "owner_id": policy.owner_id,
        "scope": policy.scope,
        "effective_from": iso(policy.effective_from),
        "expires_at": iso(policy.expires_at),
        "approved_at": iso(policy.approved_at),
        "approved_by": policy.approved_by,
        "state": policy.state,
        "metadata_allowed": policy.metadata_allowed,
        "link_display_allowed": policy.link_display_allowed,
        "derived_allowed": policy.derived_allowed,
        "training_allowed": policy.training_allowed,
        "allowed_fields": sorted(policy.allowed_fields),
        "retention_seconds": policy.retention_seconds,
        "poll_seconds": policy.poll_seconds,
        "rollover_seconds": policy.rollover_seconds,
        "timestamp_quality": policy.timestamp_quality,
        "deletion_procedure": policy.deletion_procedure,
    }


def interval_record(interval: HealthInterval) -> dict[str, Any]:
    return {
        "id": interval.id,
        "source_id": interval.source_id,
        "fetch_id": interval.fetch_id,
        "state": interval.state,
        "reason": interval.reason,
        "started_at": iso(interval.started_at),
        "ended_at": iso(interval.ended_at),
        "recorded_at": iso(interval.recorded_at),
    }


def _display_link(value: Any, policy: Policy) -> bool:
    if not policy.link_display_allowed or not isinstance(value, str):
        return False
    # urlsplit silently removes some controls. Never display that malformed input.
    if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value):
        return False
    try:
        parts = urlsplit(value)
        if (
            parts.scheme != "https"
            or parts.hostname != policy.allowed_host
            or parts.username is not None
            or parts.password is not None
            or parts.port not in (None, 443)
        ):
            return False
        try:
            return ipaddress.ip_address(parts.hostname).is_global
        except ValueError:
            return True  # Merely displays an exact allowed host; never resolves/fetches it.
    except ValueError:
        return False


def _http_guid(value: str) -> bool:
    """Recognize HTTP identifiers without rewriting opaque publisher GUIDs."""
    try:
        if urlsplit(value).scheme.casefold() in {"http", "https"}:
            return True
    except ValueError:
        pass  # A malformed authority still must respect link-display restrictions.
    # Detect malformed HTTP scheme prefixes too, including whitespace/controls
    # that a URL parser may strip. This only classifies; stored identity is untouched.
    scheme, separator, _ = value.lstrip().partition(":")
    scheme = "".join(char for char in scheme if ord(char) > 32 and ord(char) != 127)
    return bool(separator) and scheme.casefold() in {"http", "https"}


def permitted_fields(revision: Revision, policy: Policy) -> dict[str, Any]:
    fields = {key: value for key, value in revision.fields.items() if key in policy.allowed_fields}
    if "url" in fields and not _display_link(fields["url"], policy):
        del fields["url"]
    if "guid" in fields and isinstance(fields["guid"], str):
        # A GUID sometimes embeds a publisher URL and must respect link rights too.
        if _http_guid(fields["guid"]) and not _display_link(fields["guid"], policy):
            del fields["guid"]
    return fields


@dataclass
class EvidenceView:
    as_of: datetime
    panel: list[dict[str, Any]]
    receipts: list[dict[str, Any]]
    observations: list[dict[str, Any]]
    health: list[dict[str, Any]]
    gaps: list[dict[str, Any]]
    queue_lag: dict[str, Any]
    evidence_status: str
    availability_high_watermark: int


def revalidate_evidence(session: Session, view: EvidenceView) -> EvidenceView:
    """Apply current DB-clock rights and retention again without repeating object hashes.

    Evidence writers/deletion share the caller's lock, but clock expiry can happen while
    that lock is held. Strip expired references and recompute first-seen only from the
    still-permitted receipt subset. The original selection cutoff remains unchanged.
    """
    policies: dict[str, Policy] = {}
    blocked_sources: set[str] = set()
    for panel_row in view.panel:
        try:
            policies[panel_row["source_id"]] = require_policy(
                session, panel_row["source_id"], panel_row["policy_id"]
            )
        except PolicyBlocked:
            blocked_sources.add(panel_row["source_id"])
    # This tick follows all final policy reads, so an earlier policy check cannot
    # allow expiry during the rest of the permission sweep.
    current = db_now(session)
    blocked_sources.update(
        source_id for source_id, policy in policies.items() if policy.expires_at <= current
    )
    view.panel = [row for row in view.panel if row["source_id"] not in blocked_sources]
    retained_receipts = []
    expired_sources: set[str] = set()
    for row in view.receipts:
        policy = policies.get(row["source_id"])
        if row["source_id"] in blocked_sources or policy is None:
            continue
        received_at = datetime.fromisoformat(row["received_at"])
        artifact_expires_at = datetime.fromisoformat(row["artifact_expires_at"])
        if (
            artifact_expires_at <= current
            or received_at + timedelta(seconds=policy.retention_seconds) <= current
        ):
            expired_sources.add(row["source_id"])
            continue
        retained_receipts.append(row)
    view.receipts = retained_receipts
    retained_ids = {row["id"] for row in retained_receipts}
    view.observations = [row for row in view.observations if row["receipt_id"] in retained_ids]
    first_seen: dict[str, str] = {}
    for row in view.observations:
        occurrence_id = row["occurrence_id"]
        first_seen[occurrence_id] = min(
            first_seen.get(occurrence_id, row["received_at"]), row["received_at"]
        )
    for row in view.observations:
        row["first_seen_at"] = first_seen[row["occurrence_id"]]
    for source_id in sorted(blocked_sources | expired_sources):
        reason = (
            "RIGHTS_EXPIRED_DURING_READ"
            if source_id in blocked_sources
            else "RETENTION_EXPIRED_DURING_READ"
        )
        state = "RIGHTS_BLOCKED" if source_id in blocked_sources else "DEGRADED"
        for row in view.health:
            if row["source_id"] == source_id:
                row["state"] = state
                if reason not in row["reasons"]:
                    row["reasons"].append(reason)
                if source_id in blocked_sources:
                    row["last_successful_checkpoint_at"] = None
                    row["checkpoint_age_seconds"] = None
        if not any(row["source_id"] == source_id and row["reason"] == reason for row in view.gaps):
            view.gaps.append(
                {
                    "source_id": source_id,
                    "state": state,
                    "reason": reason,
                    "started_at": iso(view.as_of),
                    "ended_at": None,
                }
            )
    if not view.panel or not view.receipts:
        view.evidence_status = "EVIDENCE_UNAVAILABLE"
    elif view.gaps or any(row["state"] != "OK" for row in view.health):
        view.evidence_status = "PARTIALLY_DEGRADED"
    elif view.observations:
        view.evidence_status = "AVAILABLE"
    else:
        view.evidence_status = "HEALTHY_EMPTY"
    return view


def read_evidence(
    session: Session,
    store: LocalObjectStore,
    *,
    source_ids: list[str] | None = None,
    now: datetime | None = None,
) -> EvidenceView:
    """Read persisted, witnessed evidence after current-policy and object checks.

    Callers hold evidence_lock to serialize against deletion and evidence commits.
    A successful fetch with unparsed/missing representation is never a healthy zero.
    """
    now = now or db_now(session)
    sources = list(session.scalars(select(Source).order_by(Source.id)))
    if source_ids is not None:
        selected = set(source_ids)
        if selected - {source.id for source in sources}:
            raise PolicyBlocked("UNKNOWN_SOURCE")
        sources = [source for source in sources if source.id in selected]
    policies: dict[str, Policy] = {}
    policy: Policy | None
    panel: list[dict[str, Any]] = []
    health: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    for source in sources:
        try:
            policy = require_policy(session, source.id)
            policies[source.id] = policy
            panel.append(policy_panel(source, policy))
        except PolicyBlocked:
            # No publisher fields or policy details are exposed for blocked sources.
            gaps.append(
                {
                    "source_id": source.id,
                    "state": "RIGHTS_BLOCKED",
                    "reason": "CURRENT_PERMISSION_UNAVAILABLE",
                    "started_at": iso(now),
                    "ended_at": None,
                }
            )
    selected_ids = [source.id for source in sources]
    intervals = list(
        session.scalars(
            select(HealthInterval)
            .where(HealthInterval.source_id.in_(selected_ids), HealthInterval.recorded_at <= now)
            .order_by(HealthInterval.started_at, HealthInterval.id)
        )
    )
    gaps.extend(
        interval_record(interval) for interval in intervals if interval.state not in HEALTHY_STATES
    )
    witnesses = list(
        session.scalars(select(Availability).where(Availability.postcommit_observed_at <= now))
    )
    receipt_witness = {row.entity_id: row for row in witnesses if row.kind == "receipt"}
    parsed_witness = {row.entity_id: row for row in witnesses if row.kind == "parsed_receipt"}
    receipt_query = select(Receipt, Artifact).join(Artifact, Receipt.artifact_key == Artifact.key)
    receipt_rows = list(
        session.execute(
            receipt_query.where(
                Receipt.source_id.in_(selected_ids),
                Receipt.received_at <= now,
                Receipt.recorded_at <= now,
            ).order_by(Receipt.received_at, Receipt.id)
        )
    )
    usable: dict[str, tuple[Receipt, Artifact, Policy]] = {}
    receipt_records: list[dict[str, Any]] = []
    latest: dict[str, Receipt] = {}
    missing: set[str] = set()
    pending: set[str] = set()
    retention_expired_during_read: set[str] = set()
    for receipt, artifact in receipt_rows:
        latest[receipt.source_id] = receipt
        policy = policies.get(receipt.source_id)
        if policy is None or receipt.policy_id != policy.id:
            continue
        if (
            artifact.expires_at <= now
            or receipt.received_at + timedelta(seconds=policy.retention_seconds) <= now
        ):
            # Routine legal expiry excludes content, rather than inventing a historical outage.
            continue
        if artifact.policy_id != policy.id or not store.verify(artifact.key, artifact.sha256):
            missing.add(receipt.source_id)
            continue
        # A checksum read may take longer than the remaining authorization/retention.
        try:
            policy = require_policy(session, receipt.source_id, receipt.policy_id)
        except PolicyBlocked:
            policies.pop(receipt.source_id, None)
            continue
        verified_at = db_now(session)
        if (
            artifact.expires_at <= verified_at
            or receipt.received_at + timedelta(seconds=policy.retention_seconds) <= verified_at
        ):
            retention_expired_during_read.add(receipt.source_id)
            continue
        if receipt.id not in receipt_witness or receipt.id not in parsed_witness:
            pending.add(receipt.source_id)
            continue
        usable[receipt.id] = (receipt, artifact, policy)
        receipt_records.append(
            {
                "id": receipt.id,
                "fetch_id": receipt.fetch_id,
                "source_id": receipt.source_id,
                "policy_id": receipt.policy_id,
                "artifact_key": artifact.key,
                "artifact_sha256": artifact.sha256,
                "artifact_size": artifact.size,
                "artifact_expires_at": iso(artifact.expires_at),
                "http_status": receipt.http_status,
                "received_at": iso(receipt.received_at),
                "recorded_at": iso(receipt.recorded_at),
                "schema_version": receipt.schema_version,
                "collection_parser_version": receipt.collection_parser_version,
                "clock_quality": receipt.clock_quality,
                "receipt_availability_id": receipt_witness[receipt.id].id,
                "receipt_available_at": iso(receipt_witness[receipt.id].postcommit_observed_at),
                "processing_availability_id": parsed_witness[receipt.id].id,
                "processing_available_at": iso(parsed_witness[receipt.id].postcommit_observed_at),
            }
        )
    observations: list[dict[str, Any]] = []
    first_seen: dict[str, datetime] = {}
    rows = list(
        session.execute(
            select(Observation, Revision, Occurrence)
            .join(Revision, Observation.revision_id == Revision.id)
            .join(Occurrence, Observation.occurrence_id == Occurrence.id)
            .where(
                Observation.receipt_id.in_(list(usable)),
                Observation.recorded_at <= now,
                Revision.recorded_at <= now,
            )
            .order_by(
                Observation.received_at, Observation.receipt_id, Observation.ordinal, Observation.id
            )
        )
    )
    for observation, revision, occurrence in rows:
        receipt, artifact, policy = usable[observation.receipt_id]
        first_seen[occurrence.id] = min(
            first_seen.get(occurrence.id, receipt.received_at), receipt.received_at
        )
        observations.append(
            {
                "id": observation.id,
                "source_id": observation.source_id,
                "feed_id": observation.feed_id,
                "receipt_id": receipt.id,
                "fetch_id": receipt.fetch_id,
                "policy_id": receipt.policy_id,
                "publisher_id": occurrence.publisher_id,
                "owner_id": policy.owner_id,
                "occurrence_id": occurrence.id,
                "identity_version": occurrence.identity_version,
                "identity_confidence": occurrence.identity_confidence,
                "revision_id": revision.id,
                "fingerprint": revision.fingerprint,
                "ordinal": observation.ordinal,
                "fields": permitted_fields(revision, policy),
                "published_at": iso(revision.published_at)
                if "published_at" in policy.allowed_fields
                else None,
                "published_precision": revision.published_precision
                if "published_at" in policy.allowed_fields
                else "withheld",
                "received_at": iso(receipt.received_at),
                "receipt_recorded_at": iso(receipt.recorded_at),
                "recorded_at": iso(observation.recorded_at),
                "revision_recorded_at": iso(revision.recorded_at),
                "processing_available_at": iso(parsed_witness[receipt.id].postcommit_observed_at),
                "artifact_key": artifact.key,
                "artifact_sha256": artifact.sha256,
                "parser_version": revision.parser_version,
                "collection_parser_version": receipt.collection_parser_version,
                "normalization_version": revision.normalization_version,
                "schema_version": revision.schema_version,
                "clock_quality": receipt.clock_quality,
                "timestamp_quality": policy.timestamp_quality,
            }
        )
    for record in observations:
        record["first_seen_at"] = iso(first_seen[record["occurrence_id"]])
    queue = list(
        session.scalars(
            select(Outbox)
            .join(Receipt)
            .where(Receipt.source_id.in_(selected_ids), Outbox.state != "DONE")
        )
    )
    oldest_pending = min((row.due_at for row in queue), default=None)
    queue_lag = {
        "pending_count": len(queue),
        "oldest_due_at": iso(oldest_pending),
        "oldest_age_seconds": max(0.0, (now - oldest_pending).total_seconds())
        if oldest_pending is not None
        else None,
    }
    for source in sources:
        policy = policies.get(source.id)
        checkpoint = latest.get(source.id)
        age = max(0.0, (now - checkpoint.received_at).total_seconds()) if checkpoint else None
        reasons = []
        if policy is None:
            reasons.append("RIGHTS_BLOCKED")
        elif checkpoint is None or checkpoint.policy_id != policy.id:
            reasons.append("NO_SUCCESSFUL_CHECKPOINT")
        elif age is not None and age > max(60, 3 * policy.poll_seconds):
            reasons.append("STALE_CHECKPOINT")
        if checkpoint is not None and policy is not None and checkpoint.id not in usable:
            reasons.append("LATEST_CHECKPOINT_NOT_OPERATIONALLY_USABLE")
        if source.id in missing:
            reasons.append("MISSING_ARTIFACT")
        if source.id in retention_expired_during_read:
            reasons.append("RETENTION_EXPIRED_DURING_READ")
        if source.id in pending:
            reasons.append("PARSER_AVAILABILITY_PENDING")
        if any(
            row.source_id == source.id and row.ended_at is None and row.state not in HEALTHY_STATES
            for row in intervals
        ):
            reasons.append("OPEN_OBSERVATION_GAP")
        if any(
            row.receipt_id in {rec.id for rec, _ in receipt_rows if rec.source_id == source.id}
            for row in queue
        ):
            reasons.append("DOWNSTREAM_QUEUE_LAG")
        state = (
            "OK"
            if not reasons
            else (
                "RIGHTS_BLOCKED"
                if policy is None
                else "UNAVAILABLE"
                if checkpoint is None
                else "DEGRADED"
            )
        )
        health.append(
            {
                "source_id": source.id,
                "state": state,
                "reasons": reasons,
                "last_successful_checkpoint_at": iso(checkpoint.received_at)
                if checkpoint is not None and policy is not None
                else None,
                "checkpoint_age_seconds": age if policy is not None else None,
                "rollover_risk": bool(policy and age is not None and age > policy.rollover_seconds),
            }
        )
        for reason in reasons:
            if reason != "OPEN_OBSERVATION_GAP" and reason != "RIGHTS_BLOCKED":
                gaps.append(
                    {
                        "source_id": source.id,
                        "state": state,
                        "reason": reason,
                        "started_at": iso(checkpoint.received_at if checkpoint else now),
                        "ended_at": None,
                    }
                )
    has_checkpoint = bool(receipt_records)
    degraded = bool(gaps) or any(row["state"] != "OK" for row in health)
    if not policies or not has_checkpoint:
        status = "EVIDENCE_UNAVAILABLE"
    elif degraded:
        status = "PARTIALLY_DEGRADED"
    elif observations:
        status = "AVAILABLE"
    else:
        # Metadata observations, not resolved editorial candidates, are the M1 contract.
        status = "HEALTHY_EMPTY"
    return revalidate_evidence(
        session,
        EvidenceView(
            now,
            panel,
            receipt_records,
            observations,
            health,
            gaps,
            queue_lag,
            status,
            max((row.id for row in witnesses), default=0),
        ),
    )


def current_observations(view: EvidenceView) -> list[dict[str, Any]]:
    """Latest publisher occurrence is chosen by received chronology, never parse time."""
    latest: dict[str, dict[str, Any]] = {}
    for record in view.observations:
        key = record["occurrence_id"]
        order = (record["received_at"], record["receipt_id"], record["ordinal"], record["id"])
        previous = latest.get(key)
        if previous is None or order > (
            previous["received_at"],
            previous["receipt_id"],
            previous["ordinal"],
            previous["id"],
        ):
            latest[key] = record
    return sorted(latest.values(), key=lambda row: (row["received_at"], row["id"]), reverse=True)


def seal_snapshot(
    engine: Engine, store: LocalObjectStore, run_id: str, *, source_ids: list[str] | None = None
) -> Snapshot:
    if not run_id.strip() or len(run_id) > 100:
        raise ValueError("run_id must contain between 1 and 100 characters")
    requested_sources = sorted(set(source_ids)) if source_ids is not None else None
    with transaction(engine) as session:
        evidence_lock(session)
        existing = session.scalar(select(Snapshot).where(Snapshot.run_id == run_id))
        if existing is not None:
            existing_manifest = json.loads(existing.manifest)
            if existing_manifest["request_source_ids"] != requested_sources:
                raise SnapshotConflict("run_id already seals a different source selection")
            snapshot = existing
        else:
            now = db_now(session)
            view = read_evidence(session, store, source_ids=requested_sources, now=now)
            panel_hash = hashlib.sha256(canonical_json(view.panel).encode()).hexdigest()
            sealed_panel = {(row["source_id"], row["policy_id"]) for row in view.panel}
            sealed_receipts = {row["id"] for row in view.receipts}
            observations = [
                {
                    key: value
                    for key, value in record.items()
                    if key not in {"fields", "published_at", "published_precision"}
                }
                for record in view.observations
            ]
            manifest = canonical_json(
                {
                    "manifest_version": MANIFEST_VERSION,
                    "run_id": run_id,
                    "kind": "OBSERVED_ONLY",
                    "candidate_policy_version": LIST_VERSION,
                    "request_source_ids": requested_sources,
                    "cutoff_at": iso(now),
                    "built_at": iso(now),
                    "panel_hash": panel_hash,
                    "panel": view.panel,
                    "visibility_witness": str(session.scalar(text("SELECT pg_current_snapshot()"))),
                    "availability_high_watermark": view.availability_high_watermark,
                    "receipts": view.receipts,
                    "observations": observations,
                    "current_observation_ids": [row["id"] for row in current_observations(view)],
                    "source_health": view.health,
                    "source_gaps": view.gaps,
                    "queue_lag": view.queue_lag,
                    "evidence_status": view.evidence_status,
                    "versions": {
                        "manifest": MANIFEST_VERSION,
                        "observed_list": LIST_VERSION,
                        "implementation": "pulse-ingestion-0.1.0",
                        "implementation_sha256": implementation_hash(),
                    },
                    "validity_at_sealing": "PERMITTED_REFERENCES_ONLY",
                    "replay_contract": "immutable_references_current_rights_required",
                }
            )
            # Manifest assembly and implementation hashing can also cross a deadline.
            # Abort rather than reseal with stale permissions or recursively rebuild.
            revalidate_evidence(session, view)
            if sealed_panel != {(row["source_id"], row["policy_id"]) for row in view.panel} or (
                sealed_receipts != {row["id"] for row in view.receipts}
            ):
                raise PolicyBlocked("RIGHTS_OR_RETENTION_EXPIRED_DURING_SNAPSHOT_BUILD")
            snapshot = Snapshot(
                run_id=run_id,
                panel_hash=panel_hash,
                cutoff_at=now,
                candidate_policy_version=LIST_VERSION,
                kind="OBSERVED_ONLY",
                manifest=manifest,
                sha256=hashlib.sha256(manifest.encode()).hexdigest(),
            )
            session.add(snapshot)
            session.flush()
        snapshot_id = snapshot.id
        session.expunge(snapshot)
    # This witness is intentionally outside the manifest and follows its DB commit.
    mark_available(engine, "snapshot", snapshot_id)
    return snapshot
