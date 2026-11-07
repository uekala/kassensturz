from kassensturz import provider_research


class FakeResponse:
    status_code = 200
    encoding = "utf-8"

    def __init__(self, body):
        self.body = body.encode()

    def iter_content(self, chunk_size):
        yield self.body

    def close(self):
        pass


def test_search_provider_returns_unverified_https_candidates(monkeypatch):
    captured = {}

    def fake_get(url, **kwargs):
        captured.update(kwargs)
        return FakeResponse("""
          <a class="result__a" href="https://www.example.de/kuendigung">Kündigung – Example</a>
          <div class="result__snippet">Kontakt für Kündigungen</div>
          <a class="result__a" href="http://unsafe.example.de/">Unsicher</a>
          <a class="result__a" href="https://evil.local/">Lokal</a>
        """)

    monkeypatch.setattr(provider_research.requests, "get", fake_get)
    result = provider_research.search_provider("Example GmbH")

    assert result["status"] == "candidates_found"
    assert len(result["results"]) == 1
    assert result["results"][0]["url"] == "https://www.example.de/kuendigung"
    assert result["results"][0]["verified"] is False
    assert "Kundennummer" not in captured["params"]["q"]
    assert captured["allow_redirects"] is False
    assert captured["timeout"] == provider_research.TIMEOUT


def test_result_url_rejects_redirects_and_non_https():
    assert provider_research._result_url("http://example.org") is None
    assert provider_research._result_url("https://user:pass@example.org") is None
    assert provider_research._result_url("https://localhost/admin") is None
    assert provider_research._result_url("https://duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.org%2Fcontact") == "https://example.org/contact"


def test_search_provider_requires_provider_name():
    import pytest

    with pytest.raises(ValueError):
        provider_research.search_provider(" ")



def test_public_url_preflight_rejects_private_and_non_https(monkeypatch):
    import pytest

    with pytest.raises(ValueError):
        provider_research.inspect_public_https_url("http://example.org")
    with pytest.raises(ValueError):
        provider_research.inspect_public_https_url("https://127.0.0.1/")
    with pytest.raises(ValueError):
        provider_research.inspect_public_https_url("https://user:pass@example.org/")


def test_public_url_preflight_checks_every_dns_address(monkeypatch):
    import socket
    import pytest

    public = ("93.184.216.34", 443)
    private = ("192.168.1.10", 443)
    monkeypatch.setattr(
        provider_research.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", public),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", private),
        ],
    )
    with pytest.raises(ValueError, match="nicht öffentliche"):
        provider_research.inspect_public_https_url("https://example.org/contact")


def test_public_url_preflight_reports_only_dns_check(monkeypatch):
    import socket

    monkeypatch.setattr(
        provider_research.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
        ],
    )
    result = provider_research.inspect_public_https_url("https://example.org/contact")
    assert result["status"] == "public_host_only"
    assert result["verified"] is False
