import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, func, select, text

from pulse.capture import capture, claim_capture, schedule
from pulse.collection import CollectionResponse, FixtureAdapter
from pulse.config import Settings
from pulse.db import db_now, transaction
from pulse.errors import StaleLease
from pulse.models import (
    Artifact,
    Attempt,
    Audit,
    Availability,
    HealthInterval,
    Observation,
    OriginBudget,
    Outbox,
    Receipt,
    Source,
)
from pulse.policy import revoke_policy
from pulse.reconcile import reconcile
from pulse.worker import run_parser_once
from tests.helpers import approve, ingest, xml

pytestmark = pytest.mark.postgres


class Crash(BaseException):
    pass


def crash_at(stage: str):
    def fail(actual: str) -> None:
        if actual == stage:
            raise Crash(stage)

    return fail


def count(engine: Engine, model) -> int:
    with transaction(engine) as session:
        return session.scalar(select(func.count()).select_from(model))


def claimed(engine: Engine, settings: Settings) -> tuple[str, int]:
    schedule(engine)
    result = claim_capture(engine, settings)
    assert result is not None
    return result


def adapter(body: bytes | None = None, status: int = 200) -> FixtureAdapter:
    return FixtureAdapter(
        lambda request: CollectionResponse(
            status, body if body is not None else xml(), datetime.now(UTC)
        )
    )


def expire(engine: Engine, fetch_id: str) -> None:
    with transaction(engine) as session:
        attempt = session.get(Attempt, fetch_id)
        attempt.lease_until = db_now(session) - timedelta(seconds=1)


def test_object_crash_unacknowledged_orphan_recovery(engine, settings, store):
    approve(engine)
    claim = claimed(engine, settings)
    with pytest.raises(Crash):
        capture(engine, settings, store, adapter(), *claim, fault=crash_at("after_object_write"))
    assert count(engine, Receipt) == count(engine, Outbox) == 0
    assert len(store.keys()) == 1
    expire(engine, claim[0])
    result = reconcile(engine, store)
    assert result["orphans_deleted"] == result["expired_attempts"] == 1
    assert store.keys() == []
    retried = claim_capture(engine, settings)
    assert retried == (claim[0], claim[1] + 1)
    assert capture(engine, settings, store, adapter(), *retried)
    assert count(engine, Receipt) == count(engine, Outbox) == 1


def test_receipt_crash_pending_outbox_recovers(engine, settings, store):
    approve(engine)
    claim = claimed(engine, settings)
    with pytest.raises(Crash):
        capture(engine, settings, store, adapter(), *claim, fault=crash_at("after_receipt_commit"))
    assert count(engine, Receipt) == count(engine, Outbox) == 1
    assert count(engine, Availability) == 0
    assert reconcile(engine, store)["witnesses_recovered"] == 1
    assert run_parser_once(engine, store)
    assert count(engine, Observation) == 1
    assert reconcile(engine, store)["witnesses_recovered"] == 0


def test_postcommit_io_error_never_compensates_committed_object(engine, settings, store):
    approve(engine)
    claim = claimed(engine, settings)

    def io_error(stage: str) -> None:
        if stage == "after_receipt_commit":
            raise OSError("simulated witness/ack I/O failure")

    with pytest.raises(OSError):
        capture(engine, settings, store, adapter(), *claim, fault=io_error)
    with transaction(engine) as session:
        receipt = session.scalar(select(Receipt))
        artifact = session.get(Artifact, receipt.artifact_key)
        assert store.verify(artifact.key, artifact.sha256)
        assert session.get(Attempt, claim[0]).state == "CAPTURED"
    assert reconcile(engine, store)["witnesses_recovered"] == 1


def test_expiry_during_receipt_transaction_rolls_back(engine, settings, store):
    approve(engine)
    settings.lease_seconds = 1
    claim = claimed(engine, settings)

    def pause(stage: str) -> None:
        if stage == "before_receipt_commit":
            time.sleep(1.05)

    with pytest.raises(StaleLease):
        capture(engine, settings, store, adapter(), *claim, fault=pause)
    assert count(engine, Receipt) == count(engine, Artifact) == count(engine, Outbox) == 0
    assert store.keys() == []


