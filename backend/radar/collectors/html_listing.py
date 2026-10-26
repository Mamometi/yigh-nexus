"""Server-rendered listing pages (no API/feed available). Each linked call page is read from the
funder's own site; deadline, amount and eligibility are copied only when they appear next to an
explicit label, with the snippet kept as evidence."""
from __future__ import annotations

import re
from datetime import date
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..candidate import Candidate
from ..extract import find_amount, find_deadline, find_eligibility
from ..sanitize import INJECTION, strip_injections, visible_text

HEALTH = re.compile(r"health|disease|medic|epidemi|nutrition|climate|pandemic|vaccin|maternal|mental|infect", re.I)
CLOSED = re.compile(r"\b(?:this call (?:is|has) (?:now )?closed|applications? (?:are|is) (?:now )?closed|call closed|competition closed)\b", re.I)


def collect(fetcher, cfg, ctx) -> list[Candidate]:
    listing = fetcher.get(cfg["endpoint"], min_interval=cfg.get("min_interval_seconds", 5.0))
    soup = BeautifulSoup(listing.text, "html.parser")
    pattern = re.compile(cfg["link_pattern"])
    links = {}
    for a in soup.select("a[href]"):
        href = a["href"].split("#")[0]
        path = re.sub(r"^https?://[^/]+", "", href)
        if pattern.search(path):
            links.setdefault(urljoin(cfg["endpoint"], href), a.get_text(" ", strip=True))
    out = []
    for url, link_text in list(links.items())[: ctx.get("max_pages", 30)]:
        page = fetcher.get(url, min_interval=cfg.get("min_interval_seconds", 5.0))
        text = visible_text(page.text)
        clean, removed = strip_injections(text)
        title = BeautifulSoup(page.text, "html.parser").find("h1")
        title = (title.get_text(" ", strip=True) if title else link_text) or link_text
        if INJECTION.search(title):
            title = link_text
        if not HEALTH.search(f"{title} {clean}"):
            continue
        deadline, deadline_snip = find_deadline(clean)
        amount = find_amount(clean)
        elig = find_eligibility(clean)
        c = Candidate(source_slug=cfg["id"], title=title, official_url=url, retrieved_at=page.retrieved_at,
                      external_ref=url, funder_slug=cfg.get("funder"), description=clean[:1500],
                      deadline=deadline, deadline_text=deadline_snip, award_text=amount, eligibility=elig,
                      application_url=url, verification_method="official_page", verification_url=url)
        if CLOSED.search(clean):
            c.status = "closed"
        elif deadline:
            c.status = "open"
        c.verification_details = {
            "deadline": {"verified": bool(deadline_snip), "evidence": deadline_snip},
            "award": {"verified": bool(amount), "evidence": amount},
            "eligibility": {"verified": bool(elig), "evidence": (elig or "")[:200]},
        }
        c.verification_status = "partially_verified" if (deadline_snip or amount or elig) else "unverified"
        if not deadline_snip:
            c.review_reasons.append("No labelled deadline found on the official page")
        if not elig:
            c.review_reasons.append("Eligibility not found on the official page")
        if not amount:
            c.review_reasons.append("Award amount not found on the official page")
        if c.status is None:
            c.review_reasons.append("Status could not be determined from the page")
        if removed:
            c.suspicious = True
            c.review_reasons.append(f"Page contained {len(removed)} instruction-like sentence(s); they were ignored and removed")
        out.append(c)
    return out
