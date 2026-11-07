"""Recherche nach offiziellen Anbieter-Kontaktseiten.

Die Suche liefert nur Kandidaten und Quellenhinweise. Sie behauptet niemals,
dass eine gefundene Adresse ein bestätigter Kündigungskontakt ist.
"""
from __future__ import annotations

from html.parser import HTMLParser
import http.client
import ipaddress
import socket
import ssl
from urllib.parse import parse_qs, urlparse

import requests

SEARCH_URL = "https://html.duckduckgo.com/html/"
TIMEOUT = (3.05, 8)
MAX_RESPONSE_BYTES = 1_000_000
MAX_RESULTS = 8
USER_AGENT = "Kassensturz/0.3 (provider contact discovery)"


class _ResultsParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.results = []
        self._current = None
        self._capture = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set((attrs.get("class") or "").split())
        if tag == "a" and "result__a" in classes:
            self._current = {"title": "", "url": attrs.get("href", ""), "snippet": ""}
            self._capture = "title"
        elif self._current and tag in ("a", "div") and "result__snippet" in classes:
            self._capture = "snippet"

    def handle_data(self, data):
        if self._current and self._capture:
            self._current[self._capture] += data

    def handle_endtag(self, tag):
        if self._current and tag == "a" and self._capture == "title":
            self._capture = None
            self.results.append(self._current)
            self._current = None
        elif self._current and tag == "div" and self._capture == "snippet":
            self._capture = None


def _result_url(raw: str) -> str | None:
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https"):
        return None
    if parsed.hostname and parsed.hostname.endswith("duckduckgo.com"):
        target = parse_qs(parsed.query).get("uddg", [None])[0]
        if not target:
            return None
        parsed = urlparse(target)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return None
    host = parsed.hostname.lower()
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        return None
    return parsed.geturl()


def search_provider(provider_name: str) -> dict:
    """Sucht öffentliche Treffer; Kundendaten werden ausdrücklich nicht übergeben."""
    provider_name = " ".join((provider_name or "").split())[:120]
    if len(provider_name) < 2:
        raise ValueError("Anbietername fehlt oder ist zu kurz.")

    query = f'"{provider_name}" Kündigung Kontakt Impressum'
    response = requests.get(
        SEARCH_URL,
        params={"q": query},
        headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
        timeout=TIMEOUT,
        allow_redirects=False,
        stream=True,
    )
    try:
        if response.status_code != 200:
            raise RuntimeError("Die Anbietersuche ist momentan nicht erreichbar.")
        chunks = []
        size = 0
        for chunk in response.iter_content(16_384):
            size += len(chunk)
            if size > MAX_RESPONSE_BYTES:
                raise RuntimeError("Die Suchantwort ist unerwartet groß.")
            chunks.append(chunk)
        html = b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")
    finally:
        response.close()

    parser = _ResultsParser()
    parser.feed(html)
    seen = set()
    results = []
    for item in parser.results:
        url = _result_url(item["url"])
        title = " ".join(item["title"].split())[:200]
        if not url or not title or url in seen:
            continue
        seen.add(url)
        host = urlparse(url).hostname or ""
        results.append({
            "title": title,
            "url": url,
            "domain": host,
            "snippet": " ".join(item["snippet"].split())[:500],
            "source_type": "official_candidate",
            "verified": False,
        })
        if len(results) >= MAX_RESULTS:
            break

    return {
        "provider_name": provider_name,
        "query": query,
        "status": "candidates_found" if results else "no_results",
        "results": results,
        "notice": "Suchtreffer sind ungeprüfte Kandidaten. Kontaktdaten erst nach Prüfung einer offiziellen Anbieterquelle übernehmen.",
    }


def inspect_public_https_url(raw_url: str) -> dict:
    """Prüft URL-Form und DNS-Ziele, ohne die Zielseite abzurufen.

    Dies ist eine SSRF-Vorprüfung, keine Bestätigung der Anbieteridentität.
    Ein späterer Abruf muss DNS-Ziele beim Verbindungsaufbau erneut absichern.
    """
    parsed = urlparse((raw_url or "").strip())
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
        or parsed.fragment
    ):
        raise ValueError("Nur HTTPS-URLs auf Port 443 ohne Zugangsdaten sind erlaubt.")

    host = parsed.hostname.rstrip(".").lower()
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        raise ValueError("IP-Adressen sind als Quellenziel nicht zulässig.")

    if host == "localhost" or host.endswith((".localhost", ".local", ".internal", ".home", ".lan")):
        raise ValueError("Lokale Hostnamen sind als Quellenziel nicht zulässig.")

    try:
        records = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except (OSError, socket.gaierror):
        raise ValueError("Der Hostname konnte nicht sicher aufgelöst werden.") from None

    addresses = sorted({record[4][0] for record in records})
    if not addresses:
        raise ValueError("Der Hostname besitzt keine auflösbare öffentliche Adresse.")
    for address in addresses:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
        if not ip.is_global:
            raise ValueError("Der Hostname verweist auf eine nicht öffentliche Netzwerkadresse.")

    return {
        "host": host,
        "addresses": addresses,
        "status": "public_host_only",
        "verified": False,
        "notice": "Nur die öffentliche DNS-Auflösung wurde geprüft. Anbieterzugehörigkeit und Kontaktangaben sind damit nicht bestätigt.",
    }