def test_stale_capture_cannot_write_after_new_fence(engine, settings, store):
    approve(engine)
    first = claimed(engine, settings)
    expire(engine, first[0])
    second = claim_capture(engine, settings)
    assert second[1] == first[1] + 1
    with pytest.raises(StaleLease):
        capture(engine, settings, store, adapter(), *first)
    assert count(engine, Receipt) == 0
    assert capture(engine, settings, store, adapter(), *second)


@pytest.mark.parametrize(
    "policy_changes",
    [
        {"state": "UNKNOWN"},
        {"state": "REVOKED"},
        {"metadata_allowed": False},
        {
            "expires_at": datetime.now(UTC) - timedelta(seconds=1),
            "effective_from": datetime.now(UTC) - timedelta(days=1),
        },
    ],
)
def test_unapproved_never_collects(engine, settings, store, policy_changes):
    approve(engine, **policy_changes)
    calls = []
    schedule(engine)
    assert claim_capture(engine, settings) is None
    assert not calls and not store.keys() and count(engine, Receipt) == 0
    assert count(engine, HealthInterval) > 0


def test_live_disabled_before_adapter_or_network(engine, settings, store):
    approve(
        engine,
        scope="observed_metadata",
        endpoint="https://example.org/feed",
        allowed_host="example.org",
    )
    claim = claimed(engine, settings)
    calls = []
    collector = FixtureAdapter(lambda request: calls.append(request))
    assert capture(engine, settings, store, collector, *claim) is None
    assert calls == [] and store.keys() == [] and count(engine, Receipt) == 0


@pytest.mark.parametrize("revocation_stage", ["after_fetch", "after_object_write"])
def test_revocation_during_collection_erases_unaccepted_payload(
    engine, settings, store, revocation_stage
):
    approve(engine)
    claim = claimed(engine, settings)

    def revoke(stage: str) -> None:
        if stage == revocation_stage:
            revoke_policy(engine, "source-one", "test-steward")

    assert capture(engine, settings, store, adapter(), *claim, fault=revoke) is None
    assert count(engine, Receipt) == count(engine, Artifact) == count(engine, Outbox) == 0
    assert store.keys() == []
    with transaction(engine) as session:
        assert session.get(Attempt, claim[0]).error_code == "RIGHTS_BLOCKED"


def test_304_missing_cache_persists_unconditional_retry(engine, settings, store):
    approve(engine)
    receipt_id = ingest(engine, store, xml())
    with transaction(engine) as session:
        source = session.get(Source, "source-one")
        key = source.cache_key
        source.next_due_at = db_now(session)
    store.delete(key)
    claim = claimed(engine, settings)
    assert capture(engine, settings, store, adapter(b"", 304), *claim) is None
    with transaction(engine) as session:
        source = session.get(Source, "source-one")
        assert source.cache_key is source.etag is source.last_modified is None
        attempt = session.get(Attempt, claim[0])
        assert attempt.error_code == "CACHE_MISSING" and attempt.state == "PENDING"
        attempt.due_at = db_now(session)
        session.get(OriginBudget, attempt.rate_scope).next_allowed_at = db_now(session)
        assert session.get(Receipt, receipt_id)
    request_headers = []
    collector = FixtureAdapter(
        lambda request: (
            request_headers.append(request.etag)
            or CollectionResponse(200, xml(), datetime.now(UTC))
        )
    )
    assert capture(engine, settings, store, collector, *claim_capture(engine, settings))
    assert request_headers == [None] and count(engine, Receipt) == 2


def test_parallel_throttles_do_not_starve_healthy_origin(engine, settings, store):
    for source in ["bad-429", "bad-503", "healthy"]:
        approve(engine, source_id=source, publisher=source, rate_scope=source)
    schedule(engine)
    with ThreadPoolExecutor(max_workers=3) as executor:
        claims = list(executor.map(lambda _: claim_capture(engine, settings), range(3)))
    assert len({claim[0] for claim in claims}) == 3

    def run(claim):
        with transaction(engine) as session:
            source_id = session.get(Attempt, claim[0]).source_id
        status = {"bad-429": 429, "bad-503": 503, "healthy": 200}[source_id]
        response = FixtureAdapter(
            lambda request: CollectionResponse(
                status,
                xml() if status == 200 else b"private response body",
                datetime.now(UTC),
                retry_after="60",
            )
        )
        return capture(engine, settings, store, response, *claim)

    with ThreadPoolExecutor(max_workers=3) as executor:
        outputs = list(executor.map(run, claims))
    assert sum(value is not None for value in outputs) == 1
    assert run_parser_once(engine, store) and count(engine, Observation) == 1
    with transaction(engine) as session:
        budgets = session.scalars(
            select(OriginBudget).where(OriginBudget.id.in_(["bad-429", "bad-503"]))
        ).all()
        assert all(b.next_allowed_at > db_now(session) for b in budgets)
        failures = session.scalars(
            select(HealthInterval).where(HealthInterval.state == "RATE_LIMITED")
        ).all()
        assert {item.reason for item in failures} == {"HTTP_429", "HTTP_503"}
    assert b"private response body" not in b"".join(store.read(key) for key in store.keys())
    # Persisted throttle survives constructing a new settings/worker process.
    assert claim_capture(engine, Settings(database_url=settings.database_url)) is None


