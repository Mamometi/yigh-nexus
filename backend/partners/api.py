"""External partner API + the integrated opportunity workspace (Radar + Nexus + partners)."""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from backend.nexus import api as nexus_api
from backend.radar.api import PRIORITY_NAMES, opportunity_detail
from backend.radar.models import Opportunity
from backend.nexus.shortlist import profile_opportunity

from .match import partners_for_recommendation
from .models import Org, YaleLink, make_session

router = APIRouter(tags=["External partners"])


def partner_db():
    """New session per call; callers in request handlers get their own connection."""
    return make_session()


def _org(o: Org) -> dict:
    return {"id": o.id, "name": o.name, "type": o.org_type, "country": o.country, "website": o.website, "ror_id": o.ror_id,
            "origin": o.origin, "last_verified": o.last_verified_at, "description": o.description,
            "expertise": sorted(json.loads(o.expertise or "{}")),
            "documented_yale_links": [{"type": l.link_type, "faculty_id": l.faculty_id, "faculty_name": l.faculty_name,
                                       "detail": l.detail, "evidence_url": l.evidence.url} for l in o.yale_links],
            "evidence": [{"kind": e.kind, "url": e.url, "quote": e.quote, "retrieved_at": e.retrieved_at} for e in o.evidence]}


@router.get("/api/partners")
def list_partners(country: Optional[str] = None, type: Optional[str] = None, q: Optional[str] = None,
                  documented: Optional[bool] = None):
    db = partner_db()
    rows = db.scalars(select(Org).order_by(Org.country, Org.name)).all()
    rows = [o for o in rows if (not country or o.country == country) and (not type or o.org_type == type)
            and (not q or q.lower() in (o.name + " " + (o.description or "")).lower())
            and (documented is None or bool(o.yale_links) == documented)]
    return {"count": len(rows), "partners": [_org(o) for o in rows]}


@router.get("/api/partners/{org_id}")
def get_partner(org_id: int):
    o = partner_db().get(Org, org_id)
    if o is None:
        raise HTTPException(404, "Organization not found")
    return _org(o)


@router.get("/api/faculty/{faculty_id}/partners")
def faculty_partners(faculty_id: int):
    """Constellation: external organizations with a documented link to this faculty member."""
    links = partner_db().scalars(select(YaleLink).filter_by(faculty_id=faculty_id)).all()
    return [{"organization": {"id": l.org.id, "name": l.org.name, "country": l.org.country, "type": l.org.org_type,
                              "website": l.org.website}, "link": l.detail, "evidence_url": l.evidence.url} for l in links]


@router.get("/api/radar/opportunities/{opp_id}/workspace")
def workspace(opp_id: int, mode: str = Query("auto", pattern="^(auto|ai|rules)$"), discover: bool = False):
    """Everything for one opportunity: details, recommended faculty, teams, external partners, gaps, sources."""
    with nexus_api.MATCHER_LOCK:
        return _workspace(opp_id, mode, discover)


def _missing(item: str) -> str:
    kind, _, what = item.partition(": ")
    return {"topic": f"No one suggested works on {what}.", "method": f"No one suggested uses {what}.",
            "place": f"No one suggested has worked in {what}.", "priority": f"No one suggested is linked to YIGH's {what} priority."
            }.get(kind, f"Not covered: {item}.")


def _workspace(opp_id: int, mode: str, discover: bool):
    m = nexus_api.get_matcher()
    o = m.rdb.get(Opportunity, opp_id)
    if o is None:
        raise HTTPException(404, "Opportunity not found")
    detail = opportunity_detail(opp_id, m.rdb)
    rec = m.recommend(opp_id, mode=mode)
    ror = None
    if discover:  # optional live registry look-ups for countries without documented partners
        from backend.radar.http import Fetcher
        from .ror import Ror
        from .run import UA
        ror = Ror(make_session(), Fetcher(UA))
    pdb = partner_db()
    try:
        partners = partners_for_recommendation(pdb, rec, m.ix.d, profile_opportunity(o, PRIORITY_NAMES), ror=ror)
        pdb.commit()
    finally:
        pdb.close()
    gaps = [c["concern"] for c in rec["eligibility_concerns"]] + partners["collaboration_gaps"] + \
           [_missing(x) for x in rec["missing_capabilities"]["items"]]
    sources = sorted(set(rec["sources"]) | {u for t in partners["teams"] for p in t["partners"] for u in p["evidence_urls"]}
                     | {detail["official_url"]})
    return {"opportunity": detail, "recommended_faculty": rec["top_faculty"], "teams": rec["teams"],
            "external_partners": partners, "eligibility_and_collaboration_gaps": gaps,
            "strategic_alignment": rec["strategic_alignment"], "generated_by": rec["generated_by"],
            "validation": rec["validation"], "notes": rec["notes"] + [partners["teams"][0]["partners"][0]["note"]]
            if partners["teams"] and partners["teams"][0]["partners"] else rec["notes"], "sources": sources}


@router.get("/api/radar/matches")
def matched_opportunities(limit: int = Query(20, ge=1, le=60)):
    """Open, priority-aligned opportunities with their top suggested Yale faculty and potential external partners.
    Recommendations are cached, so this only recomputes when an opportunity or a profile changed."""
    from backend.radar.models import Opportunity as Opp
    with nexus_api.MATCHER_LOCK:
        m = nexus_api.get_matcher()
        m.rdb.expire_all()
        opps = [o for o in m.rdb.scalars(select(Opp).where(Opp.status.in_(["open", "forecasted"]))) if o.priorities]
        opps.sort(key=lambda o: (o.deadline is None, o.deadline))
        pdb = partner_db()
        out = []
        try:
            for o in opps[:limit]:
                rec = m.recommend(o.id, mode="rules", trigger="feed")  # fast list view; the AI agent runs on the opportunity page
                parts = partners_for_recommendation(pdb, rec, m.ix.d, profile_opportunity(o, PRIORITY_NAMES))
                seen, partners = set(), []
                for t in parts["teams"]:
                    for p in t["partners"]:
                        if p["organization_id"] not in seen:
                            seen.add(p["organization_id"])
                            partners.append({"id": p["organization_id"], "name": p["name"], "country": p["country"],
                                             "relationship": p["relationship"]["status"], "website": p["website"]})
                out.append({
                    "opportunity": {"id": o.id, "title": o.title, "funder": o.organization.name if o.organization else None,
                                    "deadline": o.deadline, "deadline_text": o.deadline_text, "status": o.status,
                                    "priorities": [PRIORITY_NAMES.get(p.priority) for p in o.priorities],
                                    "verification_status": o.verification_status},
                    "top_faculty": [{"id": f["faculty_id"], "name": f["name"]} for f in rec["top_faculty"][:3]],
                    "potential_partners": partners[:3],
                    "partner_gaps": parts["collaboration_gaps"][:2],
                })
            pdb.commit()
        finally:
            pdb.close()
    return {"count": len(out), "opportunities": out,
            "note": "Suggested faculty and partners come from public Yale profiles and partner records. Nobody has been contacted."}
