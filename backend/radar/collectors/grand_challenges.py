"""Grand Challenges grant opportunities (grandchallenges.org, Gates Foundation and partner initiatives).

The listing is server-rendered: each opportunity is an <article> with a titled link, a status line
("Applications Open", "Coming Soon", "Closed") and a short description. Values are read from that
official listing only; deadlines and amounts are copied only when written there with a label.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ..candidate import Candidate
from ..extract import find_amount, find_deadline
from ..sanitize import INJECTION, strip_injections

STATUS = {"applications open": "open", "open": "open", "coming soon": "forecasted", "upcoming": "forecasted",
          "closed": "closed", "applications closed": "closed"}


def collect(fetcher, cfg, ctx) -> list[Candidate]:
    page = fetcher.get(cfg["endpoint"], min_interval=cfg.get("min_interval_seconds", 5.0))
    soup = BeautifulSoup(page.text, "html.parser")
    out = []
    for art in soup.find_all("article"):
        link = art.find("a", attrs={"aria-label": True}) or art.find("a", href=True)
        if not link:
            continue
        title = (link.get("aria-label") or link.get_text(" ", strip=True)).strip()
        if not title or INJECTION.search(title):
            continue
        texts = [t.strip() for t in art.stripped_strings]
        status_txt = next((t for t in texts if t.lower() in STATUS), None)
        body, removed = strip_injections(" ".join(t for t in texts if t != title and t != status_txt))
        initiative = None
        if "Initiative" in texts:
            i = texts.index("Initiative")
            initiative = texts[i + 1] if i + 1 < len(texts) else None
        desc = re.sub(r"^.*?\bDescription\b\s*", "", body) if "Description" in body else body
        deadline, dl_snip = find_deadline(desc)
        amount = find_amount(desc)
        c = Candidate(source_slug=cfg["id"], title=title, official_url=link["href"], retrieved_at=page.retrieved_at,
                      external_ref=link["href"], funder_slug=cfg.get("funder"), funder_name=initiative,
                      description=desc[:2000] or None, deadline=deadline, deadline_text=dl_snip, award_text=amount,
                      application_url=link["href"], status=STATUS.get((status_txt or "").lower()),
                      verification_method="official_page", verification_url=cfg["endpoint"])
        c.verification_details = {"status": {"verified": bool(status_txt), "evidence": status_txt},
                                  "deadline": {"verified": bool(dl_snip), "evidence": dl_snip},
                                  "award": {"verified": bool(amount), "evidence": amount}}
        c.verification_status = "partially_verified" if status_txt else "unverified"
        c.review_reasons.append("Listing summary only: open the call page for eligibility and full terms")
        if not dl_snip:
            c.review_reasons.append("No labelled deadline in the Grand Challenges listing")
        if removed:
            c.suspicious = True
            c.review_reasons.append(f"Removed {len(removed)} instruction-like sentence(s) from the listing")
        out.append(c)
    return out
