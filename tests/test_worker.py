import hashlib
import json
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from hypothesis import given
from hypothesis import strategies as st
from sqlalchemy import Engine, func, select

from pulse.db import db_now, transaction
from pulse.errors import StaleLease
from pulse.models import (
    Artifact,
    Attempt,
    Availability,
    Consumption,
    HealthInterval,
    Observation,
    Occurrence,
    OriginBudget,
    Outbox,
    Policy,
    Receipt,
    Revision,
    Source,
)
from pulse.objects import LocalObjectStore
from pulse.policy import revoke_policy
from pulse.worker import (
    MAX_PARSE_ATTEMPTS,
    PARSER_VERSION,
    claim_parse,
    occurrence_identity,
    process_parse,
    published_time,
    run_parser_once,
)


class Crash(BaseException):
    pass


def _source(engine: Engine, *, publisher: str = "fixture-publisher") -> tuple[str, str]:
    source_id, policy_id = str(uuid4()), str(uuid4())
    with transaction(engine) as session:
        now = db_now(session)
        session.add(
            Source(
                id=source_id,
                feed_id=f"feed-{source_id}",
                current_policy_id=None,
                next_due_at=now,
            )
        )
        session.flush()
        session.add(
            Policy(
                id=policy_id,
                source_id=source_id,
                version=1,
                publisher_id=publisher,
                owner_id=f"owner-{publisher}",
                endpoint=f"fixture://{source_id}/feed",
                allowed_host=source_id,
                scope="offline_fixture",
                state="APPROVED",
                effective_from=now - timedelta(days=1),
                expires_at=now + timedelta(days=1),
                approved_at=now,
                approved_by="fixture-test",
                metadata_allowed=True,
                derived_allowed=True,
                link_display_allowed=True,
                allowed_fields=["guid", "url", "title", "published_at", "published_precision"],
                retention_seconds=86400,
                rate_scope=f"origin-{source_id}",
            )
        )
        session.add(OriginBudget(id=f"origin-{source_id}", next_allowed_at=now))
        session.flush()
        source = session.get(Source, source_id)
        assert source is not None
        source.current_policy_id = policy_id
    return source_id, policy_id


