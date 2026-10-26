"""Collect faculty headshots from their public Yale profile pages.

Reads each profile's og:image (the photo Yale publishes for the page) politely: robots.txt is respected and
requests are spaced out. An image shared by several profiles is the site's default, not a headshot, so it is
dropped and those faculty get the generic avatar on the site. Output: data/faculty_photos.json {faculty_id: url}.

    .venv/bin/python -m backend.app.scrape_photos
"""
from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

from backend.radar.http import Fetcher, SourceUnavailable

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "faculty_photos.json"
OG = re.compile(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', re.I)
UA = "YIGH-Nexus/1.0 (Yale Institute for Global Health student project; faculty directory photos)"


def headshot(url: str) -> str:
    """Ask Cloudinary for a square-ish portrait instead of the 1200x630 social card."""
    return re.sub(r"/image/upload/[^/]*/", "/image/upload/c_fill,g_face,h_480,w_480,f_auto,q_auto/", url) \
        if "cloudinary.com" in url else url


def main() -> None:
    con = sqlite3.connect(ROOT / "data" / "yigh.db")
    rows = con.execute("select id, source_url from faculty order by id").fetchall()
    done = json.loads(OUT.read_text()) if OUT.exists() else {}
    raw = done.get("_raw", {})
    f = Fetcher(UA)
    for i, (fid, url) in enumerate(rows, 1):
        if str(fid) in raw:
            continue
        try:
            m = OG.search(f.get(url, min_interval=1.5).text)
            raw[str(fid)] = m.group(1) if m else None
        except SourceUnavailable as e:
            raw[str(fid)] = None
            print(f"  {fid}: {e}")
        if i % 25 == 0:
            OUT.write_text(json.dumps({"_raw": raw}, indent=1))
            print(f"{i}/{len(rows)}")
    shared = {u for u, n in Counter(v for v in raw.values() if v).items() if n > 2}
    photos = {k: headshot(v) for k, v in raw.items() if v and v not in shared}
    OUT.write_text(json.dumps({"photos": photos, "_raw": raw, "_defaults_dropped": sorted(shared)}, indent=1))
    print(f"photos for {len(photos)} of {len(rows)} faculty; {len(shared)} default image(s) dropped")


if __name__ == "__main__":
    main()
