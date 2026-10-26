"""Dashboard endpoint for the frontend."""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .database import get_db
from .models import Faculty, FacultyPriority, School, StrategicPriority

router = APIRouter(tags=["Dashboard"])


@router.get("/api/dashboard")
def dashboard(db: Session = Depends(get_db)):
    from backend.nexus.service import Recommendation, nexus_session
    from backend.partners.api import partner_db
    from backend.partners.models import Org, YaleLink
    from backend.radar.db import get_session
    from backend.radar.models import DiscoveryRun, Opportunity, OpportunityPriority
    from backend.radar.api import PRIORITY_NAMES
    r = get_session()
    pr = {name: {"faculty": db.query(FacultyPriority).join(StrategicPriority).filter(StrategicPriority.slug == slug).count(),
                 "open_opportunities": r.query(Opportunity).filter(Opportunity.status == "open",
                                                                   Opportunity.priorities.any(OpportunityPriority.priority == slug)).count()}
          for slug, name in PRIORITY_NAMES.items()}
    from backend.radar.api import _latest_weekly
    run = _latest_weekly(r)
    n = nexus_session()
    recent = [json.loads(x.document) for x in n.scalars(select(Recommendation).order_by(Recommendation.created_at.desc()).limit(5))]
    pdb = partner_db()
    try:
        return _dashboard_payload(db, r, n, pdb, pr, run, recent)
    finally:
        r.close(); n.close(); pdb.close()


def _dashboard_payload(db, r, n, pdb, pr, run, recent):
    from backend.partners.models import Org, YaleLink
    from backend.radar.models import Opportunity
    return {
        "faculty": {"total": db.query(Faculty).count(),
                    "by_directory": dict(db.execute(select(Faculty.source, func.count(Faculty.id)).group_by(Faculty.source)).all()),
                    "by_school": dict(db.execute(select(School.name, func.count(Faculty.id)).join(Faculty).group_by(School.name)).all())},
        "opportunities": {"total": r.query(Opportunity).count(),
                          "open": r.query(Opportunity).filter(Opportunity.status.in_(["open", "forecasted"])).count(),
                          "verified_open": r.query(Opportunity).filter(Opportunity.status.in_(["open", "forecasted"]),
                                                                        Opportunity.verification_status == "verified").count(),
                          "needs_review": r.query(Opportunity).filter_by(needs_review=True).filter(Opportunity.status != "closed").count()},
        "partners": {"organizations": pdb.query(Org).count(), "documented_yale_links": pdb.query(YaleLink).count()},
        "watchlist": _watchlist_counts(),
        "priorities": pr,
        "last_discovery_run": json.loads(run.summary) if run and run.summary else None,
        "recent_matches": [{"opportunity": d["opportunity"], "generated_by": d["generated_by"],
                            "top_faculty": [f["name"] for f in d["top_faculty"][:3]], "teams": len(d["teams"])} for d in recent],
    }


def _watchlist_counts() -> dict:
    from backend.radar.pipeline import load_registry
    srcs = load_registry()["sources"]
    by = {}
    for s in srcs:
        by[s["access_method"]] = by.get(s["access_method"], 0) + 1
    return {"sources": len(srcs), "automated": sum(1 for s in srcs if s.get("enabled")), "by_method": by}