def _capture(
    engine: Engine,
    store: LocalObjectStore,
    source: tuple[str, str],
    items: Any,
    *,
    received_offset: int = 0,
    status: int = 200,
    artifact_key: str | None = None,
    raw: bytes | None = None,
) -> tuple[str, str]:
    source_id, policy_id = source
    fetch_id, receipt_id, event_id = str(uuid4()), str(uuid4()), str(uuid4())
    data = (
        raw
        if raw is not None
        else json.dumps(
            {"schema_version": "metadata-envelope-v1", "items": items},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    )
    key = artifact_key or store.put(policy_id, fetch_id, data)
    with transaction(engine) as session:
        now = db_now(session)
        session.add(
            Attempt(
                id=fetch_id,
                source_id=source_id,
                policy_id=policy_id,
                rate_scope=f"origin-{source_id}",
                schedule_key=fetch_id,
                scheduled_at=now,
                due_at=now,
                state="DONE",
                tries=1,
                fence=1,
            )
        )
        if artifact_key is None:
            session.add(
                Artifact(
                    key=key,
                    policy_id=policy_id,
                    sha256=hashlib.sha256(data).hexdigest(),
                    size=len(data),
                    created_at=now,
                    expires_at=now + timedelta(days=1),
                )
            )
        session.flush()
        session.add(
            Receipt(
                id=receipt_id,
                fetch_id=fetch_id,
                source_id=source_id,
                policy_id=policy_id,
                artifact_key=key,
                http_status=status,
                received_at=now + timedelta(seconds=received_offset),
                recorded_at=now,
            )
        )
        session.flush()
        session.add(
            Outbox(
                id=event_id,
                topic="parse_requested",
                receipt_id=receipt_id,
                version=PARSER_VERSION,
                due_at=now,
            )
        )
    return receipt_id, event_id


def _item(
    title: str = "عنوان عربي", *, guid: str = "id-1", published: str = "2026-10-12T10:20:30+03:00"
) -> dict[str, str]:
    return {
        "guid": guid,
        "url": "https://fixture.example/reused",
        "title": title,
        "published_at": published,
    }


def _counts(engine: Engine) -> tuple[int, int, int, int]:
    with transaction(engine) as session:
        return tuple(
            int(session.scalar(select(func.count()).select_from(model)) or 0)
            for model in (Occurrence, Revision, Observation, Consumption)
        )  # type: ignore[return-value]


def _expire(engine: Engine, event_id: str) -> None:
    with transaction(engine) as session:
        event = session.get(Outbox, event_id)
        assert event is not None
        event.lease_until = db_now(session) - timedelta(seconds=1)


@pytest.mark.parametrize(
    ("raw", "expected", "precision"),
    [
        (None, None, "unknown"),
        ("bad timestamp", None, "invalid"),
        ("2026-10-12", None, "date"),
        ("2026-10-12T10:20:30", None, "timezone_unknown"),
        ("Mon, 12 Oct 2026 10:20:30 -0000", None, "timezone_unknown"),
        ("2026-10-12T10:20:30+03:00", "2026-10-12T07:20:30+00:00", "second"),
        ("Mon, 12 Oct 2026 10:20:30 +0300", "2026-10-12T07:20:30+00:00", "second"),
        ("Mon, 12 Oct 2026 10:20 +0300", "2026-10-12T07:20:00+00:00", "minute"),
        ("2026-10-12T10:20Z", "2026-10-12T10:20:00+00:00", "minute"),
        ("2026-10-12T10:20:30.123Z", "2026-10-12T10:20:30.123000+00:00", "fractional_3"),
        ("2026-10-12T10:20:30.123456789Z", None, "unsupported_precision"),
    ],
)
def test_publisher_timestamps_never_infer_an_unknown_timezone(
    raw: str | None,
    expected: str | None,
    precision: str,
) -> None:
    parsed, actual_precision = published_time(raw)
    assert (parsed.isoformat() if parsed else None) == expected
    assert actual_precision == precision


@given(st.text(), st.text())
def test_publication_identity_is_independent_of_title_edits(first: str, second: str) -> None:
    stamp = datetime(2026, 10, 12, tzinfo=UTC)
    assert occurrence_identity(_item(first), stamp, "second") == occurrence_identity(
        _item(second),
        stamp,
        "second",
    )


@pytest.mark.postgres
def test_effect_commit_before_ack_is_recovered_without_duplicate_effects(
    engine: Engine,
    store: LocalObjectStore,
) -> None:
    source = _source(engine)
    receipt_id, event_id = _capture(engine, store, source, [_item()])
    claimed = claim_parse(engine)
    assert claimed is not None and claimed[0] == event_id

    def crash(stage: str) -> None:
        if stage == "after_effect_commit":
            raise Crash()

    with pytest.raises(Crash):
        process_parse(engine, store, *claimed, fault=crash)
    assert _counts(engine) == (1, 1, 1, 1)
    with transaction(engine) as session:
        event = session.get(Outbox, event_id)
        assert event is not None and event.state == "PROCESSING"
        assert session.scalar(select(func.count()).select_from(Availability)) == 0
    _expire(engine, event_id)
    redelivery = claim_parse(engine)
    assert redelivery is not None and redelivery[1] > claimed[1]
    process_parse(engine, store, *redelivery)
    assert _counts(engine) == (1, 1, 1, 1)
    with transaction(engine) as session:
        event = session.get(Outbox, event_id)
        assert event is not None and event.state == "DONE"
        witness = session.scalar(
            select(Availability).where(
                Availability.kind == "parsed_receipt",
                Availability.entity_id == receipt_id,
            )
        )
        assert witness is not None
        observation = session.scalar(select(Observation))
        assert observation is not None and witness.postcommit_observed_at >= observation.recorded_at
    with pytest.raises(StaleLease):
        process_parse(engine, store, *claimed)
    assert _counts(engine) == (1, 1, 1, 1)


@pytest.mark.postgres
def test_crash_before_effect_commit_leaves_no_partial_observation(
    engine: Engine,
    store: LocalObjectStore,
) -> None:
    source = _source(engine)
    _, event_id = _capture(engine, store, source, [_item(), _item("edit")])
    claimed = claim_parse(engine)
    assert claimed is not None

    def crash(stage: str) -> None:
        if stage == "before_effect_commit":
            raise Crash()

    with pytest.raises(Crash):
        process_parse(engine, store, *claimed, fault=crash)
    assert _counts(engine) == (0, 0, 0, 0)
    _expire(engine, event_id)
    assert run_parser_once(engine, store)
    assert _counts(engine) == (1, 2, 2, 1)


@pytest.mark.postgres
def test_stale_fence_cannot_commit_and_current_worker_can(
    engine: Engine,
    store: LocalObjectStore,
) -> None:
    _, event_id = _capture(engine, store, _source(engine), [_item()])
    old = claim_parse(engine)
    assert old is not None
    _expire(engine, event_id)
    current = claim_parse(engine)
    assert current is not None and current[1] > old[1]
    with pytest.raises(StaleLease):
        process_parse(engine, store, *old)
    assert _counts(engine) == (0, 0, 0, 0)
    process_parse(engine, store, *current)
    assert _counts(engine) == (1, 1, 1, 1)


@pytest.mark.postgres
def test_lease_expiration_during_effects_rolls_back_in_same_transaction(
    engine: Engine,
    store: LocalObjectStore,
) -> None:
    _capture(engine, store, _source(engine), [_item()])
    claimed = claim_parse(engine, lease_seconds=1)
    assert claimed is not None

    def hold(stage: str) -> None:
        if stage == "before_effect_commit":
            time.sleep(1.05)

    with pytest.raises(StaleLease):
        process_parse(engine, store, *claimed, fault=hold)
    assert _counts(engine) == (0, 0, 0, 0)


@pytest.mark.postgres
def test_out_of_order_processing_preserves_a_b_a_receipt_history(
    engine: Engine,
    store: LocalObjectStore,
) -> None:
    source = _source(engine)
    receipts = [
        _capture(engine, store, source, [_item("A")], received_offset=-30),
        _capture(engine, store, source, [_item("B")], received_offset=-20),
        _capture(engine, store, source, [_item("A")], received_offset=-10),
    ]
    claims = [claim_parse(engine) for _ in receipts]
    assert all(claim is not None for claim in claims)
    # The second receipt becomes usable first; processing time is not source chronology.
    for index in [1, 0, 2]:
        claim = claims[index]
        assert claim is not None
        process_parse(engine, store, *claim)
    assert _counts(engine) == (1, 2, 3, 3)
    with transaction(engine) as session:
        observations = list(session.scalars(select(Observation).order_by(Observation.received_at)))
        assert [observation.receipt_id for observation in observations] == [
            receipt_id for receipt_id, _ in receipts
        ]
        assert observations[0].revision_id == observations[2].revision_id
        assert observations[0].revision_id != observations[1].revision_id
        assert observations[1].recorded_at < observations[0].recorded_at
        assert [
            session.get(Revision, observation.revision_id).fields["title"]
            for observation in observations
        ] == ["A", "B", "A"]  # type: ignore[union-attr]


@pytest.mark.postgres
def test_guid_time_identity_separates_reused_urls_and_syndicated_publishers(
    engine: Engine,
    store: LocalObjectStore,
) -> None:
    first, second = _source(engine), _source(engine, publisher="other-publisher")
    for source, item in [
        (first, _item("A")),
        (first, _item("edited A")),
        (first, _item("A", guid="id-2")),
        (first, _item("A", published="2026-10-12T11:20:30+03:00")),
        (second, _item("A")),
    ]:
        _capture(engine, store, source, [item])
        assert run_parser_once(engine, store)
    assert _counts(engine) == (4, 5, 5, 5)
    with transaction(engine) as session:
        assert {row.identity_confidence for row in session.scalars(select(Occurrence))} == {
            "guid_timestamp",
        }


@pytest.mark.postgres
def test_url_only_unknown_timestamp_is_explicitly_ambiguous_and_raw_is_preserved(
    engine: Engine,
    store: LocalObjectStore,
) -> None:
    item = {"url": "https://FIXTURE.example:443/reused#part", "published_at": "unknown"}
    _capture(engine, store, _source(engine), [item])
    assert run_parser_once(engine, store)
    with transaction(engine) as session:
        occurrence, revision = session.scalar(select(Occurrence)), session.scalar(select(Revision))
        assert occurrence is not None and occurrence.identity_confidence == "url_only_ambiguous"
        assert revision is not None and revision.published_at is None
        assert revision.published_precision == "invalid" and revision.fields == item


@pytest.mark.postgres
def test_304_reuses_revision_and_occurrence_but_adds_receipt_provenance(
    engine: Engine,
    store: LocalObjectStore,
) -> None:
    source = _source(engine)
    receipt_id, _ = _capture(engine, store, source, [_item()])
    assert run_parser_once(engine, store)
    with transaction(engine) as session:
        receipt = session.get(Receipt, receipt_id)
        assert receipt is not None
        key = receipt.artifact_key
    _capture(engine, store, source, [_item()], status=304, artifact_key=key)
    assert run_parser_once(engine, store)
    assert _counts(engine) == (1, 1, 2, 2)


@pytest.mark.postgres
def test_duplicate_items_keep_distinct_ordinals_without_duplicate_revision(
    engine: Engine,
    store: LocalObjectStore,
) -> None:
    _capture(engine, store, _source(engine), [_item(), _item()])
    assert run_parser_once(engine, store)
    assert _counts(engine) == (1, 1, 2, 1)
    with transaction(engine) as session:
        assert set(session.scalars(select(Observation.ordinal))) == {0, 1}


@pytest.mark.postgres
def test_malformed_artifact_has_bounded_persisted_retries_and_failure_evidence(
    engine: Engine,
    store: LocalObjectStore,
) -> None:
    _, event_id = _capture(engine, store, _source(engine), [], raw=b"{bad-json")
    for index in range(MAX_PARSE_ATTEMPTS):
        assert run_parser_once(engine, store)
        with transaction(engine) as session:
            event = session.get(Outbox, event_id)
            assert event is not None and event.tries == index + 1
            assert event.error_code == "metadata_envelope_invalid"
            assert event.state == ("DEAD" if index == MAX_PARSE_ATTEMPTS - 1 else "RETRY")
            if event.state == "RETRY":
                assert event.due_at > db_now(session)
                event.due_at = db_now(session) - timedelta(seconds=1)
    assert not run_parser_once(engine, store)
    assert _counts(engine) == (0, 0, 0, 0)
    with transaction(engine) as session:
        failures = list(session.scalars(select(HealthInterval)))
        assert len(failures) == MAX_PARSE_ATTEMPTS
        assert all(failure.state == "PARSER_DEGRADED" for failure in failures)


@pytest.mark.postgres
def test_rejected_item_is_diagnostic_while_valid_item_retains_its_original_ordinal(
    engine: Engine,
    store: LocalObjectStore,
) -> None:
    _capture(engine, store, _source(engine), [{"title": "no identity"}, _item()])
    assert run_parser_once(engine, store)
    assert _counts(engine) == (1, 1, 1, 1)
    with transaction(engine) as session:
        assert session.scalar(select(Observation.ordinal)) == 1
        diagnostic = session.scalar(select(HealthInterval))
        assert diagnostic is not None
        assert diagnostic.details["rejected"] == {"item_identity_missing": 1}


@pytest.mark.postgres
def test_revoked_policy_blocks_parse_and_persists_rights_failure(
    engine: Engine,
    store: LocalObjectStore,
) -> None:
    source = _source(engine)
    _, event_id = _capture(engine, store, source, [_item()])
    revoke_policy(engine, source[0], "fixture-test")
    assert run_parser_once(engine, store)
    assert _counts(engine) == (0, 0, 0, 0)
    with transaction(engine) as session:
        event = session.get(Outbox, event_id)
        assert event is not None and event.state == "DEAD"
        failure = session.scalar(select(HealthInterval))
        assert failure is not None and failure.state == "RIGHTS_BLOCKED"


@pytest.mark.postgres
def test_skip_locked_claim_keeps_independent_work_claimable(
    engine: Engine,
    store: LocalObjectStore,
) -> None:
    source = _source(engine)
    _, first_id = _capture(engine, store, source, [_item()])
    _, second_id = _capture(engine, store, source, [_item(guid="id-2")])
    with transaction(engine) as locked:
        assert locked.get(Outbox, first_id, with_for_update=True) is not None
        claim = claim_parse(engine)
        assert claim is not None and claim[0] == second_id
    other = claim_parse(engine)
    assert other is not None and other[0] == first_id
