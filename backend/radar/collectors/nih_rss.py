"""NIH Guide RSS feed of funding opportunities. NOFO numbers are resolved on Grants.gov for
structured, verifiable details; items not yet on Grants.gov are kept but flagged for review."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from ..candidate import Candidate
from ..extract import parse_date
from ..http import SourceUnavailable
from ..sanitize import strip_injections
from . import grants_gov

NOFO = re.compile(r"\b((?:RFA|PAR|PA|OTA)-(?:[A-Z]{2}-)?\d{2}-\d{3})\b")  # RFA-TW-27-001, PAR-27-050


def collect(fetcher, cfg, ctx) -> list[Candidate]:
    r = fetcher.get(cfg["endpoint"], min_interval=cfg.get("min_interval_seconds", 1.0))
    root = ET.fromstring(r.text)
    gg_cfg = ctx["sources"]["grants-gov"]
    out = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip().replace("http://", "https://")
        if "/notice-files/" in link or re.match(r"(?i)notice\b", title):
            continue  # notices (NOT-…) amend opportunities; they are not opportunities themselves
        m = NOFO.search(link) or NOFO.search(title)
        if not m:
            continue
        number = m.group(1)
        try:
            hits = [h for h in grants_gov.search_number(fetcher, gg_cfg, number) if h.get("number", "").upper() == number]
        except SourceUnavailable:
            hits = []  # lookup failed for this item only; keep it as RSS-only and flag for review
        if hits:
            detail = grants_gov.fetch_detail(fetcher, gg_cfg, hits[0]["id"])
            c = grants_gov.build(hits[0], detail, cfg["id"], r.retrieved_at)
            c.official_url = link or c.official_url  # NIH Guide is the publisher of record for NIH NOFOs
            if not grants_gov.is_relevant(c, ctx["classify"]):
                continue
            out.append(c)
            continue
        clean_title, removed = strip_injections(title)
        c = Candidate(source_slug=cfg["id"], title=clean_title or number, official_url=link, retrieved_at=r.retrieved_at,
                      external_ref=number, opportunity_number=number, funder_slug="nih", funder_name="National Institutes of Health",
                      application_url=link, posted_date=parse_date((item.findtext("pubDate") or "")[5:16]), status=None)
        c.review_reasons.append("Listed in the NIH Guide but not yet found on Grants.gov: deadline, amount and eligibility not verified")
        c.suspicious = bool(removed)
        if grants_gov.is_relevant(c, ctx["classify"]):
            out.append(c)
    return out
