"""Synthetic tests only: no test contacts a publisher or public network."""

from __future__ import annotations

import socket
import subprocess
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

import pulse.collection as collection
from pulse.collection import (
    CollectionBlocked,
    CollectionCapability,
    CollectionError,
    CollectionRequest,
    CollectionResponse,
    FixtureAdapter,
    HttpsAdapter,
    backoff_seconds,
    parse_feed,
    parse_retry_after,
    published_precision,
    resolve_public_addresses,
    validate_addresses,
    validate_endpoint,
)

ENDPOINT = "https://feed.example.test/rss?format=xml"
HOST = "feed.example.test"
NOW = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)
PUBLIC_ADDRESS = "8.8.8.8"


def capability() -> CollectionCapability:
    return CollectionCapability(
        "approval-v1", ENDPOINT, HOST, datetime.now(UTC) + timedelta(hours=1)
    )


def collect(adapter: HttpsAdapter | FixtureAdapter, **changes: Any) -> CollectionResponse:
    params: dict[str, Any] = {
        "endpoint": ENDPOINT,
        "allowed_host": HOST,
        "max_bytes": 1024,
        "timeout_seconds": 1.0,
    }
    params.update(changes)
    return adapter.collect(**params)


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://feed.example.test/rss",
        "https://feed.example.test:444/rss",
        "https://feed.example.test:80/rss",
        "https://user@feed.example.test/rss",
        "https://user:password@feed.example.test/rss",
        "https://feed.example.test/rss#fragment",
        "https://feed.example.test/rss#",
        "https://feed.example.test.evil/rss",
        "https://evilfeed.example.test/rss",
        "https://feed.example.test./rss",
        "https://feed.example.test\\@other.test/rss",
        "https://feed.example.test/rss\nX: injected",
        "https://feed.example.test/أخبار",
        "https://[bad-address]/rss",
        "https://feed.example.test:not-a-port/rss",
    ],
)
def test_unsafe_endpoints_rejected(endpoint: str) -> None:
    with pytest.raises(CollectionBlocked):
        validate_endpoint(endpoint, HOST)


def test_origin_form_and_exact_case_insensitive_host() -> None:
    assert validate_endpoint(ENDPOINT, HOST.upper()) == (HOST, "/rss?format=xml")
    assert validate_endpoint("https://feed.example.test:443", HOST) == (HOST, "/")


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "172.16.1.1",
        "192.168.0.1",
        "169.254.169.254",
        "100.64.0.1",
        "0.0.0.0",
        "224.0.0.1",
        "192.0.2.1",
        "::1",
        "::",
        "fe80::1",
        "fc00::1",
        "ff02::1",
        "2001:db8::1",
        "::ffff:127.0.0.1",
        "64:ff9b::7f00:1",
        "2002:7f00:1::",
        "2001:0:4136:e378:8000:63bf:3fff:fdd2",
        "2606:4700:4700::1111%en0",
        "not-an-ip",
    ],
)
def test_non_public_destinations_and_mixed_dns_answers_rejected(address: str) -> None:
    with pytest.raises(CollectionBlocked):
        validate_addresses((PUBLIC_ADDRESS, address))


@given(st.ip_addresses(v=4))
def test_destination_validation_agrees_with_global_address_policy(address: Any) -> None:
    permitted = address.is_global and not address.is_multicast and not address.is_unspecified
    if permitted:
        assert validate_addresses((str(address),)) == (str(address),)
    else:
        with pytest.raises(CollectionBlocked):
            validate_addresses((str(address),))


def test_public_addresses_deduplicate_and_empty_answers_fail() -> None:
    assert validate_addresses((PUBLIC_ADDRESS, PUBLIC_ADDRESS)) == (PUBLIC_ADDRESS,)
    with pytest.raises(CollectionBlocked):
        validate_addresses(())


