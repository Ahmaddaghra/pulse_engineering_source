"""Persisted scheduling, admission, capture, compensation and acknowledgment."""

import hashlib
import json
import random
from collections.abc import Callable
from datetime import timedelta

from sqlalchemy import Engine, and_, exists, or_, select
from sqlalchemy.orm import Session, aliased

from pulse.availability import mark_available
from pulse.collection import (
    CollectionBlocked,
    CollectionCapability,
    CollectionError,
    Collector,
    backoff_seconds,
    parse_feed,
    parse_retry_after,
)
from pulse.config import Settings
from pulse.db import db_now, evidence_lock, transaction
from pulse.errors import PolicyBlocked, StaleLease
from pulse.models import (
    Artifact,
    Attempt,
    HealthInterval,
    OriginBudget,
    Outbox,
    Policy,
    Receipt,
    Source,
)
from pulse.objects import LocalObjectStore
from pulse.policy import require_policy

FaultHook = Callable[[str], None]


def schedule(engine: Engine, *, limit: int = 100, max_pending: int = 1000) -> list[str]:
    """Idempotent slot scheduling with a bounded durable backlog."""
    scheduled: list[str] = []
    with transaction(engine) as session:
        evidence_lock(session)
        now = db_now(session)
        pending = len(
            session.scalars(
                select(Attempt.id)
                .where(Attempt.state.in_(["PENDING", "LEASED"]))
                .limit(max_pending)
            ).all()
        )
        for source in session.scalars(
            select(Source)
            .where(Source.next_due_at <= now)
            .order_by(Source.next_due_at)
            .limit(limit)
            .with_for_update()
        ):
            existing = session.scalar(
                select(Attempt)
                .where(Attempt.source_id == source.id, Attempt.state.in_(["PENDING", "LEASED"]))
                .limit(1)
            )
            if existing is not None:
                # One durable attempt/retry chain per source; throttles cannot flood the backlog.
                budget = session.get(OriginBudget, existing.rate_scope)
                policy = session.get(Policy, existing.policy_id)
                delay = policy.poll_seconds if policy is not None else 60
                source.next_due_at = max(
                    now + timedelta(seconds=delay),
                    budget.next_allowed_at if budget is not None else now,
                )
                continue
            if pending >= max_pending:
                if not session.scalar(
                    select(HealthInterval.id)
                    .where(
                        HealthInterval.source_id == source.id,
                        HealthInterval.reason == "SCHEDULER_BACKPRESSURE",
                        HealthInterval.ended_at.is_(None),
                    )
                    .limit(1)
                ):
                    session.add(
                        HealthInterval(
                            source_id=source.id,
                            state="UNAVAILABLE",
                            reason="SCHEDULER_BACKPRESSURE",
                            started_at=source.next_due_at,
                            ended_at=None,
                            recorded_at=now,
                        )
                    )
                continue
            try:
                policy = require_policy(session, source.id)
            except PolicyBlocked:
                source.next_due_at = now + timedelta(seconds=60)
                session.add(
                    HealthInterval(
                        source_id=source.id,
                        state="RIGHTS_BLOCKED",
                        reason="SCHEDULE_POLICY_BLOCKED",
                        started_at=now,
                        ended_at=None,
                        recorded_at=now,
                    )
                )
                continue
            attempt = Attempt(
                source_id=source.id,
                policy_id=policy.id,
                rate_scope=policy.rate_scope,
                schedule_key=source.next_due_at.isoformat(),
                scheduled_at=source.next_due_at,
                due_at=now,
            )
            session.add(attempt)
            session.flush()
            scheduled.append(attempt.id)
            pending += 1
            source.next_due_at = now + timedelta(seconds=policy.poll_seconds)
    return scheduled


