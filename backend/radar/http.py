"""Polite HTTP access: robots.txt, per-host rate limits, retries, timeouts.

Collectors only talk to the network through a Fetcher, so tests can swap in FixtureFetcher.
"""
from __future__ import annotations

import json
import re
import time
import urllib.robotparser
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx


class SourceUnavailable(Exception):
    """Network error, timeout, 4xx/5xx, or disallowed by robots.txt."""
    def __init__(self, msg, status: int | None = None):
        super().__init__(msg)
        self.status = status


class BlockedByRobots(SourceUnavailable):
    pass


@dataclass
class Response:
    url: str
    status: int
    text: str
    retrieved_at: datetime

    def json(self):
        return json.loads(self.text)


def now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Fetcher:
    def __init__(self, user_agent: str, timeout: float = 30, retries: int = 2):
        self.ua = user_agent
        self.client = httpx.Client(timeout=timeout, follow_redirects=True, headers={"User-Agent": user_agent})
        self.retries = retries
        self._last: dict[str, float] = {}
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}

    def _robots_for(self, url: str):
        host = urlparse(url)
        key = f"{host.scheme}://{host.netloc}"
        if key not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                r = self.client.get(key + "/robots.txt")
                rp.parse(r.text.splitlines() if r.status_code == 200 else [])
            except httpx.HTTPError:
                rp.parse([])
            self._robots[key] = rp
        return self._robots[key]

    def _wait(self, url: str, min_interval: float):
        host = urlparse(url).netloc
        rp = self._robots_for(url)
        delay = max(min_interval, (rp.crawl_delay(self.ua) or 0) if rp else 0)
        elapsed = time.monotonic() - self._last.get(host, 0)
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self._last[host] = time.monotonic()

    def get(self, url: str, *, min_interval: float = 1.0, check_robots: bool = True) -> Response:
        if check_robots and not self._robots_for(url).can_fetch(self.ua, url):
            raise BlockedByRobots(f"robots.txt disallows {url}")
        return self._request("GET", url, min_interval=min_interval)

    def post_json(self, url: str, payload: dict, *, min_interval: float = 1.0) -> Response:
        # Official APIs: robots.txt governs crawlers, not documented API endpoints.
        return self._request("POST", url, min_interval=min_interval, json=payload)

    def _request(self, method, url, *, min_interval, **kw) -> Response:
        last_err = None
        for attempt in range(self.retries + 1):
            self._wait(url, min_interval)
            try:
                r = self.client.request(method, url, **kw)
                if r.status_code in (429, 500, 502, 503, 504) and attempt < self.retries:
                    time.sleep(2 ** attempt * 2)
                    continue
                if r.status_code >= 400:
                    raise SourceUnavailable(f"HTTP {r.status_code} for {url}", status=r.status_code)
                return Response(str(r.url), r.status_code, r.text, now())
            except httpx.HTTPError as e:
                last_err = e
                time.sleep(2 ** attempt)
        raise SourceUnavailable(f"{method} {url} failed: {last_err}")


class FixtureFetcher:
    """Serves saved responses from a directory (tests / offline demos).

    fixtures/<name>.json maps request keys to files: {"GET https://...": "file.html",
    "POST https://...|{json}": "file.json", "GET https://down.example": {"error": "HTTP 503"}}
    """
    def __init__(self, directory: str | Path, mapping: dict | None = None):
        self.dir = Path(directory)
        self.map = mapping if mapping is not None else json.loads((self.dir / "routes.json").read_text())
        self.requests: list[str] = []

    def _serve(self, key: str, url: str) -> Response:
        self.requests.append(key)
        target = self.map.get(key)
        if target is None:
            raise SourceUnavailable(f"no fixture for {key}")
        if isinstance(target, dict) and "error" in target:
            m = re.search(r"HTTP (\d{3})", target["error"])
            raise SourceUnavailable(target["error"], status=int(m.group(1)) if m else None)
        return Response(url, 200, (self.dir / target).read_text(), now())

    def get(self, url, **_):
        return self._serve(f"GET {url}", url)

    def post_json(self, url, payload, **_):
        ref = payload.get("opportunityId") or payload.get("oppNum") or payload.get("keyword") or ""
        for key in (f"POST {url}|{json.dumps(payload, sort_keys=True)}", f"POST {url}|{ref}", f"POST {url}|*"):
            if key in self.map:
                return self._serve(key, url)
        return self._serve(f"POST {url}|{ref}", url)
