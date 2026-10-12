"""Resource-bounded collection and metadata parsing.

Collection capabilities are minted by the trusted policy gate after checking the
current source approval. They are passed explicitly to the live transport; live
collection stays disabled by default. Durable acceptance must separately recheck
rights after collection. No parsing operation follows links or fetches entities.
"""

from __future__ import annotations

import http.client
import ipaddress
import json
import math
import re
import socket
import ssl
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from io import BytesIO
from typing import Protocol
from urllib.parse import urlsplit
from xml.etree.ElementTree import Element, ParseError

from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import iterparse

_MAX_BYTES = 16 * 1024 * 1024
_MAX_TIMEOUT = 60.0
_HOST_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z", re.ASCII)
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}\Z", re.ASCII)
_ISO_TIME = re.compile(
    r"\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}(?::\d{2}(?P<fraction>\.\d+)?)?"
    r"(?:[Zz]|[+-]\d{2}:?\d{2})?\Z",
    re.ASCII,
)


class CollectionError(ValueError):
    """The transport or parser could not safely accept a representation."""


class CollectionBlocked(CollectionError):
    """Collection was prevented before contacting an origin."""


@dataclass(frozen=True)
class CollectionResponse:
    status: int
    body: bytes
    received_at: datetime
    etag: str | None = None
    last_modified: str | None = None
    retry_after: str | None = None


@dataclass(frozen=True)
class CollectionCapability:
    """Explicit policy-gate authorization for one approved origin/endpoint.

    This is an internal trust-boundary value, not a public API request model.
    Possession does not replace the persistence-time approval check.
    """

    policy_version_id: str
    endpoint: str
    allowed_host: str
    expires_at: datetime


@dataclass(frozen=True)
class CollectionRequest:
    endpoint: str
    allowed_host: str
    max_bytes: int
    timeout_seconds: float
    etag: str | None = None
    last_modified: str | None = None
    capability: CollectionCapability | None = None


class Collector(Protocol):
    def collect(
        self,
        *,
        endpoint: str,
        allowed_host: str,
        max_bytes: int,
        timeout_seconds: float,
        etag: str | None = None,
        last_modified: str | None = None,
        capability: CollectionCapability | None = None,
    ) -> CollectionResponse: ...


def _limits(max_bytes: int, timeout_seconds: float) -> None:
    if not 1 <= max_bytes <= _MAX_BYTES:
        raise CollectionError("byte budget must be between 1 and 16 MiB")
    if not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= _MAX_TIMEOUT:
        raise CollectionError("timeout must be positive and at most 60 seconds")


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise CollectionError("timestamps must include a UTC offset")
    return value.astimezone(UTC)


def _host(value: str) -> str:
    host = value.lower()
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        pass
    if len(host) > 253 or not all(_HOST_LABEL.fullmatch(label) for label in host.split(".")):
        raise CollectionBlocked("host must be an exact ASCII DNS name or IP address")
    return host


def validate_endpoint(endpoint: str, allowed_host: str) -> tuple[str, str]:
    """Return approved host and origin-form path; never allow URL credentials."""
    if not endpoint.isascii() or any(ord(char) <= 32 or ord(char) == 127 for char in endpoint):
        raise CollectionBlocked("endpoint must be an encoded ASCII HTTPS URL")
    try:
        parts = urlsplit(endpoint)
        port = parts.port
        hostname = parts.hostname
    except ValueError as exc:
        raise CollectionBlocked("invalid endpoint") from exc
    if (
        parts.scheme != "https"
        or hostname is None
        or parts.username is not None
        or parts.password is not None
        or parts.fragment
        or "#" in endpoint
        or port not in (None, 443)
    ):
        raise CollectionBlocked(
            "only credential-free HTTPS on port 443 without fragments is allowed"
        )
    host = _host(hostname)
    if host != _host(allowed_host):
        raise CollectionBlocked("endpoint host is not approved")
    target = parts.path or "/"
    if parts.query:
        target += "?" + parts.query
    return host, target


