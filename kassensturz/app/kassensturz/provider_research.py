"""Recherche nach offiziellen Anbieter-Kontaktseiten.

Die Suche liefert nur Kandidaten und Quellenhinweise. Sie behauptet niemals,
dass eine gefundene Adresse ein bestätigter Kündigungskontakt ist.
"""
from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import parse_qs, quote_plus, urlparse

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