def claim_capture(engine: Engine, settings: Settings) -> tuple[str, int] | None:
    with transaction(engine) as session:
        evidence_lock(session)
        now = db_now(session)
        active = aliased(Attempt)
        candidates = session.scalars(
            select(Attempt)
            .join(OriginBudget)
            .where(
                Attempt.due_at <= now,
                or_(
                    Attempt.state == "PENDING",
                    and_(Attempt.state == "LEASED", Attempt.lease_until <= now),
                ),
                OriginBudget.next_allowed_at <= now,
                ~exists(
                    select(active.id).where(
                        active.id != Attempt.id,
                        active.rate_scope == Attempt.rate_scope,
                        active.state == "LEASED",
                        active.lease_until > now,
                    )
                ),
            )
            .order_by(Attempt.due_at, Attempt.id)
            .limit(100)
            .with_for_update(of=Attempt, skip_locked=True)
        ).all()
        for attempt in candidates:
            if attempt.tries >= settings.max_attempts:
                attempt.state, attempt.error_code = "FAILED", "RETRY_EXHAUSTED"
                session.add(
                    HealthInterval(
                        source_id=attempt.source_id,
                        fetch_id=attempt.id,
                        state="UNAVAILABLE",
                        reason="RETRY_EXHAUSTED",
                        started_at=attempt.scheduled_at,
                        ended_at=None,
                        recorded_at=now,
                    )
                )
                continue
            try:
                policy = require_policy(session, attempt.source_id, attempt.policy_id)
            except PolicyBlocked:
                attempt.state, attempt.error_code = "FAILED", "RIGHTS_BLOCKED"
                session.add(
                    HealthInterval(
                        source_id=attempt.source_id,
                        fetch_id=attempt.id,
                        state="RIGHTS_BLOCKED",
                        reason="PRE_REQUEST_BLOCKED",
                        started_at=attempt.scheduled_at,
                        ended_at=None,
                        recorded_at=now,
                    )
                )
                continue
            budget = session.get(OriginBudget, attempt.rate_scope, with_for_update=True)
            assert budget is not None
            if budget.open_until is not None and budget.open_until > now:
                continue
            if budget.breaker_state == "OPEN":
                budget.breaker_state = "HALF_OPEN"
            budget.next_allowed_at = now + timedelta(seconds=policy.min_request_seconds)
            attempt.fence += 1
            attempt.tries += 1
            attempt.state = "LEASED"
            attempt.payload_expires_at = None
            attempt.lease_until = now + timedelta(seconds=settings.lease_seconds)
            return attempt.id, attempt.fence
    return None


def _fenced(session: Session, fetch_id: str, fence: int) -> Attempt:
    attempt = session.get(Attempt, fetch_id, with_for_update=True)
    if (
        attempt is None
        or attempt.state != "LEASED"
        or attempt.fence != fence
        or attempt.lease_until is None
        or attempt.lease_until <= db_now(session)
    ):
        raise StaleLease("Capture lease expired or superseded")
    return attempt


def _failure(
    engine: Engine,
    settings: Settings,
    fetch_id: str,
    fence: int,
    code: str,
    *,
    retry_after: str | None = None,
    terminal: bool = False,
) -> None:
    with transaction(engine) as session:
        evidence_lock(session)
        attempt = _fenced(session, fetch_id, fence)
        now = db_now(session)
        budget = session.get(OriginBudget, attempt.rate_scope, with_for_update=True)
        assert budget is not None
        delay = parse_retry_after(retry_after, now=now, max_seconds=604800)
        if delay is None:
            delay = backoff_seconds(
                attempt.tries, base_seconds=1, cap_seconds=300, random_fraction=random.random()
            )
        budget.consecutive_failures += 1
        due = now + timedelta(seconds=delay)
        budget.next_allowed_at = max(budget.next_allowed_at, due)
        if budget.consecutive_failures >= 3:
            budget.breaker_state = "OPEN"
            budget.open_until = max(due, now + timedelta(seconds=30))
            budget.next_allowed_at = budget.open_until
        attempt.error_code = code
        attempt.state = (
            "FAILED" if terminal or attempt.tries >= settings.max_attempts else "PENDING"
        )
        attempt.due_at = budget.next_allowed_at
        attempt.lease_until = None
        state = (
            "RIGHTS_BLOCKED"
            if code == "RIGHTS_BLOCKED"
            else "RATE_LIMITED"
            if code in {"HTTP_429", "HTTP_503"}
            else "PARSER_DEGRADED"
            if code == "UNSAFE_REPRESENTATION"
            else "UNAVAILABLE"
        )
        session.add(
            HealthInterval(
                source_id=attempt.source_id,
                fetch_id=fetch_id,
                state=state,
                reason=code,
                started_at=attempt.scheduled_at,
                ended_at=None,
                recorded_at=now,
                details={"retry_due_at": attempt.due_at.isoformat(), "try": attempt.tries},
            )
        )


