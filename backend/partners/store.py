"""Partner records: dedupe/upsert and guarded creation of documented Yale relationships."""
from __future__ import annotations

import difflib
import json
import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Evidence, Org, YaleLink

ROR_TYPE_MAP = {"education": "university", "facility": "research_institute", "government": "ministry_public_health",
                "healthcare": "healthcare", "nonprofit": "ngo", "company": "technology", "funder": "other", "archive": "other", "other": "other"}
MULTILATERAL = re.compile(r"World Health Organization|\bWHO\b|UNICEF|World Bank|Africa CDC|Pan American Health|Gavi|Global Fund|"
                          r"United Nations|\bUN\b|African Union|ECOWAS|West African Health Organisation|Unitaid", re.I)


class PartnershipEvidenceError(ValueError):
    """Raised when someone tries to record a Yale relationship without public evidence."""


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def norm(name: str) -> str:
    n = re.sub(r"\(.*?\)", "", name.lower())
    n = re.sub(r"\b(the|of|and|for|&)\b", " ", n)
    return re.sub(r"[^a-z0-9]+", " ", n).strip()


def classify_type(name: str, ror_types: list[str] | None) -> str:
    if MULTILATERAL.search(name):
        return "multilateral"
    if re.search(r"ministry of health|public health (?:agency|institute)|national institute of public health|centre for disease control|CDC\b", name, re.I):
        return "ministry_public_health"
    if re.search(r"hospital|clinic|health (?:system|centre|center)", name, re.I) and "university" not in name.lower():
        return "healthcare"
    if re.search(r"universit|college|school of", name, re.I):
        return "university"
    if re.search(r"institut|research|laborator|centre|center", name, re.I):
        return "research_institute"
    for t in ror_types or []:
        if t in ROR_TYPE_MAP:
            return ROR_TYPE_MAP[t]
    return "other"


def find_org(db: Session, name: str, country: str | None, ror_id: str | None) -> Org | None:
    if ror_id:
        o = db.scalar(select(Org).filter_by(ror_id=ror_id))
        if o:
            return o
    n = norm(name)
    for o in db.scalars(select(Org).filter_by(norm_name=n)):
        if not country or not o.country or o.country == country:
            return o
    for o in db.scalars(select(Org).filter_by(country=country)) if country else []:
        aliases = [norm(a) for a in json.loads(o.aliases or "[]")]
        if n in aliases or difflib.SequenceMatcher(None, n, o.norm_name).ratio() >= 0.93:
            return o
    return None


def upsert_org(db: Session, *, name: str, country: str | None, origin: str, ror: dict | None = None,
               description: str | None = None, website: str | None = None, aliases: list[str] | None = None) -> Org:
    ror_id = ror["id"] if ror else None
    o = find_org(db, name, country, ror_id)
    if o is None:
        o = Org(name=name, norm_name=norm(name), country=country, origin=origin, created_at=now(), org_type="other")
        db.add(o)
    if ror:
        o.ror_id = ror_id
        o.country = ror["country"] or o.country
        o.country_code = ror.get("country_code") or o.country_code
        o.website = ror.get("website") or o.website
        o.ror_types = json.dumps(ror.get("types", []))
        aliases = (aliases or []) + ror.get("names", [])
    if website and not o.website:
        o.website = website
    if description and (not o.description or len(description) > len(o.description)):
        o.description = description
    o.aliases = json.dumps(sorted(set(json.loads(o.aliases or "[]")) | set(aliases or []) | {name}))
    o.org_type = classify_type(o.name, json.loads(o.ror_types or "[]"))
    o.last_verified_at = now()
    db.flush()
    return o


def add_evidence(db: Session, org: Org, kind: str, url: str, quote: str | None) -> Evidence:
    if not url or not url.startswith("http"):
        raise PartnershipEvidenceError("evidence needs a public URL")
    ev = db.scalar(select(Evidence).filter_by(org_id=org.id, kind=kind, url=url))
    if ev is None:
        ev = Evidence(org=org, kind=kind, url=url, quote=quote, retrieved_at=now())
        db.add(ev)
    else:
        ev.quote, ev.retrieved_at = quote or ev.quote, now()
    db.flush()
    return ev


def add_yale_link(db: Session, org: Org, *, link_type: str, evidence: Evidence | None, faculty_id=None, faculty_name=None,
                  detail=None) -> YaleLink:
    """The ONLY way a documented relationship is created: it must cite a Yale-partnership or project evidence URL."""
    if evidence is None or evidence.kind not in ("yale_partnership", "project") or not evidence.url.startswith("http"):
        raise PartnershipEvidenceError(f"refusing to record a Yale relationship for {org.name} without public evidence")
    link = db.scalar(select(YaleLink).filter_by(org_id=org.id, link_type=link_type, faculty_name=faculty_name, evidence_id=evidence.id))
    if link is None:
        link = YaleLink(org=org, link_type=link_type, faculty_id=faculty_id, faculty_name=faculty_name, detail=detail, evidence=evidence)
        db.add(link)
    db.flush()
    return link
