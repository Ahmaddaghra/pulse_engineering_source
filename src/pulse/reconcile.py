"""Compensate object/DB boundaries and erase disallowed content with audit traces."""

import json
from typing import Any

from sqlalchemy import Engine, delete, select, text
from sqlalchemy.orm import Session

from pulse.availability import mark_available
from pulse.db import db_now, evidence_lock, transaction
from pulse.models import (
    Artifact,
    Attempt,
    Audit,
    Availability,
    Consumption,
    HealthInterval,
    Observation,
    Outbox,
    Policy,
    Receipt,
    Revision,
    Snapshot,
    SnapshotInvalidation,
    Source,
)
from pulse.objects import LocalObjectStore


def _audit_once(session: Session, code: str, reference: str, source_id: str | None) -> bool:
    if session.scalar(select(Audit).where(Audit.code == code, Audit.reference_id == reference)):
        return False
    session.add(
        Audit(code=code, reference_id=reference, source_id=source_id, recorded_at=db_now(session))
    )
    return True


def _invalidate(session: Session, reference: str, reason: str) -> None:
    for snapshot in session.scalars(select(Snapshot)):
        # Manifests contain exact IDs/keys. Match serialized scalar values, not substrings.
        def contains(value: Any) -> bool:
            if isinstance(value, dict):
                return any(contains(item) for item in value.values())
            if isinstance(value, list):
                return any(contains(item) for item in value)
            return bool(value == reference)

        if contains(json.loads(snapshot.manifest)) and not session.scalar(
            select(SnapshotInvalidation).where(
                SnapshotInvalidation.snapshot_id == snapshot.id,
                SnapshotInvalidation.reference_id == reference,
                SnapshotInvalidation.reason == reason,
            )
        ):
            session.add(
                SnapshotInvalidation(
                    snapshot_id=snapshot.id,
                    reason=reason,
                    reference_id=reference,
                    recorded_at=db_now(session),
                )
            )


def reconcile(engine: Engine, store: LocalObjectStore) -> dict[str, int]:
    result = {
        "orphans_deleted": 0,
        "missing_artifacts": 0,
        "content_erased": 0,
        "expired_attempts": 0,
        "witnesses_recovered": 0,
    }
    to_witness: list[tuple[str, str]] = []
    with transaction(engine) as session:
        evidence_lock(session)
        now = db_now(session)
        artifacts = {item.key: item for item in session.scalars(select(Artifact))}
        for key in store.keys():
            if key in artifacts:
                continue
            policy_id, fetch_component, _ = key.split("/")
            attempt = session.get(Attempt, fetch_component[:36])
            policy = session.get(Policy, policy_id)
            source = session.get(Source, policy.source_id) if policy else None
            still_allowed = (
                policy is not None
                and source is not None
                and source.current_policy_id == policy.id
                and policy.state == "APPROVED"
                and policy.metadata_allowed
                and policy.effective_from <= now < policy.expires_at
            )
            if (
                still_allowed
                and attempt is not None
                and attempt.state == "LEASED"
                and attempt.lease_until is not None
                and attempt.lease_until > now
            ):
                continue  # A live object's DB acceptance may be waiting on this lock.
            store.delete(key)
            _audit_once(session, "ORPHAN_DELETED", key, policy.source_id if policy else None)
            result["orphans_deleted"] += 1
        for artifact in artifacts.values():
            policy = session.get(Policy, artifact.policy_id)
            source = session.get(Source, policy.source_id) if policy else None
            allowed = (
                policy is not None
                and source is not None
                and source.current_policy_id == policy.id
                and policy.state == "APPROVED"
                and policy.metadata_allowed
                and policy.effective_from <= now < policy.expires_at
                and artifact.expires_at > now
            )
            receipts = session.scalars(
                select(Receipt).where(Receipt.artifact_key == artifact.key)
            ).all()
            if not allowed:
                store.delete(artifact.key)
                if _audit_once(
                    session, "CONTENT_ERASED", artifact.key, policy.source_id if policy else None
                ):
                    result["content_erased"] += 1
                session.execute(text("SET LOCAL pulse.allow_erasure = 'on'"))
                for receipt in receipts:
                    revision_ids = session.scalars(
                        select(Observation.revision_id).where(Observation.receipt_id == receipt.id)
                    ).all()
                    session.execute(delete(Observation).where(Observation.receipt_id == receipt.id))
                    for revision_id in set(revision_ids):
                        if not session.scalar(
                            select(Observation.id)
                            .where(Observation.revision_id == revision_id)
                            .limit(1)
                        ):
                            session.execute(delete(Revision).where(Revision.id == revision_id))
                    _invalidate(session, receipt.id, "RIGHTS_OR_RETENTION_ERASURE")
                _invalidate(session, artifact.key, "RIGHTS_OR_RETENTION_ERASURE")
            elif not store.verify(artifact.key, artifact.sha256):
                if _audit_once(
                    session,
                    "ARTIFACT_MISSING_OR_CORRUPT",
                    artifact.key,
                    policy.source_id if policy else None,
                ):
                    result["missing_artifacts"] += 1
                    for receipt in receipts:
                        session.add(
                            HealthInterval(
                                source_id=receipt.source_id,
                                fetch_id=receipt.fetch_id,
                                state="RECOVERY_UNCERTAIN",
                                reason="ARTIFACT_MISSING_OR_CORRUPT",
                                started_at=receipt.received_at,
                                ended_at=None,
                                recorded_at=now,
                            )
                        )
                _invalidate(session, artifact.key, "ARTIFACT_MISSING_OR_CORRUPT")
                for receipt in receipts:
                    _invalidate(session, receipt.id, "ARTIFACT_MISSING_OR_CORRUPT")
            if (
                source is not None
                and source.cache_key == artifact.key
                and (not allowed or not store.verify(artifact.key, artifact.sha256))
            ):
                source.cache_key = source.etag = source.last_modified = None
        for attempt in session.scalars(
            select(Attempt).where(Attempt.state == "LEASED", Attempt.lease_until <= now)
        ):
            if _audit_once(
                session, "EXPIRED_CAPTURE_LEASE", f"{attempt.id}:{attempt.fence}", attempt.source_id
            ):
                result["expired_attempts"] += 1
                session.add(
                    HealthInterval(
                        source_id=attempt.source_id,
                        fetch_id=attempt.id,
                        state="UNAVAILABLE",
                        reason="EXPIRED_CAPTURE_LEASE",
                        started_at=attempt.scheduled_at,
                        ended_at=None,
                        recorded_at=now,
                    )
                )
            # Claim handles fence increment; recovery must not grant a stale fence new rights.
        for receipt in session.scalars(select(Receipt)):
            if not session.scalar(
                select(Availability.id).where(
                    Availability.kind == "receipt", Availability.entity_id == receipt.id
                )
            ):
                to_witness.append(("receipt", receipt.id))
            consumed = session.scalar(
                select(Consumption)
                .join(Outbox)
                .where(Outbox.receipt_id == receipt.id, Consumption.consumer == "metadata-parser")
            )
            if consumed and not session.scalar(
                select(Availability.id).where(
                    Availability.kind == "parsed_receipt", Availability.entity_id == receipt.id
                )
            ):
                to_witness.append(("parsed_receipt", receipt.id))
    for kind, entity_id in to_witness:
        mark_available(engine, kind, entity_id)
        result["witnesses_recovered"] += 1
    return result
