from datetime import datetime
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from pulse.db import db_now, evidence_lock, transaction
from pulse.errors import PolicyBlocked
from pulse.models import Audit, OriginBudget, Policy, Source

FIELDS = {"guid", "url", "title", "published_at", "published_precision"}


class PolicyInput(BaseModel):
    publisher_id: str = Field(min_length=1, max_length=80)
    owner_id: str = Field(min_length=1, max_length=80)
    endpoint: str
    allowed_host: str = Field(min_length=1, max_length=253)
    scope: str = "offline_fixture"
    state: str = "APPROVED"
    effective_from: datetime
    expires_at: datetime
    approved_by: str = Field(min_length=1, max_length=100)
    metadata_allowed: bool = True
    link_display_allowed: bool = False
    derived_allowed: bool = True
    training_allowed: bool = False
    allowed_fields: list[str] = Field(default_factory=lambda: sorted(FIELDS))
    retention_seconds: int = Field(default=86400, ge=1, le=31536000)
    poll_seconds: int = Field(default=60, ge=1, le=86400)
    max_bytes: int = Field(default=1048576, ge=1, le=4194304)
    max_items: int = Field(default=200, ge=0, le=1000)
    max_depth: int = Field(default=32, ge=1, le=64)
    max_text_chars: int = Field(default=4096, ge=1, le=16384)
    timeout_seconds: int = Field(default=10, ge=1, le=30)
    rate_scope: str = Field(min_length=1, max_length=200)
    min_request_seconds: int = Field(default=1, ge=0, le=86400)
    attribution: str = "Synthetic software fixture"
    timestamp_quality: str = "publisher_claim_unverified"
    rollover_seconds: int = Field(default=3600, ge=1, le=604800)
    deletion_procedure: str = "erase_content_keep_noncontent_audit"

    @model_validator(mode="after")
    def validate_contract(self) -> "PolicyInput":
        if self.scope not in {"offline_fixture", "observed_metadata"}:
            raise ValueError("Unsupported use scope")
        if self.state not in {"APPROVED", "REVOKED", "UNKNOWN"}:
            raise ValueError("Unknown approval state")
        if any(value.tzinfo is None for value in (self.effective_from, self.expires_at)):
            raise ValueError("Approval timestamps need explicit UTC offsets")
        if self.expires_at <= self.effective_from:
            raise ValueError("Empty approval interval")
        if not set(self.allowed_fields) <= FIELDS:
            raise ValueError("Only the metadata-envelope-v1 fields are supported")
        if not {"guid", "url"} & set(self.allowed_fields):
            raise ValueError("At least one identity field must be permitted")
        endpoint = urlsplit(self.endpoint)
        if self.scope == "offline_fixture":
            if endpoint.scheme != "fixture" or endpoint.hostname != self.allowed_host:
                raise ValueError("Offline policies require a fixture endpoint")
        elif endpoint.scheme != "https" or endpoint.hostname != self.allowed_host.lower():
            raise ValueError("Remote policies require an exact HTTPS host")
        if self.training_allowed:
            raise ValueError("Training is outside M1")
        return self


def register_policy(engine: Engine, source_id: str, feed_id: str, values: PolicyInput) -> str:
    with transaction(engine) as session:
        evidence_lock(session)
        now = db_now(session)
        source = session.get(Source, source_id, with_for_update=True)
        if source is None:
            source = Source(id=source_id, feed_id=feed_id, next_due_at=now)
            session.add(source)
            session.flush()
        elif source.feed_id != feed_id:
            raise ValueError("A source's feed identity is immutable")
        previous = (
            session.get(Policy, source.current_policy_id) if source.current_policy_id else None
        )
        policy = Policy(
            source_id=source_id,
            version=1 if previous is None else previous.version + 1,
            approved_at=now,
            **values.model_dump(),
        )
        session.add(policy)
        session.flush()
        source.current_policy_id = policy.id
        # Validators must never cross approval versions.
        source.cache_key = source.etag = source.last_modified = None
        if session.get(OriginBudget, policy.rate_scope) is None:
            session.add(OriginBudget(id=policy.rate_scope, next_allowed_at=now))
        session.add(
            Audit(
                source_id=source_id,
                code="POLICY_VERSION_REGISTERED",
                reference_id=policy.id,
                recorded_at=now,
            )
        )
        return policy.id


def require_policy(
    session: Session, source_id: str, expected_policy_id: str | None = None
) -> Policy:
    source = session.scalar(select(Source).where(Source.id == source_id).with_for_update())
    if source is None or source.current_policy_id is None:
        raise PolicyBlocked("UNKNOWN_SOURCE")
    if expected_policy_id is not None and source.current_policy_id != expected_policy_id:
        raise PolicyBlocked("POLICY_VERSION_CHANGED")
    policy = session.get(Policy, source.current_policy_id)
    now = db_now(session)
    if (
        policy is None
        or policy.state != "APPROVED"
        or not policy.metadata_allowed
        or policy.effective_from > now
        or policy.expires_at <= now
    ):
        raise PolicyBlocked("RIGHTS_BLOCKED")
    return policy


def revoke_policy(engine: Engine, source_id: str, actor: str) -> str:
    with transaction(engine) as session:
        source = session.get(Source, source_id)
        if source is None or not source.current_policy_id:
            raise PolicyBlocked("UNKNOWN_SOURCE")
        policy = session.get(Policy, source.current_policy_id)
        assert policy is not None
        data = {name: getattr(policy, name) for name in PolicyInput.model_fields}
        feed_id = source.feed_id
    data.update(state="REVOKED", approved_by=actor)
    return register_policy(engine, source_id, feed_id, PolicyInput.model_validate(data))
