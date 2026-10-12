"""At-least-once parse delivery with fenced, idempotent evidence transactions.

The input is a permitted metadata envelope, never XML or full article text. M1
stops at observations and revisions; parsing does not claim event resolution.
"""

import hashlib
import json
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import Engine, and_, or_, select
from sqlalchemy.orm import Session

from pulse.availability import mark_available
from pulse.db import db_now, evidence_lock, transaction
from pulse.errors import PolicyBlocked, StaleLease
from pulse.models import (
    Artifact,
    Consumption,
    HealthInterval,
    Observation,
    Occurrence,
    Outbox,
    Policy,
    Receipt,
    Revision,
    Source,
)
from pulse.objects import LocalObjectStore
from pulse.policy import require_policy

PARSER_VERSION = "parser-v1"
NORMALIZATION_VERSION = "normalization-v1"
SCHEMA_VERSION = "metadata-envelope-v1"
IDENTITY_VERSION = "occurrence-v1"
CONSUMER = "metadata-parser"
MAX_PARSE_ATTEMPTS = 4
SUPPORTED_FIELDS = frozenset({"guid", "url", "title", "published_at", "published_precision"})
Fault = Callable[[str], None]

_ISO_TIME = re.compile(
    r"^\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}"
    r"(?::\d{2}(?:[.,](\d+))?)?(?:[Zz]|[+-]\d{2}:?\d{2})?$"
)


class InvalidEnvelope(Exception):
    """A recoverable object cannot be safely interpreted by this parser version."""


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def published_time(raw: str | None) -> tuple[datetime | None, str]:
    """Keep an unqualified publisher claim unqualified; never infer its timezone."""
    if not raw or not raw.strip():
        return None, "unknown"
    value = raw.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        try:
            datetime.fromisoformat(value)
        except ValueError:
            return None, "invalid"
        return None, "date"
    match = _ISO_TIME.fullmatch(value)
    try:
        if match:
            fraction = match.group(1)
            if fraction and len(fraction) > 6:
                return None, "unsupported_precision"
            parsed = datetime.fromisoformat(value.replace("z", "+00:00").replace("Z", "+00:00"))
            precision = (
                f"fractional_{len(fraction)}"
                if fraction
                else "second"
                if re.search(r"[Tt ]\d{2}:\d{2}:\d{2}", value)
                else "minute"
            )
        else:
            parsed = parsedate_to_datetime(value)
            precision = "second" if re.search(r"\d{1,2}:\d{2}:\d{2}", value) else "minute"
    except (ValueError, TypeError, OverflowError):
        return None, "invalid"
    if parsed.tzinfo is None:
        return None, "timezone_unknown"
    return parsed.astimezone(UTC), precision


def normalize_url(raw: str) -> str:
    """A versioned conservative identity normalization, with original URL retained."""
    try:
        parts = urlsplit(raw.strip())
        host = parts.hostname
        if parts.scheme.lower() not in {"http", "https"} or not host or parts.username:
            raise ValueError("URL lacks a supported absolute identity")
        port = parts.port
    except ValueError as exc:
        raise InvalidEnvelope("invalid_item_url") from exc
    host = host.lower()
    if ":" in host:
        host = f"[{host}]"
    scheme = parts.scheme.lower()
    authority = host
    if port is not None and (scheme, port) not in {("http", 80), ("https", 443)}:
        authority += f":{port}"
    return urlunsplit((scheme, authority, parts.path or "/", parts.query, ""))


def occurrence_identity(
    item: dict[str, str], published_at: datetime | None, precision: str
) -> tuple[str, str]:
    guid = item.get("guid", "").strip()
    raw_url = item.get("url", "").strip()
    identity: dict[str, str] = {}
    if guid:
        identity["guid"] = guid
        confidence = "guid_only_ambiguous"
    elif raw_url:
        identity["url"] = normalize_url(raw_url)
        confidence = "url_only_ambiguous"
    else:
        raise InvalidEnvelope("item_identity_missing")
    if published_at is not None:
        identity["published_at"] = published_at.isoformat()
        identity["precision"] = precision
        confidence = "guid_timestamp" if guid else "url_timestamp_ambiguous"
    return hashlib.sha256(_json_bytes(identity)).hexdigest(), confidence


def _leased(event: Outbox, fence: int, now: datetime) -> None:
    if (
        event.topic != "parse_requested"
        or event.state != "PROCESSING"
        or event.fence != fence
        or event.lease_until is None
        or event.lease_until <= now
    ):
        raise StaleLease("parse worker no longer holds this event's current lease")


