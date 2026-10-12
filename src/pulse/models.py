"""Evidence is append-only; lease, cache and registry heads are operational state."""

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def new_id() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    feed_id: Mapped[str] = mapped_column(String(120), unique=True)
    current_policy_id: Mapped[str | None] = mapped_column(
        ForeignKey("source_policies.id", name="fk_source_policy_head", use_alter=True)
    )
    next_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    cache_key: Mapped[str | None] = mapped_column(String(240))
    etag: Mapped[str | None] = mapped_column(String(512))
    last_modified: Mapped[str | None] = mapped_column(String(512))


class Policy(Base):
    __tablename__ = "source_policies"
    __table_args__ = (
        UniqueConstraint("source_id", "version"),
        CheckConstraint(
            "retention_seconds > 0 AND expires_at > effective_from",
            name="policy_retention_positive",
        ),
        CheckConstraint(
            "max_bytes BETWEEN 1 AND 4194304 AND max_items BETWEEN 0 AND 1000 "
            "AND max_depth BETWEEN 1 AND 64 AND timeout_seconds BETWEEN 1 AND 30",
            name="policy_limits_bounded",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))
    version: Mapped[int]
    publisher_id: Mapped[str] = mapped_column(String(80))
    owner_id: Mapped[str] = mapped_column(String(80))
    endpoint: Mapped[str]
    allowed_host: Mapped[str] = mapped_column(String(253))
    scope: Mapped[str] = mapped_column(String(40))  # offline_fixture or observed_metadata
    state: Mapped[str] = mapped_column(String(20))
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[str] = mapped_column(String(100))
    metadata_allowed: Mapped[bool]
    link_display_allowed: Mapped[bool] = mapped_column(default=False)
    derived_allowed: Mapped[bool] = mapped_column(default=False)
    training_allowed: Mapped[bool] = mapped_column(default=False)
    allowed_fields: Mapped[list[str]] = mapped_column(JSONB)
    retention_seconds: Mapped[int]
    poll_seconds: Mapped[int] = mapped_column(default=60)
    max_bytes: Mapped[int] = mapped_column(default=1048576)
    max_items: Mapped[int] = mapped_column(default=200)
    max_depth: Mapped[int] = mapped_column(default=32)
    max_text_chars: Mapped[int] = mapped_column(default=4096)
    timeout_seconds: Mapped[int] = mapped_column(default=10)
    rate_scope: Mapped[str] = mapped_column(String(200))
    min_request_seconds: Mapped[int] = mapped_column(default=1)
    attribution: Mapped[str] = mapped_column(default="")
    timestamp_quality: Mapped[str] = mapped_column(default="publisher_claim_unverified")
    rollover_seconds: Mapped[int] = mapped_column(default=3600)
    deletion_procedure: Mapped[str] = mapped_column(default="erase_content_keep_noncontent_audit")


class OriginBudget(Base):
    __tablename__ = "origin_budgets"
    id: Mapped[str] = mapped_column(String(200), primary_key=True)
    next_allowed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    open_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consecutive_failures: Mapped[int] = mapped_column(default=0)
    breaker_state: Mapped[str] = mapped_column(String(20), default="CLOSED")