def test_shared_account_one_active_lease(engine, settings):
    approve(engine, "brand-a", rate_scope="shared-account")
    approve(engine, "brand-b", rate_scope="shared-account")
    schedule(engine)
    first = claim_capture(engine, settings)
    assert first
    assert claim_capture(engine, settings) is None


@pytest.mark.parametrize("body", [b"<rss>", b"<!DOCTYPE rss><rss/>", b"x" * 1048577])
def test_malformed_oversized_xml_has_safe_failure_evidence(engine, settings, store, body):
    approve(engine)
    assert capture(engine, settings, store, adapter(body), *claimed(engine, settings)) is None
    assert count(engine, Receipt) == count(engine, Artifact) == 0 and store.keys() == []
    with transaction(engine) as session:
        health = session.scalar(
            select(HealthInterval).where(HealthInterval.reason == "UNSAFE_REPRESENTATION")
        )
        assert health and "body" not in health.details


def test_only_permitted_fields_and_optional_values_persist(engine, settings, store):
    approve(engine, allowed_fields=["guid", "title"])
    receipt = ingest(
        engine,
        store,
        b"<rss><channel><item><guid>g</guid><title>T</title>"
        b"<description>private full body</description></item></channel></rss>",
    )
    assert run_parser_once(engine, store)
    with transaction(engine) as session:
        content = store.read(session.get(Receipt, receipt).artifact_key)
    item = json.loads(content)["items"][0]
    assert item == {"guid": "g", "title": "T"} and count(engine, Observation) == 1


def test_revocation_reconcile_erases_derived_content(engine, store):
    approve(engine)
    ingest(engine, store, xml())
    assert run_parser_once(engine, store)
    revoke_policy(engine, "source-one", "test-steward")
    assert reconcile(engine, store)["content_erased"] == 1
    assert store.keys() == [] and count(engine, Observation) == 0
    assert count(engine, Receipt) == 1 and count(engine, Audit) >= 3


def test_append_only_receipt_db_guard(engine, store):
    approve(engine)
    ingest(engine, store, xml())
    with pytest.raises(Exception, match="append-only evidence"):
        with transaction(engine) as session:
            session.execute(text("UPDATE fetch_receipts SET http_status=201"))
    with transaction(engine) as session:
        assert session.scalar(select(Receipt.http_status)) == 200


def test_pending_backpressure_bounded(engine):
    for source in ["one", "two", "three"]:
        approve(engine, source_id=source)
    assert len(schedule(engine, max_pending=2)) == 2
    assert schedule(engine, max_pending=2) == []
    assert count(engine, Attempt) == 2


def test_already_expired_response_not_persisted(engine, settings, store):
    approve(engine, retention_seconds=1)
    response = FixtureAdapter(
        lambda request: CollectionResponse(200, xml(), datetime.now(UTC) - timedelta(seconds=10))
    )
    assert capture(engine, settings, store, response, *claimed(engine, settings)) is None
    assert store.keys() == [] and count(engine, Receipt) == 0