def validate_addresses(addresses: tuple[str, ...]) -> tuple[str, ...]:
    """Reject mixed public/private answers, rather than picking a safe-looking one."""
    if not addresses:
        raise CollectionBlocked("origin has no resolved addresses")
    approved = []
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError as exc:
            raise CollectionBlocked("resolver returned an invalid address") from exc
        if "%" in address or not ip.is_global or ip.is_multicast or ip.is_unspecified:
            raise CollectionBlocked("origin resolves to a non-public address")
        # Translation/tunnel forms can conceal an IPv4 destination. Fail closed
        # for NAT64/Teredo; mapped and 6to4 addresses must meet IPv4 policy.
        if isinstance(ip, ipaddress.IPv6Address):
            if ip in ipaddress.IPv6Network("64:ff9b::/96") or ip.teredo is not None:
                raise CollectionBlocked("IPv6 translation/tunnel destinations are not allowed")
            if ip.sixtofour is not None and not ip.sixtofour.is_global:
                raise CollectionBlocked("origin embeds a non-public IPv4 address")
        # IPv4-mapped IPv6 must meet the IPv4 policy as well.
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
            if not ip.ipv4_mapped.is_global:
                raise CollectionBlocked("origin resolves to a non-public mapped address")
        approved.append(str(ip))
    return tuple(dict.fromkeys(approved))


def resolve_public_addresses(host: str, timeout_seconds: float) -> tuple[str, ...]:
    """Bound the system resolver with a killable subprocess.

    getaddrinfo has no portable timeout; keeping it outside the collector process
    makes an indefinitely blocked resolver terminate at the request deadline.
    """
    script = (
        "import json,socket,sys; "
        "print(json.dumps(sorted({a[4][0] for a in "
        "socket.getaddrinfo(sys.argv[1],443,type=socket.SOCK_STREAM)})))"
    )
    try:
        result = subprocess.run(
            [sys.executable, "-I", "-c", script, host],
            capture_output=True,
            text=True,
            check=True,
            timeout=timeout_seconds,
        )
        decoded: object = json.loads(result.stdout)
    except (subprocess.SubprocessError, OSError, ValueError) as exc:
        raise CollectionError("bounded origin resolution failed") from exc
    if not isinstance(decoded, list) or not all(isinstance(item, str) for item in decoded):
        raise CollectionBlocked("resolver returned an invalid result")
    return validate_addresses(tuple(str(item) for item in decoded))


