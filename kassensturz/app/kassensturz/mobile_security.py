"""Transport and request-rate security primitives for the future mobile API.

This module does not expose routes or open a listener. Forwarding headers are
trusted only when the immediate TCP peer is explicitly present in the proxy
allowlist. Rate-limit identity is derived from the socket peer or a validated
forwarded chain from such a trusted proxy.
"""
from __future__ import annotations

import ipaddress
import math
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable, Iterable

from starlette.requests import Request


IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network


def parse_trusted_proxy_networks(value: str | None) -> tuple[IPNetwork, ...]:
    """Parse a comma-separated allowlist of exact proxy IPs or CIDR networks."""
    networks: list[IPNetwork] = []
    for item in (value or "").split(","):
        entry = item.strip()
        if not entry:
            continue
        try:
            networks.append(ipaddress.ip_network(entry, strict=False))
        except ValueError as exc:
            raise ValueError("KASSENSTURZ_TRUSTED_PROXIES contains an invalid IP network.") from exc
    return tuple(networks)


def _parse_ip(value: str | None) -> IPAddress | None:
    if not value:
        return None
    try:
        return ipaddress.ip_address(value.strip())
    except ValueError:
        return None


def _is_trusted(address: IPAddress | None, networks: Iterable[IPNetwork]) -> bool:
    if address is None:
        return False
    return any(address.version == network.version and address in network for network in networks)


def socket_peer(request: Request) -> IPAddress | None:
    """Return only the TCP peer address; never consult forwarding headers."""
    return _parse_ip(request.client.host if request.client else None)


def effective_client_ip(
    request: Request,
    trusted_proxies: Iterable[IPNetwork] = (),
) -> IPAddress | None:
    """Resolve the client IP without allowing an untrusted peer to spoof XFF.

    If the socket peer is not trusted, all forwarding headers are ignored. For
    a trusted proxy, walk the X-Forwarded-For chain from nearest to farthest and
    return the first non-trusted hop. A malformed chain falls back to the
    immediate peer, which is the conservative shared proxy bucket.
    """
    peer = socket_peer(request)
    if peer is None or not _is_trusted(peer, trusted_proxies):
        return peer

    forwarded = request.headers.get("x-forwarded-for")
    if not forwarded:
        return peer

    entries = [part.strip() for part in forwarded.split(",")]
    if not entries or any(not part for part in entries):
        return peer

    chain = [_parse_ip(entry) for entry in entries]
    if any(address is None for address in chain):
        return peer

    for address in reversed(chain):
        if address is not None and not _is_trusted(address, trusted_proxies):
            return address
    return peer


def request_is_https(
    request: Request,
    trusted_proxies: Iterable[IPNetwork] = (),
) -> bool:
    """Check direct TLS or a single HTTPS assertion from an allowlisted proxy."""
    if request.scope.get("scheme", "").lower() == "https":
        return True

    peer = socket_peer(request)
    if not _is_trusted(peer, trusted_proxies):
        return False

    forwarded_proto = request.headers.get("x-forwarded-proto", "")
    # Do not accept a comma-separated chain or ambiguous proxy values.
    return forwarded_proto.strip().lower() == "https"


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    remaining: int
    retry_after: int


@dataclass
class _Bucket:
    events: deque[float]


class InMemoryRateLimiter:
    """Thread-safe bounded sliding-window limiter for a single app process.

    This limiter is suitable only while Kassensturz runs as one application
    process. Multi-worker deployments must replace it with shared state (for
    example a transactional SQLite-backed limiter) before enabling mobile APIs.
    When the bucket table is full, unknown keys are rejected until buckets
    expire; the limiter never evicts a live bucket to make room for an attacker.
    """

    def __init__(
        self,
        *,
        max_keys: int = 4096,
        clock: Callable[[], float] | None = None,
    ):
        if max_keys < 1:
            raise ValueError("max_keys must be at least 1.")
        self._max_keys = max_keys
        self._clock = clock or time.monotonic
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, *, limit: int, window_seconds: float) -> RateLimitDecision:
        """Consume one attempt and return retry timing when the key is limited."""
        if not isinstance(key, str) or not key.strip():
            raise ValueError("rate-limit key must be a non-empty string")
        if isinstance(limit, bool) or limit < 1:
            raise ValueError("limit must be a positive integer")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")

        now = self._clock()
        cutoff = now - window_seconds
        with self._lock:
            # Opportunistically prune expired buckets to keep memory bounded.
            expired_keys = []
            for bucket_key, bucket in self._buckets.items():
                while bucket.events and bucket.events[0] <= cutoff:
                    bucket.events.popleft()
                if not bucket.events:
                    expired_keys.append(bucket_key)
            for bucket_key in expired_keys:
                del self._buckets[bucket_key]

            bucket = self._buckets.get(key)
            if bucket is None:
                if len(self._buckets) >= self._max_keys:
                    return RateLimitDecision(False, 0, max(1, math.ceil(window_seconds)))
                bucket = _Bucket(deque())
                self._buckets[key] = bucket

            if len(bucket.events) >= limit:
                retry_after = max(
                    1,
                    math.ceil(bucket.events[0] + window_seconds - now),
                )
                return RateLimitDecision(False, 0, retry_after)

            bucket.events.append(now)
            return RateLimitDecision(True, limit - len(bucket.events), 0)


def request_rate_limit_key(
    request: Request,
    trusted_proxies: Iterable[IPNetwork] = (),
    *,
    scope: str,
) -> str:
    """Build a namespaced limiter key from the resolved network client."""
    if not scope or not scope.strip():
        raise ValueError("rate-limit scope must be non-empty")
    address = effective_client_ip(request, trusted_proxies)
    # Missing or invalid peer metadata shares one conservative bucket.
    return f"{scope.strip()}:{address.compressed if address else 'unknown'}"