def test_breaker_opens_and_allows_one_recovery_probe(engine, settings, store):
    approve(engine, "source-one", rate_scope="account")
    approve(engine, "source-two", rate_scope="account")
    schedule(engine)
    first = claim_capture(engine, settings)
    for _ in range(3):
        assert first
        assert capture(engine, settings, store, adapter(b"", 503), *first) is None
        with transaction(engine) as session:
            budget = session.get(OriginBudget, "account")
            attempt = session.get(Attempt, first[0])
            if budget.consecutive_failures == 3:
                assert budget.breaker_state == "OPEN" and budget.open_until > db_now(session)
                break
            budget.next_allowed_at = db_now(session)
            attempt.due_at = db_now(session)
        first = claim_capture(engine, settings)
    assert claim_capture(engine, settings) is None
    with transaction(engine) as session:
        budget = session.get(OriginBudget, "account")
        budget.open_until = budget.next_allowed_at = db_now(session) - timedelta(seconds=1)
        for attempt in session.scalars(select(Attempt).where(Attempt.state == "PENDING")):
            attempt.due_at = db_now(session)
    probe = claim_capture(engine, settings)
    assert probe and claim_capture(engine, settings) is None
    with transaction(engine) as session:
        assert session.get(OriginBudget, "account").breaker_state == "HALF_OPEN"
    assert capture(engine, settings, store, adapter(), *probe)
    with transaction(engine) as session:
        budget = session.get(OriginBudget, "account")
        assert budget.breaker_state == "CLOSED" and budget.consecutive_failures == 0


def test_reconcile_recovers_parser_postcommit_witness(engine, store):
    from pulse.worker import claim_parse, process_parse

    approve(engine)
    ingest(engine, store, xml())
    claim = claim_parse(engine)
    with pytest.raises(Crash):
        process_parse(engine, store, *claim, fault=crash_at("after_effect_commit"))
    assert count(engine, Observation) == 1
    assert reconcile(engine, store)["witnesses_recovered"] == 1
    with transaction(engine) as session:
        assert session.scalar(select(Availability).where(Availability.kind == "parsed_receipt"))


def test_nonparser_consumption_cannot_establish_availability(engine, store):
    from pulse.availability import mark_available
    from pulse.models import Consumption

    approve(engine)
    receipt_id = ingest(engine, store, xml())
    with transaction(engine) as session:
        event = session.scalar(select(Outbox))
        session.add(
            Consumption(
                consumer="unrelated-consumer",
                event_id=event.id,
                version=event.version,
                recorded_at=db_now(session),
            )
        )
    with pytest.raises(ValueError, match="Parsing is not committed"):
        mark_available(engine, "parsed_receipt", receipt_id)


def test_orphan_retention_deadline_overrides_active_lease(engine, settings, store):
    approve(engine, retention_seconds=1)
    claim = claimed(engine, settings)
    with pytest.raises(Crash):
        capture(engine, settings, store, adapter(), *claim, fault=crash_at("after_object_write"))
    assert reconcile(engine, store)["orphans_deleted"] == 0  # Active and still permitted.
    time.sleep(1.05)
    with transaction(engine) as session:
        assert session.get(Attempt, claim[0]).lease_until > db_now(session)
    assert reconcile(engine, store)["orphans_deleted"] == 1
    assert store.keys() == [] and count(engine, Receipt) == 0


def test_interrupted_staging_write_reconciled(engine, settings, store):
    from pathlib import Path

    approve(engine)
    claim = claimed(engine, settings)
    with pytest.raises(Crash):
        capture(engine, settings, store, adapter(), *claim, fault=crash_at("after_object_write"))
    # A process killed inside object installation can leave its permitted staging bytes.
    key = store.keys()[0]
    staging = str(Path(key).parent / ".put-test1234")
    (store.root / staging).write_bytes(store.read(key))
    expire(engine, claim[0])
    assert reconcile(engine, store)["orphans_deleted"] == 2
    assert store.keys() == []


def test_long_throttle_cannot_fill_backlog_and_starve_new_healthy_source(engine, settings, store):
    approve(engine, "bad", poll_seconds=1)
    schedule(engine, max_pending=2)
    claim = claim_capture(engine, settings)
    collector = FixtureAdapter(
        lambda request: CollectionResponse(429, b"", datetime.now(UTC), retry_after="604800")
    )
    assert capture(engine, settings, store, collector, *claim) is None
    for _ in range(3):
        with transaction(engine) as session:
            session.get(Source, "bad").next_due_at = db_now(session)
        assert schedule(engine, max_pending=2) == []
    approve(engine, "healthy")
    assert len(schedule(engine, max_pending=2)) == 1
    healthy_claim = claim_capture(engine, settings)
    assert healthy_claim
    with transaction(engine) as session:
        assert session.get(Attempt, healthy_claim[0]).source_id == "healthy"
    assert capture(engine, settings, store, adapter(), *healthy_claim)
    assert count(engine, Attempt) == 2
