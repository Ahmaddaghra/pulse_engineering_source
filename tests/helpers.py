from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine

from pulse.capture import capture, claim_capture, schedule
from pulse.collection import CollectionResponse, FixtureAdapter
from pulse.config import Settings
from pulse.objects import LocalObjectStore
from pulse.policy import PolicyInput, register_policy


def approve(
    engine: Engine,
    source_id: str = "source-one",
    *,
    publisher: str = "publisher-one",
    owner: str = "owner-one",
    **changes: object,
) -> str:
    now = datetime.now(UTC)
    data = dict(
        publisher_id=publisher,
        owner_id=owner,
        endpoint=f"fixture://{source_id}/feed",
        allowed_host=source_id,
        effective_from=now - timedelta(days=1),
        expires_at=now + timedelta(days=7),
        approved_by="offline-test",
        rate_scope=source_id,
        min_request_seconds=0,
        link_display_allowed=True,
    )
    data.update(changes)
    return register_policy(engine, source_id, f"feed-{source_id}", PolicyInput.model_validate(data))


def xml(
    title: str = "A",
    *,
    guid: str = "article-1",
    url: str = "https://example.org/news/1",
    published: str = "2026-10-01T10:00:00.123456Z",
) -> bytes:
    from xml.sax.saxutils import escape

    return (
        f"<rss><channel><item><guid>{escape(guid)}</guid><link>{escape(url)}</link>"
        f"<title>{escape(title)}</title><pubDate>{escape(published)}</pubDate>"
        "</item></channel></rss>"
    ).encode()


def ingest(
    engine: Engine,
    store: LocalObjectStore,
    body: bytes,
    *,
    source_id: str = "source-one",
    received_at: datetime | None = None,
    status: int = 200,
) -> str:
    from pulse.db import db_now, transaction
    from pulse.models import Source

    with transaction(engine) as session:
        source = session.get(Source, source_id)
        assert source is not None
        source.next_due_at = db_now(session)
    schedule(engine)
    config = Settings(
        database_url=engine.url.render_as_string(hide_password=False), object_root=store.root
    )
    claim = claim_capture(engine, config)
    assert claim is not None
    adapter = FixtureAdapter(
        lambda request: CollectionResponse(
            status, body, received_at or datetime.now(UTC), etag='"fixture-etag"'
        )
    )
    result = capture(engine, config, store, adapter, *claim)
    assert result is not None
    return result
