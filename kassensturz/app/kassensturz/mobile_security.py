"""Grundbausteine für Transportsicherheit und Ratenbegrenzung der API der Handy-App.

Dieses Modul öffnet keinen Listener. Weiterleitungs-Headern wird nur vertraut, wenn die
direkte TCP-Gegenstelle ausdrücklich in der Proxy-Allowlist steht. Die Identität für die
Ratenbegrenzung kommt von der Socket-Gegenstelle oder einer geprüften Weiterleitungskette
eines solchen vertrauenswürdigen Proxys.
"""
from __future__ import annotations

import ipaddress
import math
import threading
import time
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from starlette.requests import Request

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network


def parse_trusted_proxy_networks(value: str | None) -> tuple[IPNetwork, ...]:
    """Eine kommagetrennte Allowlist exakter Proxy-IPs oder CIDR-Netze auswerten."""
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


def address_in_networks(
    address: IPAddress | None,
    networks: Iterable[IPNetwork],
) -> bool:
    """Eine IP-Adresse gegen eine ausdrückliche Allowlist von Netzen prüfen."""
    return _is_trusted(address, networks)


def socket_peer(request: Request) -> IPAddress | None:
    """Nur die Adresse der TCP-Gegenstelle zurückgeben; nie Weiterleitungs-Header befragen."""
    return _parse_ip(request.client.host if request.client else None)


def effective_client_ip(
    request: Request,
    trusted_proxies: Iterable[IPNetwork] = (),
) -> IPAddress | None:
    """Die Client-IP ermitteln, ohne dass eine nicht vertrauenswürdige Gegenstelle XFF fälschen kann.

    Ist die Socket-Gegenstelle nicht vertrauenswürdig, werden alle Weiterleitungs-Header ignoriert.
    Bei einem vertrauenswürdigen Proxy die X-Forwarded-For-Kette von nah nach fern durchgehen und
    den ersten nicht vertrauenswürdigen Hop zurückgeben. Eine fehlerhafte Kette fällt auf die
    direkte Gegenstelle zurück, den vorsichtigen gemeinsamen Proxy-Eimer.
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
    """Direktes TLS oder eine einzelne HTTPS-Zusicherung eines erlaubten Proxys prüfen."""
    if request.scope.get("scheme", "").lower() == "https":
        return True

    peer = socket_peer(request)
    if not _is_trusted(peer, trusted_proxies):
        return False

    forwarded_proto = request.headers.get("x-forwarded-proto", "")
    # Keine kommagetrennte Kette und keine mehrdeutigen Proxy-Werte akzeptieren.
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
    """Threadsicherer, begrenzter Sliding-Window-Limiter für einen einzelnen App-Prozess.

    Dieser Limiter taugt nur, solange Kassensturz als ein Anwendungsprozess läuft.
    Installationen mit mehreren Workern müssen ihn durch einen gemeinsamen Zustand
    ersetzen (zum Beispiel einen transaktionalen Limiter auf SQLite-Basis), bevor die
    APIs der Handy-App eingeschaltet werden. Ist die Eimertabelle voll, werden unbekannte
    Schlüssel abgelehnt, bis Eimer ablaufen; der Limiter verdrängt nie einen lebenden Eimer,
    um einem Angreifer Platz zu machen.
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
        """Einen Versuch verbrauchen und die Wartezeit zurückgeben, wenn der Schlüssel begrenzt ist."""
        if not isinstance(key, str) or not key.strip():
            raise ValueError("rate-limit key must be a non-empty string")
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive integer")
        if (
            isinstance(window_seconds, bool)
            or not isinstance(window_seconds, (int, float))
            or not math.isfinite(window_seconds)
            or window_seconds <= 0
        ):
            raise ValueError("window_seconds must be a positive finite number")

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
    """Einen Limiter-Schlüssel mit Namensraum aus dem ermittelten Netz-Client bauen."""
    if not scope or not scope.strip():
        raise ValueError("rate-limit scope must be non-empty")
    address = effective_client_ip(request, trusted_proxies)
    # Fehlende oder ungültige Angaben zur Gegenstelle teilen sich einen vorsichtigen Eimer.
    return f"{scope.strip()}:{address.compressed if address else 'unknown'}"
