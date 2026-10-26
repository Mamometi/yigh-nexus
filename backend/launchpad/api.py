"""Team Launchpad API: bring in an opportunity (link or list), then draft a one-pager with the user's goals.
Finding faculty and partners uses the existing workspace endpoint (/api/radar/opportunities/{id}/workspace)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.auth.api import current_user
from backend.nexus import api as nexus_api
from backend.radar.db import get_radar_db

from .importer import ImportError_, import_link

router = APIRouter(prefix="/api/launchpad", tags=["Team Launchpad"])


class LinkIn(BaseModel):
    url: str = Field(max_length=1000)


class OnePagerIn(BaseModel):
    opportunity_id: int
    team: str | None = None
    goals: list[str] = Field(default_factory=list, max_length=8)


@router.post("/import")
def import_opportunity(body: LinkIn, user: dict = Depends(current_user), db=Depends(get_radar_db)):
    """Use a pasted link: match it to an opportunity already in the Radar, or read it from Grants.gov or the page itself."""
    try:
        opp, how = import_link(db, body.url)
    except ImportError_ as e:
        raise HTTPException(422, str(e))
    return {"id": opp.id, "title": opp.title, "how": how,
            "message": {"existing": "This opportunity is already in the Opportunities hub.",
                        "grants_gov": "Found it on Grants.gov and added the official details.",
                        "page": "Read the details from that page. They haven't been checked with the funder, so confirm them before applying."}[how]}


@router.post("/one-pager")
def one_pager(body: OnePagerIn, user: dict = Depends(current_user)):
    """A one-page concept for the opportunity, built around the user's goals and a suggested team."""
    goals = [g.strip()[:300] for g in body.goals if g.strip()]
    with nexus_api.MATCHER_LOCK:
        from backend.nexus.concept import build_concept
        from backend.partners.api import workspace
        try:
            ws = workspace(body.opportunity_id, mode="auto")
            return build_concept(nexus_api.get_matcher(), ws, body.team, goals=goals)
        except ValueError as e:
            raise HTTPException(422, str(e))
