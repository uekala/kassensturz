import ipaddress
from collections import deque

import pytest
from starlette.requests import Request

from kassensturz.mobile_security import (
    InMemoryRateLimiter,
    effective_client_ip,
    parse_trusted_proxy_networks,
    request_is_https,
    request_rate_limit_key,
    socket_peer,
)


def make_request(
    peer: str,
    *,
    scheme: str = "http",
    headers: dict[str, str] | None = None,
) -> Request:
    raw_headers = [
        (key.lower().encode("latin-1"), value.encode("latin-1"))
        for key, value in (headers or {}).items()
    ]
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": scheme,
            "path": "/api/v1/me",
            "raw_path": b"/api/v1/me",
            "query_string": b"",
            "headers": raw_headers,
            "client": (peer, 50123),
            "server": ("kassensturz.local", 443 if scheme == "https" else 80),
        }
    )


def test_trusted_proxy_networks_parse_ipv4_ipv6_and_cidrs():
    networks = parse_trusted_proxy_networks("10.0.0.0/8, 2001:db8::/32, 192.0.2.10")

    assert len(networks) == 3
    assert ipaddress.ip_address("10.20.30.40") in networks[0]
    assert ipaddress.ip_address("2001:db8::5") in networks[1]
    assert ipaddress.ip_address("192.0.2.10") in networks[2]


def test_invalid_trusted_proxy_configuration_is_rejected():
    with pytest.raises(ValueError):
        parse_trusted_proxy_networks("10.0.0.0/8,not-an-ip")


def test_direct_https_is_accepted_without_proxy_headers():
    request = make_request("203.0.113.5", scheme="https")

    assert request_is_https(request) is True


def test_untrusted_forwarded_proto_cannot_upgrade_http_to_https():
    request = make_request(
        "203.0.113.5",
        headers={"X-Forwarded-Proto": "https"},
    )

    assert request_is_https(
        request,
        parse_trusted_proxy_networks("10.0.0.10"),
    ) is False


def test_configured_proxy_can_assert_https():
    trusted = parse_trusted_proxy_networks("10.0.0.10")
    request = make_request(
        "10.0.0.10",
        headers={"X-Forwarded-Proto": "https"},
    )

    assert request_is_https(request, trusted) is True


@pytest.mark.parametrize(
    "forwarded_proto",
    ["http", "https,http", "https, https", "", "HTTPS,HTTP"],
)
def test_trusted_proxy_must_send_one_unambiguous_https_value(forwarded_proto):
    request = make_request(
        "10.0.0.10",
        headers={"X-Forwarded-Proto": forwarded_proto},
    )

    assert request_is_https(
        request,
        parse_trusted_proxy_networks("10.0.0.10"),
    ) is False


def test_untrusted_peer_cannot_spoof_client_address_with_forwarded_for():
    request = make_request(
        "203.0.113.25",
        headers={"X-Forwarded-For": "172.30.32.2"},
    )

    assert socket_peer(request) == ipaddress.ip_address("203.0.113.25")
    assert effective_client_ip(request) == ipaddress.ip_address("203.0.113.25")


def test_trusted_proxy_chain_resolves_first_untrusted_hop():
    trusted = parse_trusted_proxy_networks("10.0.0.0/8")
    request = make_request(
        "10.0.0.10",
        headers={"X-Forwarded-For": "203.0.113.25, 10.0.0.20"},
    )

    assert effective_client_ip(request, trusted) == ipaddress.ip_address("203.0.113.25")


def test_malformed_forwarded_for_falls_back_to_proxy_peer():
    trusted = parse_trusted_proxy_networks("10.0.0.10")
    request = make_request(
        "10.0.0.10",
        headers={"X-Forwarded-For": "203.0.113.25, garbage"},
    )

    assert effective_client_ip(request, trusted) == ipaddress.ip_address("10.0.0.10")


def test_rate_limit_keys_are_scoped_and_network_derived():
    request = make_request(
        "203.0.113.25",
        headers={"X-Forwarded-For": "198.51.100.2"},
    )

    assert request_rate_limit_key(request, scope="pair") == "pair:203.0.113.25"
    assert request_rate_limit_key(request, scope="refresh") == "refresh:203.0.113.25"


def test_rate_limiter_allows_limit_then_denies_until_window_expires():
    current = [100.0]
    limiter = InMemoryRateLimiter(clock=lambda: current[0])

    first = limiter.hit("pair:203.0.113.25", limit=2, window_seconds=60)
    second = limiter.hit("pair:203.0.113.25", limit=2, window_seconds=60)
    third = limiter.hit("pair:203.0.113.25", limit=2, window_seconds=60)

    assert first.allowed is True and first.remaining == 1
    assert second.allowed is True and second.remaining == 0
    assert third.allowed is False and third.retry_after == 60

    current[0] += 60
    after_window = limiter.hit("pair:203.0.113.25", limit=2, window_seconds=60)
    assert after_window.allowed is True


def test_rate_limiter_has_a_bounded_fail_closed_key_table():
    current = [10.0]
    limiter = InMemoryRateLimiter(max_keys=1, clock=lambda: current[0])

    assert limiter.hit("pair:203.0.113.1", limit=1, window_seconds=30).allowed
    denied = limiter.hit("pair:203.0.113.2", limit=1, window_seconds=30)

    assert denied.allowed is False
    assert denied.retry_after == 30

    current[0] += 30
    allowed_after_expiry = limiter.hit(
        "pair:203.0.113.2",
        limit=1,
        window_seconds=30,
    )
    assert allowed_after_expiry.allowed is True


def test_rate_limiter_rejects_invalid_parameters():
    limiter = InMemoryRateLimiter()
    with pytest.raises(ValueError):
        limiter.hit("", limit=1, window_seconds=60)
    with pytest.raises(ValueError):
        limiter.hit("device", limit=0, window_seconds=60)
    with pytest.raises(ValueError):
        limiter.hit("device", limit=1, window_seconds=0)
