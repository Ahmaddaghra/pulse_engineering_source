from sqlalchemy import Engine, select, text

from pulse.db import db_now, evidence_lock, transaction
from pulse.models import Availability, Consumption, Outbox, Receipt, Snapshot


def mark_available(engine: Engine, kind: str, entity_id: str) -> None:
    """Post-commit observation of durable state, never a predicted commit timestamp.

    Failure here delays availability; recovery can safely append the witness later.
    Snapshot sealing only includes witnesses already committed when it takes the lock.
    """
    if kind not in {"receipt", "parsed_receipt", "snapshot"}:
        raise ValueError("Unsupported availability kind")
    with transaction(engine) as session:
        evidence_lock(session)
        if session.scalar(
            select(Availability).where(
                Availability.kind == kind, Availability.entity_id == entity_id
            )
        ):
            return
        if kind == "receipt" and session.get(Receipt, entity_id) is None:
            raise ValueError("Receipt is not committed")
        if kind == "parsed_receipt" and not session.scalar(
            select(Consumption)
            .join(Outbox, Consumption.event_id == Outbox.id)
            .where(
                Outbox.receipt_id == entity_id,
                Outbox.topic == "parse_requested",
                Consumption.consumer == "metadata-parser",
                Consumption.version == Outbox.version,
            )
        ):
            raise ValueError("Parsing is not committed")
        if kind == "snapshot" and session.get(Snapshot, entity_id) is None:
            raise ValueError("Snapshot is not committed")
        session.add(
            Availability(
                kind=kind,
                entity_id=entity_id,
                postcommit_observed_at=db_now(session),
                db_snapshot=str(session.scalar(text("SELECT pg_current_snapshot()"))),
            )
        )
