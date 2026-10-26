"""Team Launchpad: turn a pasted link into an opportunity the matching agents can work with.

1. If the link (or an opportunity number in it) is already in the Radar, use that record.
2. Grants.gov and NIH Guide links are looked up through the official Grants.gov API, exactly like the weekly run.
3. Any other page is fetched once (respecting robots.txt) and saved as a "user-added" opportunity. Its details are
   whatever the page itself says: nothing is filled in or guessed, and it is flagged as not checked with the funder.
User-added opportunities are kept out of the main Opportunities list and funder pages.
"""
from __future__ import annotations

import re
from datetime import date
from urllib.parse import parse_qs, urlparse

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.radar.candidate import Candidate, normalize_number, normalize_url
from backend.radar.collectors import grants_gov
from backend.radar.http import Fetcher, SourceUnavailable, now
from backend.radar.models import DiscoveryRun, FundingSource, Opportunity, Sighting
from backend.radar.pipeline import load_registry, seed, upsert
from backend.radar.sanitize import html_to_text, strip_injections

USER_SOURCE = "user-added"
NUMBER = re.compile(r"\b([A-Z]{2,4}-[A-Z]{2}-\d{2}-\d{3})\b", re.I)


class ImportError_(Exception):
    """A link that can't be used, with a message meant for the person who pasted it."""


def _registry():
    return load_registry()


def _source(db: Session, slug: str) -> FundingSource:
    src = db.scalar(select(FundingSource).filter_by(slug=slug))
    if src is None and slug == USER_SOURCE:
        src = FundingSource(slug=USER_SOURCE, name="Added from a link (Team Launchpad)", official_url="https://", access_method="manual",
                            enabled=False, notes="Pages people pasted into the Team Launchpad. Not checked with the funder.")
        db.add(src)
        db.flush()
    return src


def find_existing(db: Session, url: str) -> Opportunity | None:
    u = normalize_url(url)
    for o in db.scalars(select(Opportunity).where(or_(Opportunity.official_url.is_not(None), Opportunity.application_url.is_not(None)))):
        if u in {normalize_url(o.official_url or ""), normalize_url(o.application_url or "")}:
            return o
    s = db.scalar(select(Sighting).where(Sighting.source_url.is_not(None)).where(Sighting.source_url.ilike(f"%{urlparse(url).path}%"))) \
        if urlparse(url).path not in ("", "/") else None
    if s and normalize_url(s.source_url) == u:
        return s.opportunity
    gid = grants_gov_id(url)
    if gid:
        s = db.scalar(select(Sighting).filter_by(external_ref=gid))
        if s:
            return s.opportunity
    m = NUMBER.search(url)
    if m:
        return db.scalar(select(Opportunity).filter_by(opportunity_number=normalize_number(m.group(1)))) or \
            db.scalar(select(Opportunity).where(Opportunity.opportunity_number.ilike(m.group(1))))
    return None


def grants_gov_id(url: str) -> str | None:
    p = urlparse(url)
    if "grants.gov" not in p.netloc:
        return None
    m = re.search(r"/search-results-detail/(\d+)", p.path)
    if m:
        return m.group(1)
    q = parse_qs(p.query)
    return (q.get("oppId") or q.get("oppid") or [None])[0]


def _save(db: Session, c: Candidate, slug: str) -> Opportunity:
    sources = {slug: _source(db, slug)}
    run = DiscoveryRun(mode="user_link", started_at=now(), status="success", summary='{"scope": "user_link"}')
    db.add(run)
    db.flush()
    _, opp = upsert(db, c.uid, [c], sources, run, date.today())
    run.finished_at = now()
    db.commit()
    return opp


def import_link(db: Session, url: str, fetcher=None) -> tuple[Opportunity, str]:
    """Returns (opportunity, how) where how is 'existing' | 'grants_gov' | 'page'."""
    url = url.strip()
    if not re.match(r"^https?://[^\s/]+\.[^\s]+", url):
        raise ImportError_("That doesn't look like a web link. Paste the full address, starting with https://")
    found = find_existing(db, url)
    if found:
        return found, "existing"

    reg = _registry()
    fetcher = fetcher or Fetcher(reg["user_agent"])
    gg = next(s for s in reg["sources"] if s["id"] == "grants-gov")
    seed(db, reg)

    gid = grants_gov_id(url)
    m = NUMBER.search(url)
    try:
        if not gid and m:
            hits = grants_gov.search_number(fetcher, gg, m.group(1))
            gid = str(hits[0]["id"]) if hits else None
            hit = hits[0] if hits else {}
        else:
            hit = {}
        if gid:
            detail = grants_gov.fetch_detail(fetcher, gg, gid)
            c = grants_gov.build(hit or {"id": gid}, detail, "grants-gov", now())
            opp = find_existing(db, c.official_url) or db.scalar(select(Opportunity).filter_by(uid=c.uid))
            return (opp, "existing") if opp else (_save(db, c, "grants-gov"), "grants_gov")
    except (SourceUnavailable, RuntimeError, KeyError, ValueError):
        pass  # fall through to reading the page itself

    try:
        r = fetcher.get(url, min_interval=1.0)
    except SourceUnavailable as e:
        raise ImportError_(f"We couldn't open that page ({e}). If the site blocks automated access, pick the opportunity from the list instead.")
    html = r.text
    title = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S | re.I) or re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    title_text = re.sub(r"\s+", " ", html_to_text(title.group(1))).strip() if title else ""
    text, removed = strip_injections(html_to_text(html))
    if not title_text or len(text) < 200:
        raise ImportError_("That page doesn't have enough text to work with. Try the funder's main announcement page.")
    c = Candidate(source_slug=USER_SOURCE, title=title_text[:300], official_url=url, retrieved_at=now(), description=text[:6000],
                  status=None, verification_status="unverified",
                  review_reasons=["Added from a link in the Team Launchpad; details are only what that page says"],
                  suspicious=bool(removed))
    m2 = NUMBER.search(text)
    if m2:
        c.opportunity_number = m2.group(1).upper()
    return _save(db, c, USER_SOURCE), "page"