class Attempt(Base):
    __tablename__ = "fetch_attempts"
    __table_args__ = (
        UniqueConstraint("source_id", "schedule_key"),
        CheckConstraint("fence >= 0", name="attempt_fence_nonnegative"),
        Index("ix_attempt_due", "state", "due_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))
    policy_id: Mapped[str] = mapped_column(ForeignKey("source_policies.id"))
    rate_scope: Mapped[str] = mapped_column(ForeignKey("origin_budgets.id"))
    schedule_key: Mapped[str] = mapped_column(String(100))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    state: Mapped[str] = mapped_column(String(20), default="PENDING")
    tries: Mapped[int] = mapped_column(default=0)
    fence: Mapped[int] = mapped_column(default=0)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(80))


class Artifact(Base):
    __tablename__ = "artifacts"
    key: Mapped[str] = mapped_column(String(240), primary_key=True)
    policy_id: Mapped[str] = mapped_column(ForeignKey("source_policies.id"))
    sha256: Mapped[str] = mapped_column(String(64))
    size: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Receipt(Base):
    __tablename__ = "fetch_receipts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    fetch_id: Mapped[str] = mapped_column(ForeignKey("fetch_attempts.id"), unique=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))
    policy_id: Mapped[str] = mapped_column(ForeignKey("source_policies.id"))
    artifact_key: Mapped[str] = mapped_column(ForeignKey("artifacts.key"))
    http_status: Mapped[int]
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    schema_version: Mapped[str] = mapped_column(String(40), default="metadata-envelope-v1")
    collection_parser_version: Mapped[str] = mapped_column(
        String(40), default="xml-metadata-v1", server_default="xml-metadata-v1"
    )
    clock_quality: Mapped[str] = mapped_column(default="collector_utc_db_clock_unqualified")


class Outbox(Base):
    __tablename__ = "outbox"
    __table_args__ = (
        UniqueConstraint("topic", "receipt_id", "version"),
        Index("ix_outbox_due", "topic", "state", "due_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    topic: Mapped[str] = mapped_column(String(80))
    receipt_id: Mapped[str] = mapped_column(ForeignKey("fetch_receipts.id"))
    version: Mapped[str] = mapped_column(String(40), default="parser-v1")
    state: Mapped[str] = mapped_column(String(20), default="PENDING")
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    tries: Mapped[int] = mapped_column(default=0)
    fence: Mapped[int] = mapped_column(default=0)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(80))


class Consumption(Base):
    __tablename__ = "consumptions"
    consumer: Mapped[str] = mapped_column(String(80), primary_key=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("outbox.id"), primary_key=True)
    version: Mapped[str] = mapped_column(String(40), primary_key=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Occurrence(Base):
    __tablename__ = "publication_occurrences"
    __table_args__ = (UniqueConstraint("publisher_id", "identity_key", "identity_version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    publisher_id: Mapped[str] = mapped_column(String(80))
    identity_key: Mapped[str] = mapped_column(String(64))
    identity_version: Mapped[str] = mapped_column(String(40), default="occurrence-v1")
    identity_confidence: Mapped[str] = mapped_column(String(40))


class Revision(Base):
    __tablename__ = "article_revisions"
    __table_args__ = (
        UniqueConstraint(
            "occurrence_id",
            "fingerprint",
            "parser_version",
            "normalization_version",
            "schema_version",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    occurrence_id: Mapped[str] = mapped_column(ForeignKey("publication_occurrences.id"))
    fingerprint: Mapped[str] = mapped_column(String(64))
    fields: Mapped[dict[str, Any]] = mapped_column(JSONB)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_precision: Mapped[str] = mapped_column(String(30))
    parser_version: Mapped[str] = mapped_column(String(40))
    normalization_version: Mapped[str] = mapped_column(String(40))
    schema_version: Mapped[str] = mapped_column(String(40))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Observation(Base):
    __tablename__ = "feed_item_observations"
    __table_args__ = (
        UniqueConstraint("receipt_id", "ordinal", "parser_version"),
        Index("ix_observation_occurrence", "occurrence_id", "received_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    receipt_id: Mapped[str] = mapped_column(ForeignKey("fetch_receipts.id"))
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))
    feed_id: Mapped[str] = mapped_column(String(120))
    ordinal: Mapped[int]
    occurrence_id: Mapped[str] = mapped_column(ForeignKey("publication_occurrences.id"))
    revision_id: Mapped[str] = mapped_column(ForeignKey("article_revisions.id"))
    parser_version: Mapped[str] = mapped_column(String(40))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Availability(Base):
    __tablename__ = "availability_witnesses"
    __table_args__ = (UniqueConstraint("kind", "entity_id"),)
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    kind: Mapped[str] = mapped_column(String(40))  # receipt or parsed_receipt or snapshot
    entity_id: Mapped[str] = mapped_column(String(36))
    postcommit_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    db_snapshot: Mapped[str]


class HealthInterval(Base):
    __tablename__ = "source_health_intervals"
    __table_args__ = (Index("ix_health_source", "source_id", "recorded_at"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))
    fetch_id: Mapped[str | None] = mapped_column(ForeignKey("fetch_attempts.id"))
    state: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str] = mapped_column(String(80))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class Snapshot(Base):
    __tablename__ = "snapshots"
    __table_args__ = (
        UniqueConstraint("run_id", "panel_hash", "cutoff_at", "candidate_policy_version", "kind"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(String(100))
    panel_hash: Mapped[str] = mapped_column(String(64))
    cutoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    candidate_policy_version: Mapped[str] = mapped_column(String(40), default="observed-list-v1")
    kind: Mapped[str] = mapped_column(String(40), default="OBSERVED_ONLY")
    manifest: Mapped[str]
    sha256: Mapped[str] = mapped_column(String(64))


class SnapshotInvalidation(Base):
    __tablename__ = "snapshot_invalidations"
    __table_args__ = (UniqueConstraint("snapshot_id", "reason", "reference_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("snapshots.id"))
    reason: Mapped[str] = mapped_column(String(80))
    reference_id: Mapped[str] = mapped_column(String(240))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Audit(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_id: Mapped[str | None] = mapped_column(ForeignKey("sources.id"))
    code: Mapped[str] = mapped_column(String(80))
    reference_id: Mapped[str] = mapped_column(String(240))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
