"""Home page: YIGH institutional content (config/yigh_profile.json), live system figures, and YIGH news
from the official YIGH news RSS feed (cached for 6 hours)."""
from __future__ import annotations

import json
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.radar.http import Fetcher, SourceUnavailable
from backend.radar.sanitize import html_to_text, strip_injections

from .constellation_api import dashboard
from .database import get_db

router = APIRouter(tags=["Home"])
PROFILE = Path(__file__).resolve().parents[2] / "config" / "yigh_profile.json"
NEWS_RSS = "https://medicine.yale.edu/yigh/news-rss/?title=News%20from%20around%20Yale%20and%20the%20World&orgId=118812"
_news_cache: dict = {"at": 0.0, "items": []}


def yigh_news(limit: int = 6) -> list[dict]:
    if time.time() - _news_cache["at"] < 6 * 3600 and _news_cache["items"]:
        return _news_cache["items"][:limit]
    try:
        r = Fetcher("YIGH-Radar/1.0 (Yale Institute for Global Health; research use)").get(NEWS_RSS, min_interval=1.0)
        root = ET.fromstring(r.text)
    except (SourceUnavailable, ET.ParseError):
        return _news_cache["items"][:limit]  # serve stale rather than nothing
    items = []
    for it in root.iter("item"):
        content = next((c for c in it if c.tag.endswith("content")), None)
        desc, _ = strip_injections(html_to_text(it.findtext("description") or ""))
        items.append({"title": (it.findtext("title") or "").strip(), "url": (it.findtext("link") or "").strip(),
                      "summary": desc[:280], "date": it.findtext("pubDate"),
                      "image": content.get("url") if content is not None else None,
                      "image_alt": content.get("alt") if content is not None else None})
    _news_cache.update(at=time.time(), items=items)
    return items[:limit]


@router.get("/api/home")
def home(db: Session = Depends(get_db)):
    return {"profile": json.loads(PROFILE.read_text()), "live": dashboard(db), "news": yigh_news(3),
            "news_source": "https://medicine.yale.edu/yigh/news"}