def test_resolver_is_killable_and_validates_results(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(kwargs)
        assert args[0][-1] == HOST
        return subprocess.CompletedProcess(args[0], 0, '["8.8.8.8"]', "")

    monkeypatch.setattr(subprocess, "run", run)
    assert resolve_public_addresses(HOST, 0.5) == (PUBLIC_ADDRESS,)
    assert calls[0]["timeout"] == 0.5

    def timeout(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(CollectionError, match="resolution"):
        resolve_public_addresses(HOST, 0.01)


def test_live_gate_precedes_dns_or_transport() -> None:
    def forbidden_resolution(host: str, timeout: float) -> tuple[str, ...]:
        pytest.fail("unauthorized collection reached DNS")

    for adapter, grant in [
        (HttpsAdapter(resolver=forbidden_resolution), capability()),
        (HttpsAdapter(live_enabled=True, resolver=forbidden_resolution), None),
        (
            HttpsAdapter(live_enabled=True, resolver=forbidden_resolution),
            CollectionCapability("v1", ENDPOINT, HOST, NOW),
        ),
        (
            HttpsAdapter(live_enabled=True, resolver=forbidden_resolution),
            CollectionCapability("v1", "https://other.test/", HOST, capability().expires_at),
        ),
    ]:
        with pytest.raises(CollectionBlocked):
            collect(adapter, capability=grant)


class FakeResponse:
    def __init__(
        self, status: int = 200, body: bytes = b"<rss/>", headers: dict[str, str] | None = None
    ) -> None:
        self.status = status
        self.body = body
        self.headers = headers or {}

    def getheader(self, name: str, default: str | None = None) -> str | None:
        return self.headers.get(name, default)

    def read1(self, count: int) -> bytes:
        result, self.body = self.body[:count], self.body[count:]
        return result


class FakeConnection:
    instances: list[FakeConnection] = []
    response = FakeResponse()

    def __init__(self, host: str, address: str, timeout: float) -> None:
        self.host, self.address, self.timeout = host, address, timeout
        self.closed = False
        self.request_args: tuple[str, str, dict[str, str]] | None = None
        self.__class__.instances.append(self)

    def request(self, method: str, path: str, *, headers: dict[str, str]) -> None:
        self.request_args = method, path, headers

    def getresponse(self) -> FakeResponse:
        return self.response

    def abort(self) -> None:
        self.close()

    def close(self) -> None:
        self.closed = True


def mock_transport(monkeypatch: pytest.MonkeyPatch, response: FakeResponse) -> HttpsAdapter:
    FakeConnection.instances = []
    FakeConnection.response = response
    monkeypatch.setattr(collection, "_PinnedHTTPSConnection", FakeConnection)
    return HttpsAdapter(live_enabled=True, resolver=lambda host, timeout: (PUBLIC_ADDRESS,))


def test_live_transport_pins_ip_preserves_hostname_and_sends_cache_validators(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = mock_transport(monkeypatch, FakeResponse(headers={"ETag": '"v2"'}))
    result = collect(adapter, capability=capability(), etag='"v1"', last_modified="yesterday")
    connection = FakeConnection.instances[0]
    assert (connection.host, connection.address) == (HOST, PUBLIC_ADDRESS)
    assert connection.request_args == (
        "GET",
        "/rss?format=xml",
        {
            "Accept-Encoding": "identity",
            "Accept": "application/rss+xml, application/atom+xml",
            "If-None-Match": '"v1"',
            "If-Modified-Since": "yesterday",
        },
    )
    assert connection.closed
    assert result.body == b"<rss/>"
    assert result.etag == '"v2"'
    assert result.received_at.tzinfo == UTC


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_redirects_fail_closed_without_second_request(
    status: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = mock_transport(
        monkeypatch, FakeResponse(status, headers={"Location": "http://127.0.0.1/admin"})
    )
    with pytest.raises(CollectionBlocked, match="redirect"):
        collect(adapter, capability=capability())
    assert len(FakeConnection.instances) == 1
    assert FakeConnection.instances[0].closed


@pytest.mark.parametrize("encoding", ["gzip", "deflate", "br", "identity, gzip", ""])
def test_compressed_payloads_rejected(encoding: str, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = mock_transport(monkeypatch, FakeResponse(headers={"Content-Encoding": encoding}))
    with pytest.raises(CollectionError, match="compressed"):
        collect(adapter, capability=capability())


@pytest.mark.parametrize(
    "response",
    [
        FakeResponse(body=b"x" * 1025),
        FakeResponse(headers={"Content-Length": "1025"}),
        FakeResponse(headers={"Content-Length": "-1"}),
        FakeResponse(headers={"Content-Length": "garbage"}),
        FakeResponse(headers={"Content-Length": "9" * 5000}),
    ],
)
def test_response_bytes_and_length_bounded(
    response: FakeResponse,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = mock_transport(monkeypatch, response)
    with pytest.raises(CollectionError):
        collect(adapter, capability=capability())
    assert FakeConnection.instances[0].closed


@pytest.mark.parametrize("status", [304, 429, 503])
def test_conditional_and_retry_responses_preserve_status_headers(
    status: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = mock_transport(monkeypatch, FakeResponse(status, b"", {"Retry-After": "60"}))
    result = collect(adapter, capability=capability())
    assert (result.status, result.body, result.retry_after) == (status, b"", "60")


def test_validator_injection_precedes_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = mock_transport(monkeypatch, FakeResponse())
    with pytest.raises(CollectionError, match="validator"):
        collect(adapter, capability=capability(), etag='"v1"\r\nX-Secret: injected')
    assert not FakeConnection.instances


def test_connect_uses_literal_ip_and_original_sni(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[tuple[str, object]] = []

    class StubSocket:
        def settimeout(self, value: object) -> None:
            events.append(("timeout", value))

        def connect(self, address: object) -> None:
            events.append(("connect", address))

        def do_handshake(self) -> None:
            events.append(("handshake", True))

        def close(self) -> None:
            events.append(("close", True))

    class StubContext:
        def wrap_socket(self, sock: StubSocket, **kwargs: Any) -> StubSocket:
            assert kwargs["do_handshake_on_connect"] is False
            events.append(("server_hostname", kwargs["server_hostname"]))
            return sock

    monkeypatch.setattr(socket, "socket", lambda *args: StubSocket())
    connection = collection._PinnedHTTPSConnection(HOST, PUBLIC_ADDRESS, 1.0)
    connection._tls_context = StubContext()  # type: ignore[assignment]
    connection.connect()
    assert ("connect", (PUBLIC_ADDRESS, 443)) in events
    assert ("server_hostname", HOST) in events
    assert ("handshake", True) in events
    connection.close()


def test_fixture_receives_limits_and_conditional_headers() -> None:
    requests: list[CollectionRequest] = []

    def responder(request: CollectionRequest) -> CollectionResponse:
        requests.append(request)
        return CollectionResponse(200, b"<rss/>", NOW, '"v1"')

    result = collect(FixtureAdapter(responder), etag='"previous"')
    assert result.status == 200
    assert requests[0].etag == '"previous"'
    assert requests[0].max_bytes == 1024
    with pytest.raises(CollectionError, match="budget"):
        collect(FixtureAdapter(lambda request: CollectionResponse(200, b"x" * 1025, NOW)))


@pytest.mark.parametrize("value", [None, "bad", "-3", "+3", "3.5", "١٢", "x" * 129])
def test_invalid_retry_after_returns_none(value: str | None) -> None:
    assert parse_retry_after(value, now=NOW) is None


def test_retry_after_seconds_http_date_past_and_caps() -> None:
    assert parse_retry_after(" 120 ", now=NOW) == 120
    assert parse_retry_after("9999999999999999999999", now=NOW, max_seconds=300) == 300
    assert parse_retry_after(format_datetime(NOW + timedelta(minutes=2)), now=NOW) == 120
    assert parse_retry_after(format_datetime(NOW - timedelta(minutes=2)), now=NOW) == 0
    assert parse_retry_after(format_datetime(NOW + timedelta(days=2)), now=NOW) == 86400


@given(
    attempt=st.integers(min_value=0, max_value=100000),
    fraction=st.floats(min_value=0, max_value=1, allow_nan=False),
)
def test_backoff_remains_bounded(attempt: int, fraction: float) -> None:
    delay = backoff_seconds(attempt, base_seconds=2, cap_seconds=120, random_fraction=fraction)
    assert 0 <= delay <= 120
    if attempt < 7:
        assert delay <= min(2 * 2**attempt, 120)


def test_backoff_caps_and_equal_jitter_values() -> None:
    assert backoff_seconds(0, random_fraction=0) == 0.5
    assert backoff_seconds(1, random_fraction=1) == 2
    assert backoff_seconds(1000000, random_fraction=1) == 300
    with pytest.raises(CollectionError):
        backoff_seconds(-1, random_fraction=0.5)


RSS = (
    '<rss version="2.0"><channel><item><guid>publisher:1</guid>'
    "<link>https://publisher.test/story/1</link><title>عنوان الخبر</title>"
    "<pubDate>Mon, 12 Oct 2026 11:45:00 GMT</pubDate>"
    "<description>NOT RETAINED</description></item></channel></rss>"
).encode()


def test_only_permitted_metadata_is_extracted_and_arabic_preserved() -> None:
    assert parse_feed(RSS) == [
        {
            "guid": "publisher:1",
            "url": "https://publisher.test/story/1",
            "title": "عنوان الخبر",
            "published_at": "Mon, 12 Oct 2026 11:45:00 GMT",
            "published_precision": "second",
        }
    ]
    assert "NOT RETAINED" not in repr(parse_feed(RSS))


def test_atom_metadata_and_date_precision() -> None:
    body = b"""<feed xmlns="http://www.w3.org/2005/Atom"><entry>
    <id>atom:1</id><title>Title</title><link rel="self" href="https://feed.test/self"/>
    <link href="https://publisher.test/1"/><published>2026-10-12</published>
    <content>not retained</content></entry></feed>"""
    result = parse_feed(body)[0]
    assert result["guid"] == "atom:1"
    assert result["url"] == "https://publisher.test/1"
    assert result["published_precision"] == "day"


@pytest.mark.parametrize(
    "body",
    [
        b"<!DOCTYPE rss [<!ENTITY x 'attack'>]><rss><channel><item><title>&x;</title>"
        b"</item></channel></rss>",
        b"<!DOCTYPE rss SYSTEM 'http://127.0.0.1/secret'><rss/>",
        b"<rss><channel>",
        b"not XML",
        b"<html><body>not a feed</body></html>",
    ],
)
def test_malformed_dtd_and_entities_fail_without_external_access(body: bytes) -> None:
    with pytest.raises(CollectionError):
        parse_feed(body)


def test_parser_resource_budgets_cover_discarded_content_and_structure() -> None:
    cases = [
        (RSS, {"max_bytes": len(RSS) - 1}),
        (b"<rss><x><x><x/></x></x></rss>", {"max_depth": 3}),
        (b"<rss><channel><item/><item/></channel></rss>", {"max_items": 1}),
        (b"<rss><channel><x/><x/><x/></channel></rss>", {"max_elements": 3}),
        (
            b"<rss><channel><description>discarded</description></channel></rss>",
            {"max_text_chars": 2},
        ),
        (b'<rss><channel><x attribute="discarded"/></channel></rss>', {"max_text_chars": 2}),
    ]
    for body, limits in cases:
        with pytest.raises(CollectionError, match="budget"):
            parse_feed(body, **limits)


@given(st.integers(min_value=1, max_value=20))
def test_item_budget_cannot_accept_more_than_its_limit(count: int) -> None:
    body = b"<rss><channel>" + b"<item/>" * count + b"</channel></rss>"
    assert len(parse_feed(body, max_items=count)) == count
    if count > 1:
        with pytest.raises(CollectionError, match="item budget"):
            parse_feed(body, max_items=count - 1)


@pytest.mark.parametrize(
    "url", ["javascript:alert(1)", "file:///secret", "https://user@host.test/1"]
)
def test_unsafe_article_links_are_not_retained(url: str) -> None:
    body = f"<rss><channel><item><link>{url}</link></item></channel></rss>".encode()
    assert parse_feed(body)[0]["url"] is None


@pytest.mark.parametrize(
    ("value", "precision"),
    [
        (None, "unknown"),
        ("bad", "unknown"),
        ("2026-10-12", "day"),
        ("2026-10-12T10:20Z", "minute"),
        ("2026-10-12T10:20:00Z", "second"),
        ("2026-10-12T10:20:00.123Z", "microsecond"),
    ],
)
def test_publisher_claim_precision(value: str | None, precision: str) -> None:
    assert published_precision(value) == precision


@pytest.mark.parametrize("deadline_source", ["request_timeout", "capability_expiry"])
def test_absolute_transport_deadline_interrupts_a_blocked_body_read(
    monkeypatch: pytest.MonkeyPatch,
    deadline_source: str,
) -> None:
    """Use an AF_UNIX socket pair: exercise timer interruption with zero network access."""
    reader, writer = socket.socketpair()

    class BlockingResponse(FakeResponse):
        def read1(self, count: int) -> bytes:
            return reader.recv(count)

    class BlockingConnection(FakeConnection):
        response = BlockingResponse()

        def abort(self) -> None:
            reader.shutdown(socket.SHUT_RDWR)

        def close(self) -> None:
            reader.close()
            writer.close()
            super().close()

    monkeypatch.setattr(collection, "_PinnedHTTPSConnection", BlockingConnection)
    adapter = HttpsAdapter(live_enabled=True, resolver=lambda host, timeout: (PUBLIC_ADDRESS,))
    started = collection.time.monotonic()
    try:
        grant = capability()
        request_timeout = 0.03
        if deadline_source == "capability_expiry":
            grant = CollectionCapability(
                "approval-v1",
                ENDPOINT,
                HOST,
                datetime.now(UTC) + timedelta(seconds=0.03),
            )
            request_timeout = 1.0
        with pytest.raises(CollectionError, match="deadline"):
            collect(adapter, capability=grant, timeout_seconds=request_timeout)
        assert collection.time.monotonic() - started < 1.0
    finally:
        reader.close()
        writer.close()


def test_default_tls_context_verifies_certificates_and_hostname() -> None:
    connection = collection._PinnedHTTPSConnection(HOST, PUBLIC_ADDRESS, 1.0)
    assert connection._tls_context.check_hostname
    assert connection._tls_context.verify_mode == collection.ssl.CERT_REQUIRED
    connection.close()


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan"), 61])
def test_invalid_transport_time_budget_fails_before_callback(timeout: float) -> None:
    def responder(request: CollectionRequest) -> CollectionResponse:
        pytest.fail("invalid budget reached callback")

    with pytest.raises(CollectionError, match="timeout"):
        collect(FixtureAdapter(responder), timeout_seconds=timeout)


def test_fixture_scheme_is_local_and_requires_exact_approved_host() -> None:
    calls: list[CollectionRequest] = []

    def responder(request: CollectionRequest) -> CollectionResponse:
        calls.append(request)
        return CollectionResponse(200, b"<rss/>", NOW)

    adapter = FixtureAdapter(responder)
    assert collect(adapter, endpoint="fixture://feed.example.test/feed").status == 200
    assert len(calls) == 1
    for endpoint in [
        "fixture://other.test/feed",
        "fixture://user@feed.example.test/feed",
        "fixture://feed.example.test:443/feed",
        "fixture://feed.example.test/feed#fragment",
        "fixture://feed.example.test/feed#",
        "fixture://feed.example.test/feed\nignored",
    ]:
        with pytest.raises(CollectionBlocked):
            collect(adapter, endpoint=endpoint)
    assert len(calls) == 1
    with pytest.raises(CollectionBlocked):
        collect(
            HttpsAdapter(live_enabled=True),
            endpoint="fixture://feed.example.test/feed",
            capability=capability(),
        )


def test_zero_item_budget_accepts_a_healthy_empty_feed_only() -> None:
    assert parse_feed(b"<rss><channel/></rss>", max_items=0) == []
    with pytest.raises(CollectionError, match="item budget"):
        parse_feed(b"<rss><channel><item/></channel></rss>", max_items=0)


@pytest.mark.parametrize(
    "body",
    [
        b"<rss/>",
        b"<rss><extension/></rss>",
        b"<rss><channel/><channel/></rss>",
        b"<rss><extension><channel/></extension></rss>",
        b"<rss><channel><extension><item/></extension></channel></rss>",
        b"<rss><item/><channel/></rss>",
    ],
)
def test_malformed_rss_structure_cannot_become_healthy_empty(body: bytes) -> None:
    with pytest.raises(CollectionError, match="channel"):
        parse_feed(body)


def test_expired_capability_prevents_resolution_and_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_resolution(host: str, timeout: float) -> tuple[str, ...]:
        pytest.fail("expired capability reached DNS")

    def forbidden_connection(*args: object) -> FakeConnection:
        pytest.fail("expired capability reached connection construction")

    monkeypatch.setattr(collection, "_PinnedHTTPSConnection", forbidden_connection)
    grant = CollectionCapability(
        "approval-v1", ENDPOINT, HOST, datetime.now(UTC) - timedelta(seconds=1)
    )
    with pytest.raises(CollectionBlocked, match="expired"):
        collect(HttpsAdapter(live_enabled=True, resolver=forbidden_resolution), capability=grant)


def test_capability_lifetime_clamps_resolution_and_connection_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    budgets: list[float] = []

    def resolver(host: str, timeout: float) -> tuple[str, ...]:
        budgets.append(timeout)
        return (PUBLIC_ADDRESS,)

    monkeypatch.setattr(collection, "_PinnedHTTPSConnection", FakeConnection)
    FakeConnection.instances = []
    FakeConnection.response = FakeResponse()
    adapter = HttpsAdapter(live_enabled=True, resolver=resolver)
    grant = CollectionCapability(
        "approval-v1", ENDPOINT, HOST, datetime.now(UTC) + timedelta(seconds=0.2)
    )
    result = collect(adapter, capability=grant, timeout_seconds=30)
    assert result.status == 200
    assert 0 < budgets[0] <= 0.2
    assert 0 < FakeConnection.instances[0].timeout <= budgets[0]


def test_capability_expiring_during_resolution_prevents_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tick = [100.0]

    def resolver(host: str, timeout: float) -> tuple[str, ...]:
        tick[0] = 101.0
        return (PUBLIC_ADDRESS,)

    def forbidden_connection(*args: object) -> FakeConnection:
        pytest.fail("expired resolution budget reached a connection")

    monkeypatch.setattr(collection.time, "monotonic", lambda: tick[0])
    monkeypatch.setattr(collection, "_PinnedHTTPSConnection", forbidden_connection)
    grant = CollectionCapability(
        "approval-v1", ENDPOINT, HOST, datetime.now(UTC) + timedelta(seconds=0.2)
    )
    with pytest.raises(CollectionError, match="resolution"):
        collect(HttpsAdapter(live_enabled=True, resolver=resolver), capability=grant)


def test_capability_expiring_during_tls_context_creation_prevents_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tick = [100.0]

    class SlowConstruction(FakeConnection):
        def __init__(self, host: str, address: str, timeout: float) -> None:
            super().__init__(host, address, timeout)
            tick[0] = 101.0

    monkeypatch.setattr(collection.time, "monotonic", lambda: tick[0])
    monkeypatch.setattr(collection, "_PinnedHTTPSConnection", SlowConstruction)
    SlowConstruction.instances = []
    SlowConstruction.response = FakeResponse()
    grant = CollectionCapability(
        "approval-v1", ENDPOINT, HOST, datetime.now(UTC) + timedelta(seconds=0.2)
    )
    adapter = HttpsAdapter(live_enabled=True, resolver=lambda host, timeout: (PUBLIC_ADDRESS,))
    with pytest.raises(CollectionError, match="deadline"):
        collect(adapter, capability=grant)
    assert SlowConstruction.instances[0].request_args is None
    assert SlowConstruction.instances[0].closed