def capture(
    engine: Engine,
    settings: Settings,
    store: LocalObjectStore,
    collector: Collector,
    fetch_id: str,
    fence: int,
    *,
    fault: FaultHook | None = None,
) -> str | None:
    def checkpoint(stage: str) -> None:
        if fault is not None:
            fault(stage)

    key: str | None = None
    newly_written = False
    receipt_committed = False
    try:
        with transaction(engine) as session:
            evidence_lock(session)
            attempt = _fenced(session, fetch_id, fence)
            policy = require_policy(session, attempt.source_id, attempt.policy_id)
            if policy.scope != "offline_fixture" and not settings.live_enabled:
                raise CollectionBlocked("LIVE_DISABLED")
            if (
                policy.scope != "offline_fixture"
                and settings.lease_seconds <= policy.timeout_seconds + 2
            ):
                raise CollectionBlocked("LIVE_LEASE_TOO_SHORT")
            source = session.get(Source, attempt.source_id)
            assert source is not None
            source_id, policy_id = source.id, policy.id
            cache_key, etag, last_modified = source.cache_key, source.etag, source.last_modified
            assert attempt.lease_until is not None
            request = dict(
                endpoint=policy.endpoint,
                allowed_host=policy.allowed_host,
                max_bytes=policy.max_bytes,
                timeout_seconds=policy.timeout_seconds,
                etag=etag,
                last_modified=last_modified,
                capability=CollectionCapability(
                    policy.id,
                    policy.endpoint,
                    policy.allowed_host,
                    min(policy.expires_at, attempt.lease_until),
                ),
            )
            limits = (policy.max_bytes, policy.max_depth, policy.max_items, policy.max_text_chars)
        checkpoint("before_fetch")
        response = collector.collect(**request)  # type: ignore[arg-type]
        checkpoint("after_fetch")
        if response.status in {429, 503}:
            _failure(
                engine,
                settings,
                fetch_id,
                fence,
                f"HTTP_{response.status}",
                retry_after=response.retry_after,
            )
            return None
        if response.status not in {200, 304}:
            _failure(engine, settings, fetch_id, fence, "HTTP_FAILURE")
            return None
        if response.received_at.tzinfo is None:
            raise CollectionError("Response timestamp has no timezone")
        if response.status == 200:
            items = parse_feed(
                response.body,
                max_bytes=limits[0],
                max_depth=limits[1],
                max_items=limits[2],
                max_text_chars=limits[3],
            )
        with transaction(engine) as session:
            evidence_lock(session)
            attempt = _fenced(session, fetch_id, fence)
            policy = require_policy(session, source_id, policy_id)
            now = db_now(session)
            if response.received_at > now + timedelta(seconds=1):
                raise CollectionError("Response clock is ahead of database")
            if response.status == 304:
                artifact = session.get(Artifact, cache_key) if cache_key else None
                if (
                    artifact is None
                    or artifact.policy_id != policy_id
                    or artifact.expires_at <= now
                    or not store.verify(artifact.key, artifact.sha256)
                ):
                    source = session.get(Source, source_id)
                    assert source is not None
                    source.cache_key = source.etag = source.last_modified = None
                    # Persist clearing before retry; never accept a fictitious usable 304.
                    key = None
                else:
                    key = artifact.key
                    digest, size, expires = artifact.sha256, artifact.size, artifact.expires_at
            else:
                envelope = {
                    "schema_version": "metadata-envelope-v1",
                    "items": [
                        {
                            name: value
                            for name, value in item.items()
                            if name in policy.allowed_fields and value is not None
                        }
                        for item in items
                    ],
                }
                data = json.dumps(
                    envelope, sort_keys=True, ensure_ascii=False, separators=(",", ":")
                ).encode()
                if len(data) > policy.max_bytes:
                    raise CollectionError("Permitted envelope exceeds storage byte budget")
                digest, size = hashlib.sha256(data).hexdigest(), len(data)
                expires = min(
                    policy.expires_at,
                    response.received_at + timedelta(seconds=policy.retention_seconds),
                )
                if expires <= now:
                    raise CollectionError("Representation retention already expired")
                attempt.payload_expires_at = expires
                # The rights lock is released during I/O. Acceptance rechecks below.
        if response.status == 304 and key is None:
            _failure(engine, settings, fetch_id, fence, "CACHE_MISSING")
            return None
        if response.status == 200:
            key = store.put(policy_id, f"{fetch_id}-{fence}", data)
            newly_written = True
            checkpoint("after_object_write")
        assert key is not None
        with transaction(engine) as session:
            evidence_lock(session)
            attempt = _fenced(session, fetch_id, fence)
            policy = require_policy(session, source_id, policy_id)
            now = db_now(session)
            if expires <= now or not store.verify(key, digest):
                raise CollectionError("Artifact unavailable before acceptance")
            if session.get(Artifact, key) is None:
                session.add(
                    Artifact(
                        key=key,
                        policy_id=policy_id,
                        sha256=digest,
                        size=size,
                        created_at=now,
                        expires_at=expires,
                    )
                )
                session.flush()
            receipt = Receipt(
                fetch_id=fetch_id,
                source_id=source_id,
                policy_id=policy_id,
                artifact_key=key,
                http_status=response.status,
                received_at=response.received_at,
                recorded_at=now,
            )
            session.add(receipt)
            session.flush()
            session.add(Outbox(topic="parse_requested", receipt_id=receipt.id, due_at=now))
            source = session.get(Source, source_id)
            assert source is not None
            source.cache_key = key
            source.etag = response.etag if response.status == 200 else response.etag or etag
            source.last_modified = (
                response.last_modified
                if response.status == 200
                else response.last_modified or last_modified
            )
            budget = session.get(OriginBudget, attempt.rate_scope, with_for_update=True)
            assert budget is not None
            budget.consecutive_failures, budget.breaker_state, budget.open_until = 0, "CLOSED", None
            session.add(
                HealthInterval(
                    source_id=source_id,
                    fetch_id=fetch_id,
                    state="NO_CHANGE_VALID_CACHE" if response.status == 304 else "OK",
                    reason="CAPTURE_COMMITTED",
                    started_at=attempt.scheduled_at,
                    ended_at=now,
                    recorded_at=now,
                    details={"parse_pending": True, "publication_completeness": "unknown"},
                )
            )
            checkpoint("before_receipt_commit")
            _fenced(session, fetch_id, fence)
            require_policy(session, source_id, policy_id)
            attempt.state, attempt.lease_until = "CAPTURED", None
            receipt_id = receipt.id
        receipt_committed = True
        checkpoint("after_receipt_commit")
        mark_available(engine, "receipt", receipt_id)
        return receipt_id  # ACK only after receipt+cache+artifact reference+outbox commit.
    except (PolicyBlocked, CollectionBlocked) as exc:
        if receipt_committed:
            raise
        if newly_written and key is not None:
            store.delete(key)
        code = "RIGHTS_BLOCKED" if isinstance(exc, PolicyBlocked) else "COLLECTION_BLOCKED"
        _failure(engine, settings, fetch_id, fence, code, terminal=True)
        return None
    except (CollectionError, OSError):
        if receipt_committed:
            raise
        if newly_written and key is not None:
            store.delete(key)
        _failure(engine, settings, fetch_id, fence, "UNSAFE_REPRESENTATION")
        return None
    except StaleLease:
        if receipt_committed:
            raise
        if newly_written and key is not None:
            store.delete(key)
        raise


def run_capture_once(
    engine: Engine, settings: Settings, store: LocalObjectStore, collector: Collector
) -> str | None:
    claim = claim_capture(engine, settings)
    return capture(engine, settings, store, collector, *claim) if claim else None
