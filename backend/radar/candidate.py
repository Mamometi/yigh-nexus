"""A candidate opportunity as read from one source, before it is merged into the database."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from urllib.parse import urlsplit, urlunsplit

MATERIAL_FIELDS = ("title", "deadline", "deadline_text", "award_floor", "award_ceiling", "award_text", "eligibility",
                   "geographic_restrictions", "application_url", "status")


def normalize_number(num: str | None) -> str | None:
    if not num:
        return None
    n = re.sub(r"\s+", "", num.upper())
    return n or None


def normalize_url(url: str) -> str:
    p = urlsplit(url.strip())
    return urlunsplit((p.scheme.lower() or "https", p.netloc.lower().removeprefix("www."), p.path.rstrip("/"), p.query, ""))


@dataclass
class Candidate:
    source_slug: str
    title: str
    official_url: str
    retrieved_at: datetime
    external_ref: str | None = None          # source-specific id (e.g. Grants.gov opportunity id)
    opportunity_number: str | None = None
    funder_slug: str | None = None
    funder_name: str | None = None
    description: str | None = None
    deadline: date | None = None
    deadline_text: str | None = None
    award_floor: float | None = None
    award_ceiling: float | None = None
    award_text: str | None = None
    currency: str | None = None
    eligibility: str | None = None
    geographic_restrictions: str | None = None
    application_url: str | None = None
    posted_date: date | None = None
    status: str | None = None                # forecasted | open | closed | None (unknown)
    verification_status: str = "unverified"
    verification_method: str | None = None
    verification_url: str | None = None
    verification_details: dict = field(default_factory=dict)
    review_reasons: list[str] = field(default_factory=list)
    suspicious: bool = False

    @property
    def uid(self) -> str:
        num = normalize_number(self.opportunity_number)
        if num:
            return f"opp:{num}"
        return "url:" + hashlib.sha1(normalize_url(self.official_url).encode()).hexdigest()[:20]

    def material(self) -> dict:
        out = {}
        for f in MATERIAL_FIELDS:
            v = getattr(self, f)
            out[f] = v.isoformat() if isinstance(v, date) else v
        return out

    def content_hash(self) -> str:
        m = self.material()
        return hashlib.sha256(repr(sorted(m.items())).encode()).hexdigest()