def _validator(value: str | None) -> str | None:
    if value is not None and (
        len(value) > 1024
        or not value.isascii()
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise CollectionError("invalid conditional-request validator")
    return value


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Connect to a checked IP while verifying TLS against the approved hostname."""

    def __init__(self, host: str, address: str, timeout: float) -> None:
        self._approved_address = address
        self._tls_context = ssl.create_default_context()
        self._active_socket: socket.socket | None = None
        self._socket_lock = threading.Lock()
        self._expired = False
        super().__init__(host, port=443, timeout=timeout, context=self._tls_context)

    def abort(self) -> None:
        """Interrupt even a slow header/body read at the whole-request deadline."""
        with self._socket_lock:
            self._expired = True
            if self._active_socket is not None:
                try:
                    self._active_socket.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                self._active_socket.close()

    def _set_active(self, sock: socket.socket) -> None:
        with self._socket_lock:
            self._active_socket = sock
            if self._expired:
                sock.close()
                raise TimeoutError("collection deadline expired")

    def connect(self) -> None:
        family = socket.AF_INET6 if ":" in self._approved_address else socket.AF_INET
        raw_socket = socket.socket(family, socket.SOCK_STREAM)
        self._set_active(raw_socket)
        raw_socket.settimeout(self.timeout)
        try:
            raw_socket.connect((self._approved_address, 443))
            tls_socket = self._tls_context.wrap_socket(
                raw_socket, server_hostname=self.host, do_handshake_on_connect=False
            )
            self._set_active(tls_socket)
            tls_socket.do_handshake()
            self.sock = tls_socket
        except BaseException:
            raw_socket.close()
            with self._socket_lock:
                if self._active_socket is not None:
                    self._active_socket.close()
            raise


class HttpsAdapter:
    def __init__(
        self,
        *,
        live_enabled: bool = False,
        resolver: Callable[[str, float], tuple[str, ...]] = resolve_public_addresses,
    ) -> None:
        self.live_enabled = live_enabled
        self._resolver = resolver

    def collect(
        self,
        *,
        endpoint: str,
        allowed_host: str,
        max_bytes: int,
        timeout_seconds: float,
        etag: str | None = None,
        last_modified: str | None = None,
        capability: CollectionCapability | None = None,
    ) -> CollectionResponse:
        _limits(max_bytes, timeout_seconds)
        if not self.live_enabled or capability is None:
            raise CollectionBlocked("live collection requires an explicit authorized capability")
        if (
            not capability.policy_version_id
            or capability.endpoint != endpoint
            or _host(capability.allowed_host) != _host(allowed_host)
            or _utc(capability.expires_at) <= datetime.now(UTC)
        ):
            raise CollectionBlocked("collection capability is expired or does not match the origin")
        host, target = validate_endpoint(endpoint, allowed_host)
        headers = {
            "Accept-Encoding": "identity",
            "Accept": "application/rss+xml, application/atom+xml",
        }
        if _validator(etag) is not None:
            headers["If-None-Match"] = str(etag)
        if _validator(last_modified) is not None:
            headers["If-Modified-Since"] = str(last_modified)
        # Capability is bounded by the capture lease, including suspended workers.
        capability_remaining = (_utc(capability.expires_at) - datetime.now(UTC)).total_seconds()
        if capability_remaining <= 0:
            raise CollectionBlocked("collection lease capability expired")
        timeout_seconds = min(timeout_seconds, capability_remaining)
        deadline = time.monotonic() + timeout_seconds
        addresses = validate_addresses(self._resolver(host, timeout_seconds))
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise CollectionError("collection deadline expired during resolution")
        connection = _PinnedHTTPSConnection(host, addresses[0], remaining)
        timer = threading.Timer(remaining, connection.abort)
        timer.daemon = True
        timer.start()
        try:
            connection.request("GET", target, headers=headers)
            response = connection.getresponse()
            # Redirects are never followed, including same-host redirects.
            if 300 <= response.status < 400 and response.status != 304:
                raise CollectionBlocked("redirects are not authorized")
            encoding = response.getheader("Content-Encoding", "identity")
            if encoding.lower().strip() != "identity":
                raise CollectionError("compressed representations are not accepted")
            length = response.getheader("Content-Length")
            if length is not None:
                if (
                    len(length) > 20
                    or not length.isascii()
                    or not length.isdigit()
                    or int(length) > max_bytes
                ):
                    raise CollectionError("response exceeds byte budget or has invalid length")
            chunks = bytearray()
            while True:
                if time.monotonic() >= deadline:
                    raise CollectionError("collection deadline expired")
                chunk = response.read1(min(65536, max_bytes + 1 - len(chunks)))
                if not chunk:
                    break
                chunks.extend(chunk)
                if len(chunks) > max_bytes:
                    raise CollectionError("response exceeds byte budget")
            if time.monotonic() >= deadline:
                raise CollectionError("collection deadline expired")
            return CollectionResponse(
                status=response.status,
                body=bytes(chunks),
                received_at=datetime.now(UTC),
                etag=_validator(response.getheader("ETag")),
                last_modified=_validator(response.getheader("Last-Modified")),
                retry_after=_validator(response.getheader("Retry-After")),
            )
        except (OSError, http.client.HTTPException) as exc:
            raise CollectionError("bounded HTTPS collection failed") from exc
        finally:
            timer.cancel()
            connection.close()


class FixtureAdapter:
    """Injectable offline collector; caller still performs both policy checks."""

    def __init__(self, responder: Callable[[CollectionRequest], CollectionResponse]) -> None:
        self._responder = responder

    def collect(
        self,
        *,
        endpoint: str,
        allowed_host: str,
        max_bytes: int,
        timeout_seconds: float,
        etag: str | None = None,
        last_modified: str | None = None,
        capability: CollectionCapability | None = None,
    ) -> CollectionResponse:
        _limits(max_bytes, timeout_seconds)
        if endpoint.startswith("fixture:"):
            if not endpoint.isascii() or any(ord(char) <= 32 for char in endpoint):
                raise CollectionBlocked("fixture endpoint must be an encoded ASCII URL")
            try:
                parts = urlsplit(endpoint)
                if (
                    parts.scheme != "fixture"
                    or parts.hostname is None
                    or _host(parts.hostname) != _host(allowed_host)
                    or parts.username is not None
                    or parts.password is not None
                    or parts.port is not None
                    or "#" in endpoint
                ):
                    raise CollectionBlocked(
                        "fixture endpoint does not match its exact approved host"
                    )
            except ValueError as exc:
                raise CollectionBlocked("invalid fixture endpoint") from exc
        else:
            validate_endpoint(endpoint, allowed_host)
        started = time.monotonic()
        result = self._responder(
            CollectionRequest(
                endpoint, allowed_host, max_bytes, timeout_seconds, etag, last_modified, capability
            )
        )
        if time.monotonic() - started > timeout_seconds:
            raise CollectionError("fixture exceeded its collection timeout")
        if len(result.body) > max_bytes:
            raise CollectionError("fixture exceeds byte budget")
        _utc(result.received_at)
        return result


def parse_retry_after(
    value: str | None, *, now: datetime, max_seconds: float = 86400.0
) -> float | None:
    """Read Retry-After delay-seconds or HTTP-date; cap hostile delays."""
    if not math.isfinite(max_seconds) or max_seconds <= 0:
        raise CollectionError("retry delay cap must be positive and finite")
    current = _utc(now)
    if value is None or len(value) > 128:
        return None
    value = value.strip()
    if value.isascii() and value.isdigit():
        return float(min(int(value), max_seconds))
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            return None
        return min(max((_utc(parsed) - current).total_seconds(), 0.0), max_seconds)
    except (ValueError, TypeError, OverflowError):
        return None


def backoff_seconds(
    attempt: int,
    *,
    base_seconds: float = 1.0,
    cap_seconds: float = 300.0,
    random_fraction: float,
) -> float:
    """Bounded equal-jitter exponential retry delay; attempt zero is the first retry."""
    if attempt < 0 or not 0 <= random_fraction <= 1:
        raise CollectionError("invalid retry attempt or jitter sample")
    if not all(math.isfinite(value) and value > 0 for value in (base_seconds, cap_seconds)):
        raise CollectionError("backoff bounds must be positive and finite")
    if base_seconds >= cap_seconds or attempt >= 1024:
        maximum = cap_seconds
    else:
        maximum = min(base_seconds * (2.0**attempt), cap_seconds)
    return maximum * (0.5 + random_fraction * 0.5)


def _tag(element: Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _text(element: Element, name: str) -> str | None:
    for child in element:
        if _tag(child) == name:
            return "".join(child.itertext()).strip() or None
    return None


def _safe_item_url(value: str | None) -> str | None:
    if value is None or any(ord(char) < 32 for char in value):
        return None
    try:
        parts = urlsplit(value)
        if (
            parts.scheme not in ("https", "http")
            or parts.hostname is None
            or parts.username is not None
            or parts.password is not None
        ):
            return None
        _ = parts.port
    except ValueError:
        return None
    return value


def published_precision(value: str | None) -> str:
    """Record the precision of the publisher's raw claim, without granting availability."""
    if value is None:
        return "unknown"
    if _DATE.fullmatch(value):
        return "day"
    iso = _ISO_TIME.fullmatch(value)
    if iso is not None:
        if iso.group("fraction") is not None:
            return "microsecond"
        return "second" if value[16:17] == ":" else "minute"
    try:
        parsedate_to_datetime(value)
        return "second"
    except (TypeError, ValueError, OverflowError):
        return "unknown"


def _item(element: Element, atom: bool) -> dict[str, str | None]:
    if atom:
        link = None
        for child in element:
            if _tag(child) == "link" and child.get("rel", "alternate") == "alternate":
                link = child.get("href")
                break
        guid = _text(element, "id")
        published = _text(element, "published") or _text(element, "updated")
    else:
        link = _text(element, "link")
        guid = _text(element, "guid")
        published = _text(element, "pubDate") or _text(element, "date")
    return {
        "guid": guid,
        "url": _safe_item_url(link),
        "title": _text(element, "title"),
        "published_at": published,
        "published_precision": published_precision(published),
    }


def parse_feed(
    body: bytes,
    *,
    max_bytes: int = 1024 * 1024,
    max_depth: int = 32,
    max_items: int = 1000,
    max_elements: int = 10000,
    max_text_chars: int = 1024 * 1024,
    timeout_seconds: float = 5.0,
) -> list[dict[str, str | None]]:
    """Parse only RSS/Atom metadata, rejecting entities, DTDs and resource overflow.

    Limits cover the complete XML, including fields that will be discarded.
    Structural/size limits and an elapsed-time check bound work here; process-level
    CPU/address-space isolation is a separate deployment responsibility.
    """
    _limits(max_bytes, timeout_seconds)
    if len(body) > max_bytes:
        raise CollectionError("XML exceeds byte budget")
    if (
        not 1 <= max_depth <= 128
        or not 0 <= max_items <= 10000
        or not 1 <= max_elements <= 100000
        or max_text_chars < 1
    ):
        raise CollectionError("invalid XML structural budget")
    deadline = time.monotonic() + timeout_seconds
    stack: list[Element] = []
    result: list[dict[str, str | None]] = []
    item_count = 0
    element_count = 0
    channel_count = 0
    text_count = 0
    root_name: str | None = None
    try:
        iterator = iterparse(
            BytesIO(body),
            events=("start", "end"),
            forbid_dtd=True,
            forbid_entities=True,
            forbid_external=True,
        )
        for event, element in iterator:
            if time.monotonic() >= deadline:
                raise CollectionError("XML parsing exceeded its timeout")
            name = _tag(element)
            if event == "start":
                element_count += 1
                if element_count > max_elements:
                    raise CollectionError("XML exceeds element budget")
                stack.append(element)
                if root_name is None:
                    root_name = name
                    if name not in ("rss", "feed"):
                        raise CollectionError("only RSS and Atom feeds are accepted")
                if len(stack) > max_depth:
                    raise CollectionError("XML exceeds nesting budget")
                if root_name == "rss" and name == "channel":
                    if len(stack) != 2 or channel_count:
                        raise CollectionError("RSS requires one direct channel")
                    channel_count += 1
                if (
                    root_name == "rss"
                    and name == "item"
                    and (len(stack) != 3 or _tag(stack[-2]) != "channel")
                ):
                    raise CollectionError("RSS items must be direct channel children")
                if name in ("item", "entry"):
                    item_count += 1
                    if item_count > max_items:
                        raise CollectionError("XML exceeds item budget")
                continue
            text_count += len(element.text or "") + len(element.tail or "")
            text_count += sum(len(value) for value in element.attrib.values())
            if text_count > max_text_chars:
                raise CollectionError("XML exceeds text budget")
            is_rss_item = (
                root_name == "rss"
                and name == "item"
                and len(stack) == 3
                and _tag(stack[-2]) == "channel"
            )
            is_atom_item = root_name == "feed" and name == "entry" and len(stack) == 2
            if is_rss_item or is_atom_item:
                result.append(_item(element, atom=is_atom_item))
                element.clear()
                stack[-2].remove(element)
            stack.pop()
    except (ParseError, DefusedXmlException) as exc:
        raise CollectionError("malformed or unsafe XML") from exc
    if root_name == "rss" and channel_count != 1:
        raise CollectionError("RSS requires one direct channel")
    return result