MAX_PAGE_BYTES = 512_000
PAGE_TIMEOUT = 6


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS connection that connects to a prevalidated IP but verifies host TLS."""

    def __init__(self, host: str, address: str, timeout: int):
        super().__init__(host, port=443, timeout=timeout, context=ssl.create_default_context())
        self._pinned_address = address

    def connect(self):
        raw = socket.create_connection((self._pinned_address, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except Exception:
            raw.close()
            raise


class _PageEvidenceParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = []
        self.emails = set()
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag.lower() == "title":
            self._in_title = True
        href = attrs.get("href", "")
        if isinstance(href, str) and href.lower().startswith("mailto:"):
            address = href[7:].split("?", 1)[0].strip()
            if len(address) <= 254 and "@" in address and not any(ch.isspace() for ch in address):
                self.emails.add(address)

    def handle_endtag(self, tag):
        if tag.lower() == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title.append(data)


def fetch_public_page_evidence(raw_url: str) -> dict:
    """Fetches a small HTML page through a DNS-pinned, TLS-verified connection.

    Redirects are intentionally not followed. The page and extracted data remain
    untrusted evidence; this function never marks a provider contact verified.
    """
    checked = inspect_public_https_url(raw_url)
    parsed = urlparse(raw_url)
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    last_error = None
    response = None
    connection = None
    for address in checked["addresses"]:
        try:
            connection = _PinnedHTTPSConnection(checked["host"], address, PAGE_TIMEOUT)
            connection.request(
                "GET",
                path,
                headers={
                    "Host": checked["host"],
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml",
                    "Connection": "close",
                },
            )
            response = connection.getresponse()
            break
        except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
            last_error = exc
            if connection:
                connection.close()
            connection = None
    if response is None:
        raise RuntimeError("Die öffentliche Webseite konnte nicht sicher abgerufen werden.") from last_error

    try:
        if response.status in (301, 302, 303, 307, 308):
            raise RuntimeError("Die Webseite leitet weiter. Bitte Zieladresse separat prüfen.")
        if response.status != 200:
            raise RuntimeError(f"Die Webseite antwortet mit HTTP {response.status}.")
        content_type = (response.getheader("Content-Type") or "").lower()
        if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
            raise RuntimeError("Die Quelle liefert kein HTML-Dokument.")
        declared_length = response.getheader("Content-Length")
        if declared_length and declared_length.isdigit() and int(declared_length) > MAX_PAGE_BYTES:
            raise RuntimeError("Die Webseite ist für die begrenzte Prüfung zu groß.")
        body = response.read(MAX_PAGE_BYTES + 1)
        if len(body) > MAX_PAGE_BYTES:
            raise RuntimeError("Die Webseite überschreitet die erlaubte Antwortgröße.")
        charset = "utf-8"
        for part in content_type.split(";")[1:]:
            if part.strip().startswith("charset="):
                charset = part.split("=", 1)[1].strip().strip('"')[:40]
        try:
            html = body.decode(charset, errors="replace")
        except LookupError:
            html = body.decode("utf-8", errors="replace")
        parser = _PageEvidenceParser()
        parser.feed(html)
        return {
            "url": raw_url,
            "host": checked["host"],
            "http_status": response.status,
            "page_title": " ".join(" ".join(parser.title).split())[:200],
            "emails_found": sorted(parser.emails)[:20],
            "status": "page_fetched_unverified",
            "verified": False,
            "notice": "Die Seite wurde über eine geprüfte öffentliche IP mit TLS-Hostprüfung abgerufen. Inhalt und E-Mail-Adressen sind ungeprüfte Hinweise, keine bestätigten Anbieterkontakte.",
        }
    finally:
        if connection:
            connection.close()
