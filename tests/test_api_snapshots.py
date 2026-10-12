"""Real PostgreSQL API, availability and immutable-seal acceptance checks."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select

from pulse.api import create_app
from pulse.config import Settings
from pulse.db import db_now, evidence_lock, transaction
from pulse.models import (
    Artifact,
    Availability,
    HealthInterval,
    Observation,
    Policy,
    Receipt,
    Revision,
    Snapshot,
    SnapshotInvalidation,
)
from pulse.objects import LocalObjectStore
from pulse.policy import revoke_policy
from pulse.snapshots import SnapshotConflict, permitted_fields, seal_snapshot
from pulse.worker import run_parser_once
from tests.helpers import approve, ingest, xml

pytestmark = pytest.mark.postgres
READER = {"Authorization": "Bearer test-reader"}
AUDITOR = {"Authorization": "Bearer test-auditor"}


def parsed(
    engine: Engine,
    store: LocalObjectStore,
    body: bytes,
    *,
    received_at: datetime | None = None,
    source_id: str = "source-one",
) -> str:
    receipt_id = ingest(engine, store, body, received_at=received_at, source_id=source_id)
    assert run_parser_once(engine, store)
    return receipt_id


def test_public_health_auth_scope_and_readiness(settings: Settings, engine: Engine) -> None:
    client = TestClient(create_app(settings, engine))
    assert client.get("/health").json() == {"status": "alive"}
    assert client.get("/v1/observations").status_code == 401
    assert client.get("/v1/observations", headers=AUDITOR).status_code == 401
    assert (
        client.post("/v1/snapshots", headers=READER, json={"run_id": "denied"}).status_code == 401
    )
    ready = client.get("/ready", headers=READER)
    assert ready.status_code == 200
    assert ready.json()["migration"]
    disabled = TestClient(create_app(settings.model_copy(update={"api_token": ""}), engine))
    assert disabled.get("/v1/observations", headers=READER).status_code == 503
    overlapping = TestClient(
        create_app(settings.model_copy(update={"audit_token": settings.api_token}), engine)
    )
    assert overlapping.get("/v1/observations", headers=READER).status_code == 503
    assert (
        overlapping.post("/v1/snapshots", headers=READER, json={"run_id": "denied"}).status_code
        == 503
    )


def test_unavailable_vs_healthy_empty_and_open_gap(
    settings: Settings, engine: Engine, store: LocalObjectStore
) -> None:
    approve(engine)
    client = TestClient(create_app(settings, engine))
    initial = client.get("/v1/observations", headers=READER).json()
    assert initial["evidence_status"] == "EVIDENCE_UNAVAILABLE"
    assert initial["records"] == []
    parsed(engine, store, b"<rss><channel/></rss>")
    empty = client.get("/v1/observations", headers=READER).json()
    assert empty["evidence_status"] == "HEALTHY_EMPTY"
    assert empty["source_health"][0]["last_successful_checkpoint_at"]
    with transaction(engine) as session:
        evidence_lock(session)
        now = db_now(session)
        session.add(
            HealthInterval(
                source_id="source-one",
                state="UNAVAILABLE",
                reason="FIXTURE_OUTAGE",
                started_at=now - timedelta(minutes=1),
                ended_at=None,
                recorded_at=now,
                details={},
            )
        )
    # A later successful receipt cannot delete an earlier open missingness interval.
    parsed(engine, store, b"<rss><channel/></rss>")
    degraded = client.get("/v1/observations", headers=READER).json()
    assert degraded["evidence_status"] == "PARTIALLY_DEGRADED"
    assert degraded["records"] == []
    assert any(row["reason"] == "FIXTURE_OUTAGE" for row in degraded["source_gaps"])
    assert degraded["forecasts_available"] is False
    assert degraded["mode"] == "OBSERVED_ONLY"


def test_receipt_requires_committed_parse_availability(
    settings: Settings, engine: Engine, store: LocalObjectStore
) -> None:
    approve(engine)
    receipt_id = ingest(engine, store, xml())
    client = TestClient(create_app(settings, engine))
    waiting = client.get("/v1/observations", headers=READER).json()
    assert waiting["records"] == []
    assert waiting["evidence_status"] == "EVIDENCE_UNAVAILABLE"
    assert waiting["queue_lag"]["pending_count"] == 1
    assert run_parser_once(engine, store)
    available = client.get("/v1/observations", headers=READER).json()
    assert available["records"][0]["receipt_id"] == receipt_id
    assert available["records"][0]["processing_available_at"]
    with transaction(engine) as session:
        witness = session.scalar(
            select(Availability).where(
                Availability.kind == "parsed_receipt", Availability.entity_id == receipt_id
            )
        )
        observation = session.scalar(
            select(Observation).where(Observation.receipt_id == receipt_id)
        )
        assert witness is not None and observation is not None
        assert witness.postcommit_observed_at >= observation.recorded_at


def test_out_of_order_current_and_exact_frozen_first_seen(
    settings: Settings, engine: Engine, store: LocalObjectStore
) -> None:
    approve(engine)
    now = datetime.now(UTC)
    newer_receipt = parsed(engine, store, xml("newer"), received_at=now - timedelta(seconds=1))
    seal = seal_snapshot(engine, store, "out-of-order")
    frozen = seal.manifest
    older_receipt = parsed(engine, store, xml("older"), received_at=now - timedelta(seconds=10))
    client = TestClient(create_app(settings, engine))
    current = client.get("/v1/observations", headers=READER).json()["records"]
    assert len(current) == 1
    assert current[0]["receipt_id"] == newer_receipt
    assert current[0]["fields"]["title"] == "newer"
    assert datetime.fromisoformat(current[0]["first_seen_at"]) == now - timedelta(seconds=10)
    history = client.get("/v1/articles", headers=READER).json()["records"]
    assert {row["receipt_id"] for row in history} == {newer_receipt, older_receipt}
    replay = client.get(f"/v1/snapshots/{seal.id}", headers=AUDITOR).json()
    assert replay["manifest"] == frozen
    assert replay["sha256"] == hashlib.sha256(frozen.encode()).hexdigest()
    assert replay["payload"][0]["fields"]["title"] == "newer"
    assert datetime.fromisoformat(replay["payload"][0]["first_seen_at"]) == now - timedelta(
        seconds=1
    )
    # Same run retries return the exact original committed seal despite later inputs.
    repeated = seal_snapshot(engine, store, "out-of-order")
    assert repeated.id == seal.id and repeated.manifest == frozen
    with transaction(engine) as session:
        assert session.scalar(select(func.count()).select_from(Snapshot)) == 1


def test_a_b_a_revision_reuse_history_and_snapshot_invariance(
    settings: Settings, engine: Engine, store: LocalObjectStore
) -> None:
    approve(engine)
    parsed(engine, store, xml("A"))
    seal = seal_snapshot(engine, store, "before-edit")
    parsed(engine, store, xml("B"))
    parsed(engine, store, xml("A"))
    client = TestClient(create_app(settings, engine))
    records = client.get("/v1/articles", headers=READER).json()["records"]
    assert [row["fields"]["title"] for row in records] == ["A", "B", "A"]
    assert records[0]["revision_id"] == records[2]["revision_id"]
    assert records[0]["id"] != records[2]["id"]
    with transaction(engine) as session:
        assert session.scalar(select(func.count()).select_from(Revision)) == 2
        assert session.scalar(select(func.count()).select_from(Observation)) == 3
        persisted = session.get(Snapshot, seal.id)
        assert persisted is not None and persisted.manifest == seal.manifest
    manifest = json.loads(seal.manifest)
    assert all("title" not in row for row in manifest["observations"])
    assert "https://example.org/news/1" not in seal.manifest
    assert "fields" not in manifest["observations"][0]
    assert manifest["receipts"][0]["receipt_availability_id"] > 0
    assert manifest["visibility_witness"]
    assert manifest["availability_high_watermark"] > 0


def test_rights_field_filter_missing_artifact_and_revoked_replay(
    settings: Settings, engine: Engine, store: LocalObjectStore
) -> None:
    approve(engine, allowed_fields=["guid", "title"], link_display_allowed=False)
    receipt_id = parsed(engine, store, xml("restricted"))
    client = TestClient(create_app(settings, engine))
    record = client.get("/v1/observations", headers=READER).json()["records"][0]
    assert record["fields"] == {"guid": "article-1", "title": "restricted"}
    assert record["published_at"] is None
    sealed = seal_snapshot(engine, store, "rights")
    revoke_policy(engine, "source-one", "test-revocation")
    assert client.get("/v1/sources", headers=READER).json()["sources"] == []
    revoked = client.get("/v1/observations", headers=READER).json()
    assert revoked["evidence_status"] == "EVIDENCE_UNAVAILABLE"
    assert revoked["records"] == []
    replay = client.get(f"/v1/snapshots/{sealed.id}", headers=AUDITOR).json()
    assert replay["validity"] == "REPLAY_UNAVAILABLE"
    assert replay["payload"] is None
    assert "CURRENT_RIGHTS_UNAVAILABLE_OR_CHANGED" in replay["replay_unavailable_reasons"]
    assert replay["manifest"] == sealed.manifest
    with transaction(engine) as session:
        receipt = session.get(Receipt, receipt_id)
        assert receipt is not None
        artifact = session.get(Artifact, receipt.artifact_key)
        assert artifact is not None
        store.delete(artifact.key)
    missing = client.get(f"/v1/snapshots/{sealed.id}", headers=AUDITOR).json()
    assert missing["payload"] is None
    assert missing["manifest"] == sealed.manifest


@pytest.mark.parametrize(
    "guid, link_allowed, host, visible",
    [
        ("HTTPS://example.org/news/1", False, "example.org", False),
        ("HtTpS://example.org/news/1", False, "example.org", False),
        ("HTtp://example.org/news/1", False, "example.org", False),
        ("https://example.org/news/1", False, "example.org", False),
        ("http://example.org/news/1", False, "example.org", False),
        ("  HtTpS://example.org/news/1", False, "example.org", False),
        ("\tHTTPS://example.org/news/1", False, "example.org", False),
        ("\x00HTTPS://example.org/news/1", False, "example.org", False),
        ("HTTPS://example.org/news/1", True, "other.example.org", False),
        ("HTTPS://[broken", True, "example.org", False),
        ("http s://example.org/news/1", True, "example.org", False),
        ("ht\ttps://example.org/news/1", True, "example.org", False),
        ("ht\x00tps://example.org/news/1", True, "example.org", False),
        ("HTTPS://example.org/news/\n1", True, "example.org", False),
        (" https://example.org/news/1", True, "example.org", False),
        ("HTTP://example.org/news/1", True, "example.org", False),
        ("HTTPS://example.org@other.example.org/news/1", True, "example.org", False),
        ("HTTPS://example.org:444/news/1", True, "example.org", False),
        ("HTTPS://example.org/news/1", True, "example.org", True),
        ("HtTpS://example.org/news/1", True, "example.org", True),
        ("https://example.org/news/1", True, "example.org", True),
        ("article-1", False, "example.org", True),
        ("urn:publisher:article-1", False, "example.org", True),
        ("publisher-http:article-1", False, "example.org", True),
        ("article/HTTPS://example.org/news/1", False, "example.org", True),
        ("  opaque publisher GUID  ", False, "example.org", True),
    ],
)
def test_permitted_guid_url_classification_preserves_stored_identity(
    guid: str, link_allowed: bool, host: str, visible: bool
) -> None:
    revision = Revision(fields={"guid": guid, "title": "permitted metadata"})
    policy = Policy(
        allowed_fields=["guid", "title"],
        link_display_allowed=link_allowed,
        allowed_host=host,
    )
    fields = permitted_fields(revision, policy)
    expected = {"title": "permitted metadata"}
    if visible:
        expected["guid"] = guid
    assert fields == expected
    assert revision.fields == {"guid": guid, "title": "permitted metadata"}


@pytest.mark.parametrize(
    "scheme", ["HTTPS", "HtTpS", "HTtp", "https", "http", " HTTPS", "ht\ttps", "https "]
)
@pytest.mark.parametrize("restriction", ["no_links", "wrong_host"])
def test_url_guids_follow_link_rights_across_current_history_and_replay(
    settings: Settings,
    engine: Engine,
    store: LocalObjectStore,
    scheme: str,
    restriction: str,
) -> None:
    host = "example.org" if restriction == "no_links" else "other.example.org"
    approve(
        engine,
        allowed_fields=["guid", "title"],
        link_display_allowed=restriction != "no_links",
        allowed_host=host,
        endpoint=f"fixture://{host}/feed",
    )
    guid = f"{scheme}://example.org/news/1"
    stored_guid = guid.strip()  # Feed text normalization already removes outer whitespace.
    receipt_id = parsed(engine, store, xml("restricted URL GUID", guid=guid))
    sealed = seal_snapshot(engine, store, f"guid-{scheme}-{restriction}")
    client = TestClient(create_app(settings, engine))
    for route in ("/v1/observations", "/v1/articles"):
        response = client.get(route, headers=READER)
        assert response.status_code == 200
        assert response.json()["records"][0]["fields"] == {"title": "restricted URL GUID"}
        assert stored_guid not in response.text
    replay = client.get(f"/v1/snapshots/{sealed.id}", headers=AUDITOR)
    assert replay.status_code == 200
    assert replay.json()["payload"][0]["fields"] == {"title": "restricted URL GUID"}
    assert replay.json()["manifest"] == sealed.manifest
    assert stored_guid not in replay.text
    with transaction(engine) as session:
        observation = session.scalar(
            select(Observation).where(Observation.receipt_id == receipt_id)
        )
        assert observation is not None
        revision = session.get(Revision, observation.revision_id)
        assert revision is not None
        assert revision.fields == {"guid": stored_guid, "title": "restricted URL GUID"}


@pytest.mark.parametrize("scheme", ["HTTPS", "HtTpS", "https"])
def test_permitted_url_guid_replay_preserves_original_case_after_future_input(
    settings: Settings, engine: Engine, store: LocalObjectStore, scheme: str
) -> None:
    approve(
        engine,
        allowed_fields=["guid", "title"],
        allowed_host="example.org",
        endpoint="fixture://example.org/feed",
    )
    guid = f"{scheme}://example.org/news/1"
    parsed(engine, store, xml("original", guid=guid))
    sealed = seal_snapshot(engine, store, "allowed-guid-prefix-invariance")
    client = TestClient(create_app(settings, engine))
    before = client.get(f"/v1/snapshots/{sealed.id}", headers=AUDITOR).json()
    assert before["payload"][0]["fields"] == {"guid": guid, "title": "original"}
    parsed(engine, store, xml("future", guid=guid))
    after = client.get(f"/v1/snapshots/{sealed.id}", headers=AUDITOR).json()
    assert before["manifest"] == after["manifest"]
    assert before["sha256"] == after["sha256"]
    assert before["payload"] == after["payload"]


def test_missing_artifact_degrades_and_append_only_invalidation(
    settings: Settings, engine: Engine, store: LocalObjectStore
) -> None:
    approve(engine)
    receipt_id = parsed(engine, store, xml())
    sealed = seal_snapshot(engine, store, "missing-object")
    with transaction(engine) as session:
        receipt = session.get(Receipt, receipt_id)
        assert receipt is not None
        store.delete(receipt.artifact_key)
        session.add(
            SnapshotInvalidation(
                snapshot_id=sealed.id,
                reason="MISSING_ARTIFACT",
                reference_id=receipt.artifact_key,
                recorded_at=db_now(session),
            )
        )
    client = TestClient(create_app(settings, engine))
    observations = client.get("/v1/observations", headers=READER).json()
    assert observations["evidence_status"] == "EVIDENCE_UNAVAILABLE"
    assert any(row["reason"] == "MISSING_ARTIFACT" for row in observations["source_gaps"])
    replay = client.get(f"/v1/snapshots/{sealed.id}", headers=AUDITOR).json()
    assert replay["payload"] is None
    assert replay["invalidations"][0]["reason"] == "MISSING_ARTIFACT"
    assert replay["manifest"] == sealed.manifest
    assert replay["sha256"] == sealed.sha256


def test_stale_checkpoint_and_pagination_openapi(
    settings: Settings, engine: Engine, store: LocalObjectStore
) -> None:
    approve(engine, poll_seconds=1)
    parsed(engine, store, xml(), received_at=datetime.now(UTC) - timedelta(minutes=2))
    client = TestClient(create_app(settings, engine))
    degraded = client.get("/v1/observations", headers=READER).json()
    assert degraded["evidence_status"] == "PARTIALLY_DEGRADED"
    assert any(row["reason"] == "STALE_CHECKPOINT" for row in degraded["source_gaps"])
    assert client.get("/v1/observations?limit=101", headers=READER).status_code == 422
    assert client.get("/v1/observations?offset=-1", headers=READER).status_code == 422
    page = client.get("/v1/observations?limit=1&offset=1", headers=READER).json()
    assert page["records"] == [] and page["total"] == 1
    contracts = client.get("/openapi.json").json()
    assert "ProvenanceRecord" in contracts["components"]["schemas"]
    assert contracts["components"]["schemas"]["SealRequest"]["additionalProperties"] is False


def test_seal_rejects_retrospective_cutoff_and_run_conflict(
    settings: Settings, engine: Engine, store: LocalObjectStore
) -> None:
    approve(engine)
    parsed(engine, store, xml())
    client = TestClient(create_app(settings, engine))
    response = client.post(
        "/v1/snapshots",
        headers=AUDITOR,
        json={"run_id": "no-backdate", "cutoff_at": "2020-01-01T00:00:00Z"},
    )
    assert response.status_code == 422
    first = seal_snapshot(engine, store, "same-run", source_ids=["source-one"])
    with pytest.raises(SnapshotConflict):
        seal_snapshot(engine, store, "same-run")
    second = seal_snapshot(engine, store, "same-run", source_ids=["source-one", "source-one"])
    assert first.id == second.id and first.manifest == second.manifest


def test_concurrent_retries_seal_one_committed_identity(
    engine: Engine, store: LocalObjectStore
) -> None:
    from concurrent.futures import ThreadPoolExecutor

    approve(engine)
    parsed(engine, store, xml("concurrent"))
    with ThreadPoolExecutor(max_workers=2) as workers:
        jobs = [workers.submit(seal_snapshot, engine, store, "concurrent-run") for _ in range(2)]
        sealed = [job.result(timeout=10) for job in jobs]
    assert sealed[0].id == sealed[1].id
    assert sealed[0].manifest == sealed[1].manifest
    with transaction(engine) as session:
        assert session.scalar(select(func.count()).select_from(Snapshot)) == 1
        assert (
            session.scalar(
                select(func.count())
                .select_from(Availability)
                .where(Availability.kind == "snapshot", Availability.entity_id == sealed[0].id)
            )
            == 1
        )


def test_retention_excludes_preexisting_observation_display(
    settings: Settings, engine: Engine, store: LocalObjectStore
) -> None:
    approve(engine, retention_seconds=1)
    parsed(
        engine,
        store,
        xml("expired-metadata"),
    )
    time.sleep(1.05)
    response = (
        TestClient(create_app(settings, engine)).get("/v1/observations", headers=READER).json()
    )
    assert response["records"] == []
    assert response["evidence_status"] == "EVIDENCE_UNAVAILABLE"
    assert response["source_health"][0]["state"] != "OK"


def test_all_rejected_items_are_degraded_evidence_not_healthy_zero(settings, engine, store):
    approve(engine)
    parsed(
        engine, store, b"<rss><channel><item><title>Missing identity</title></item></channel></rss>"
    )
    result = TestClient(create_app(settings, engine)).get("/v1/observations", headers=READER).json()
    assert result["records"] == []
    assert result["evidence_status"] == "PARTIALLY_DEGRADED"
    assert any(gap["reason"] == "parse_rejected_items" for gap in result["source_gaps"])


def test_future_parser_version_cannot_change_sealed_output(settings, engine, store, monkeypatch):
    import pulse.worker as worker
    from pulse.models import Outbox

    approve(engine)
    parsed(engine, store, xml("original-parser"))
    client = TestClient(create_app(settings, engine))
    sealed = seal_snapshot(engine, store, "version-prefix-invariance")
    before = client.get(f"/v1/snapshots/{sealed.id}", headers=AUDITOR).json()
    receipt = ingest(engine, store, xml("future-parser"))
    with transaction(engine) as session:
        event = session.scalar(select(Outbox).where(Outbox.receipt_id == receipt))
        event.version = "parser-v2"
    monkeypatch.setattr(worker, "PARSER_VERSION", "parser-v2")
    assert run_parser_once(engine, store)
    after = client.get(f"/v1/snapshots/{sealed.id}", headers=AUDITOR).json()
    assert before["manifest"] == after["manifest"]
    assert before["sha256"] == after["sha256"]
    assert before["payload"] == after["payload"]
    current = client.get("/v1/observations", headers=READER).json()
    assert current["records"][0]["parser_version"] == "parser-v2"
    assert current["records"][0]["collection_parser_version"] == "xml-metadata-v1"


@pytest.mark.parametrize("expiry", ["policy", "retention"])
@pytest.mark.parametrize("route", ["observations", "replay", "seal"])
def test_expiry_during_checksum_read_never_exposes_or_seals_fields(
    settings: Settings, engine: Engine, store: LocalObjectStore, monkeypatch, expiry, route
):
    changes = (
        {"expires_at": datetime.now(UTC) + timedelta(seconds=1)}
        if expiry == "policy"
        else {"retention_seconds": 1}
    )
    approve(engine, **changes)
    parsed(engine, store, xml("NO_CONTENT_AFTER_MIDREAD_EXPIRY"))
    original_seal = (
        seal_snapshot(engine, store, "before-read-expiry") if route == "replay" else None
    )
    original_verify = LocalObjectStore.verify

    def delayed_verify(self, key, digest):
        result = original_verify(self, key, digest)
        time.sleep(1.1)
        return result

    monkeypatch.setattr(LocalObjectStore, "verify", delayed_verify)
    client = TestClient(create_app(settings, engine))
    if route == "observations":
        response = client.get("/v1/observations", headers=READER)
        result = response.json()
        assert response.status_code == 200
        assert result["records"] == []
        assert result["evidence_status"] == "EVIDENCE_UNAVAILABLE"
        expected = (
            "RIGHTS_EXPIRED_DURING_READ"
            if expiry == "policy"
            else ("RETENTION_EXPIRED_DURING_READ")
        )
        assert any(gap["reason"] == expected for gap in result["source_gaps"])
    elif route == "replay":
        response = client.get(f"/v1/snapshots/{original_seal.id}", headers=AUDITOR)
        result = response.json()
        assert response.status_code == 200
        assert result["payload"] is None
        assert result["validity"] == "REPLAY_UNAVAILABLE"
        assert result["manifest"] == original_seal.manifest
    else:
        sealed = seal_snapshot(engine, store, "during-read-expiry")
        manifest = json.loads(sealed.manifest)
        assert manifest["observations"] == []
        assert manifest["receipts"] == []
        assert manifest["evidence_status"] == "EVIDENCE_UNAVAILABLE"
        assert "NO_CONTENT_AFTER_MIDREAD_EXPIRY" not in sealed.manifest
        return
    assert "NO_CONTENT_AFTER_MIDREAD_EXPIRY" not in response.text


def test_final_retention_sweep_recomputes_first_seen_from_remaining_receipts(
    settings: Settings, engine: Engine, store: LocalObjectStore, monkeypatch
):
    approve(engine, retention_seconds=3)
    now = datetime.now(UTC)
    parsed(engine, store, xml("same-occurrence"), received_at=now - timedelta(seconds=2))
    latest_receipt = parsed(engine, store, xml("same-occurrence"), received_at=now)
    original_verify = LocalObjectStore.verify
    checks = 0

    def delay_second_hash(self, key, digest):
        nonlocal checks
        result = original_verify(self, key, digest)
        checks += 1
        if checks == 2:
            time.sleep(1.1)
        return result

    monkeypatch.setattr(LocalObjectStore, "verify", delay_second_hash)
    response = TestClient(create_app(settings, engine)).get("/v1/observations", headers=READER)
    result = response.json()
    assert response.status_code == 200
    assert len(result["records"]) == 1
    assert result["records"][0]["receipt_id"] == latest_receipt
    assert datetime.fromisoformat(result["records"][0]["first_seen_at"]) == now
    assert result["evidence_status"] == "PARTIALLY_DEGRADED"
    assert any(gap["reason"] == "RETENTION_EXPIRED_DURING_READ" for gap in result["source_gaps"])


def test_expiry_during_manifest_assembly_aborts_seal(engine, store, monkeypatch):
    import pulse.snapshots as snapshots
    from pulse.errors import PolicyBlocked

    approve(engine, retention_seconds=1)
    parsed(engine, store, xml("expires-during-build"))
    original_hash = snapshots.implementation_hash

    def delayed_hash():
        result = original_hash()
        time.sleep(1.1)
        return result

    monkeypatch.setattr(snapshots, "implementation_hash", delayed_hash)
    with pytest.raises(PolicyBlocked, match="EXPIRED_DURING_SNAPSHOT_BUILD"):
        seal_snapshot(engine, store, "expiry-during-build")
    with transaction(engine) as session:
        assert session.scalar(select(func.count()).select_from(Snapshot)) == 0


def test_expiry_during_replay_payload_assembly_hides_payload(settings, engine, store, monkeypatch):
    from pulse.api import ProvenanceRecord

    approve(engine, retention_seconds=1)
    parsed(engine, store, xml("expires-during-payload-build"))
    sealed = seal_snapshot(engine, store, "expiry-during-payload")
    original_validate = ProvenanceRecord.model_validate

    def delayed_validate(value):
        result = original_validate(value)
        time.sleep(1.1)
        return result

    monkeypatch.setattr(ProvenanceRecord, "model_validate", staticmethod(delayed_validate))
    response = TestClient(create_app(settings, engine)).get(
        f"/v1/snapshots/{sealed.id}", headers=AUDITOR
    )
    result = response.json()
    assert response.status_code == 200
    assert result["payload"] is None
    assert result["validity"] == "REPLAY_UNAVAILABLE"
    assert "RIGHTS_OR_RETENTION_EXPIRED_DURING_REPLAY" in result["replay_unavailable_reasons"]
    assert "expires-during-payload-build" not in response.text