def claim_parse(engine: Engine, lease_seconds: int = 30) -> tuple[str, int] | None:
    if not 1 <= lease_seconds <= 300:
        raise ValueError("lease_seconds must be between 1 and 300")
    with transaction(engine) as session:
        evidence_lock(session)
        now = db_now(session)
        eligible = or_(
            and_(Outbox.state.in_(["PENDING", "RETRY"]), Outbox.due_at <= now),
            and_(Outbox.state == "PROCESSING", Outbox.lease_until <= now),
        )
        event = session.scalar(
            select(Outbox)
            .where(Outbox.topic == "parse_requested", eligible)
            .order_by(Outbox.due_at, Outbox.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if event is None:
            return None
        # A committed effect still needs its ACK even after the final claim crashed.
        consumed = session.get(Consumption, (CONSUMER, event.id, event.version)) is not None
        if event.tries >= MAX_PARSE_ATTEMPTS and not consumed:
            receipt = session.get(Receipt, event.receipt_id)
            assert receipt is not None
            event.state, event.error_code, event.lease_until = (
                "DEAD",
                "parse_retries_exhausted",
                None,
            )
            session.add(
                HealthInterval(
                    source_id=receipt.source_id,
                    fetch_id=receipt.fetch_id,
                    state="PARSER_DEGRADED",
                    reason="parse_retries_exhausted",
                    started_at=receipt.received_at,
                    ended_at=now,
                    recorded_at=now,
                    details={"event_id": event.id, "tries": event.tries},
                )
            )
            return None
        event.state = "PROCESSING"
        event.tries += 1
        event.fence += 1
        event.lease_until = now + timedelta(seconds=lease_seconds)
        return event.id, event.fence


def _envelope(store: LocalObjectStore, artifact: Artifact, policy: Policy) -> list[Any]:
    if artifact.size > policy.max_bytes:
        raise InvalidEnvelope("artifact_size_invalid")
    try:
        data = store.read(artifact.key)
    except (OSError, ValueError) as exc:
        raise InvalidEnvelope("artifact_missing_or_corrupt") from exc
    if hashlib.sha256(data).hexdigest() != artifact.sha256:
        raise InvalidEnvelope("artifact_missing_or_corrupt")
    if len(data) != artifact.size or len(data) > policy.max_bytes:
        raise InvalidEnvelope("artifact_size_invalid")
    try:
        envelope = json.loads(data)
    except (ValueError, UnicodeDecodeError, RecursionError) as exc:
        raise InvalidEnvelope("metadata_envelope_invalid") from exc
    if (
        not isinstance(envelope, dict)
        or set(envelope) != {"schema_version", "items"}
        or envelope["schema_version"] != SCHEMA_VERSION
        or not isinstance(envelope["items"], list)
        or len(envelope["items"]) > policy.max_items
    ):
        raise InvalidEnvelope("metadata_envelope_invalid")
    return list(envelope["items"])


def _observe(
    session: Session,
    receipt: Receipt,
    source: Source,
    policy: Policy,
    ordinal: int,
    value: Any,
    now: datetime,
) -> None:
    if (
        not isinstance(value, dict)
        or not set(value) <= set(policy.allowed_fields) & SUPPORTED_FIELDS
        or any(
            not isinstance(item, str) or len(item) > policy.max_text_chars or "\x00" in item
            for item in value.values()
        )
    ):
        raise InvalidEnvelope("item_schema_invalid")
    item: dict[str, str] = value
    try:
        for text in item.values():
            text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise InvalidEnvelope("item_schema_invalid") from exc
    timestamp, precision = published_time(item.get("published_at"))
    identity, confidence = occurrence_identity(item, timestamp, precision)
    occurrence = session.scalar(
        select(Occurrence).where(
            Occurrence.publisher_id == policy.publisher_id,
            Occurrence.identity_key == identity,
            Occurrence.identity_version == IDENTITY_VERSION,
        )
    )
    if occurrence is None:
        occurrence = Occurrence(
            publisher_id=policy.publisher_id,
            identity_key=identity,
            identity_version=IDENTITY_VERSION,
            identity_confidence=confidence,
        )
        session.add(occurrence)
        session.flush()
    fingerprint = hashlib.sha256(_json_bytes(item)).hexdigest()
    revision = session.scalar(
        select(Revision).where(
            Revision.occurrence_id == occurrence.id,
            Revision.fingerprint == fingerprint,
            Revision.parser_version == PARSER_VERSION,
            Revision.normalization_version == NORMALIZATION_VERSION,
            Revision.schema_version == SCHEMA_VERSION,
        )
    )
    if revision is None:
        revision = Revision(
            occurrence_id=occurrence.id,
            fingerprint=fingerprint,
            fields=item,
            published_at=timestamp,
            published_precision=precision,
            parser_version=PARSER_VERSION,
            normalization_version=NORMALIZATION_VERSION,
            schema_version=SCHEMA_VERSION,
            recorded_at=now,
        )
        session.add(revision)
        session.flush()
    session.add(
        Observation(
            receipt_id=receipt.id,
            source_id=receipt.source_id,
            feed_id=source.feed_id,
            ordinal=ordinal,
            occurrence_id=occurrence.id,
            revision_id=revision.id,
            parser_version=PARSER_VERSION,
            received_at=receipt.received_at,
            recorded_at=now,
        )
    )


def _failure(engine: Engine, event_id: str, fence: int, code: str, blocked: bool) -> None:
    with transaction(engine) as session:
        evidence_lock(session)
        event = session.get(Outbox, event_id, with_for_update=True)
        if event is None:
            raise StaleLease("parse event no longer exists")
        now = db_now(session)
        _leased(event, fence, now)
        receipt = session.get(Receipt, event.receipt_id)
        assert receipt is not None
        event.error_code = code
        event.state = "DEAD" if blocked or event.tries >= MAX_PARSE_ATTEMPTS else "RETRY"
        # Stable jitter makes retry scheduling testable while spreading simultaneous failures.
        jitter = (
            0.5
            + int(hashlib.sha256(f"{event.id}:{event.tries}".encode()).hexdigest()[:8], 16) / 2**33
        )
        event.due_at = now + timedelta(seconds=min(60, 2**event.tries) * jitter)
        event.lease_until = None
        session.add(
            HealthInterval(
                source_id=receipt.source_id,
                fetch_id=receipt.fetch_id,
                state="RIGHTS_BLOCKED" if blocked else "PARSER_DEGRADED",
                reason=code,
                started_at=receipt.received_at,
                ended_at=now,
                recorded_at=now,
                details={"event_id": event.id, "tries": event.tries, "queue_state": event.state},
            )
        )


def process_parse(
    engine: Engine,
    store: LocalObjectStore,
    event_id: str,
    fence: int,
    *,
    fault: Fault | None = None,
) -> None:
    receipt_id: str
    try:
        with transaction(engine) as session:
            evidence_lock(session)
            event = session.get(Outbox, event_id, with_for_update=True)
            if event is None:
                raise StaleLease("parse event no longer exists")
            now = db_now(session)
            _leased(event, fence, now)
            receipt = session.get(Receipt, event.receipt_id)
            assert receipt is not None
            receipt_id = receipt.id
            if session.get(Consumption, (CONSUMER, event.id, event.version)) is None:
                policy = require_policy(session, receipt.source_id, receipt.policy_id)
                if not policy.derived_allowed:
                    raise PolicyBlocked("derived metadata processing is not permitted")
                if event.version != PARSER_VERSION or receipt.schema_version != SCHEMA_VERSION:
                    raise InvalidEnvelope("unsupported_parser_or_schema_version")
                source = session.get(Source, receipt.source_id)
                artifact = session.get(Artifact, receipt.artifact_key)
                if source is None or artifact is None or artifact.expires_at <= now:
                    raise InvalidEnvelope("artifact_unavailable_or_expired")
                items = _envelope(store, artifact, policy)
                rejected: dict[str, int] = {}
                for ordinal, item in enumerate(items):
                    try:
                        _observe(session, receipt, source, policy, ordinal, item, now)
                    except InvalidEnvelope as exc:
                        code = str(exc)
                        rejected[code] = rejected.get(code, 0) + 1
                if rejected:
                    session.add(
                        HealthInterval(
                            source_id=receipt.source_id,
                            fetch_id=receipt.fetch_id,
                            state="PARSER_DEGRADED",
                            reason="parse_rejected_items",
                            started_at=receipt.received_at,
                            ended_at=now,
                            recorded_at=now,
                            details={
                                "receipt_id": receipt.id,
                                "rejected": rejected,
                                "accepted_count": len(items) - sum(rejected.values()),
                            },
                        )
                    )
                session.add(
                    Consumption(
                        consumer=CONSUMER,
                        event_id=event.id,
                        version=event.version,
                        recorded_at=now,
                    )
                )
            if fault is not None:
                fault("before_effect_commit")
            # The lock is held through commit. Recheck after parsing and any blocked waits.
            _leased(event, fence, db_now(session))
    except PolicyBlocked:
        _failure(engine, event_id, fence, "derived_policy_blocked", True)
        return
    except (InvalidEnvelope, OSError) as exc:
        code = str(exc) if isinstance(exc, InvalidEnvelope) else "artifact_io_failure"
        _failure(engine, event_id, fence, code, False)
        return
    if fault is not None:
        fault("after_effect_commit")
    # This is a separate committed witness, never the transaction-start timestamp.
    mark_available(engine, "parsed_receipt", receipt_id)
    # Delivery acknowledgment is deliberately separate from logical effects.
    with transaction(engine) as session:
        event = session.get(Outbox, event_id, with_for_update=True)
        if event is None:
            raise StaleLease("parse event no longer exists")
        _leased(event, fence, db_now(session))
        event.state, event.lease_until, event.error_code = "DONE", None, None


def run_parser_once(engine: Engine, store: LocalObjectStore, lease_seconds: int = 30) -> bool:
    claimed = claim_parse(engine, lease_seconds)
    if claimed is None:
        return False
    process_parse(engine, store, *claimed)
    return True
