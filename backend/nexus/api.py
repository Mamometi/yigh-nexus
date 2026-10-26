"""YIGH Nexus matching API (mounted under /api/nexus)."""
from __future__ import annotations

import threading
from functools import lru_cache
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.auth.api import current_user

from .service import Matcher

router = APIRouter(prefix="/api/nexus", tags=["YIGH Nexus matching"])
# The cached Matcher holds SQLite sessions, which must not be used by two threads at once.
MATCHER_LOCK = threading.RLock()


@lru_cache(maxsize=1)
def get_matcher() -> Matcher:
    return Matcher()


@router.get("/faculty/search")
def faculty_search(expertise: Optional[str] = None, method: Optional[str] = None, school: Optional[str] = None,
                   department: Optional[str] = None, priority: Optional[str] = None, place: Optional[str] = None,
                   project: Optional[str] = None):
    """Documented-only faculty retrieval. Filters combine with AND; every hit includes evidence and its source URL."""
    with MATCHER_LOCK:
        ix = get_matcher().ix
        results = None
        for active, hits in [(expertise, lambda: ix.by_expertise([expertise])), (method, lambda: ix.by_method([method])),
                             (school or department, lambda: ix.by_school(school, department)), (priority, lambda: ix.by_priority(priority)),
                             (place, lambda: ix.by_geography(place)), (project, lambda: ix.projects(project, k=100))]:
            if not active:
                continue
            found = {h["faculty_id"]: h for h in hits()}
            if results is None:
                results = found
            else:
                results = {i: {**results[i], "evidence": results[i]["evidence"] + found[i]["evidence"]} for i in results if i in found}
        if results is None:
            raise HTTPException(400, "Give at least one filter: expertise, method, school, department, priority, place, project")
        return {"count": len(results), "faculty": list(results.values())}


@router.get("/opportunities/{opportunity_id}/recommendation")
def recommendation(opportunity_id: int, mode: str = Query("auto", pattern="^(auto|ai|rules)$")):
    """Recommended faculty and teams for one opportunity (served from cache when nothing relevant changed)."""
    with MATCHER_LOCK:
        try:
            return get_matcher().recommend(opportunity_id, mode=mode)
        except KeyError:
            raise HTTPException(404, "Opportunity not found")


@router.post("/opportunities/{opportunity_id}/refresh")
def refresh_one(opportunity_id: int, force: bool = True, mode: str = Query("auto", pattern="^(auto|ai|rules)$")):
    """Administrator refresh (force=true recomputes even when inputs are unchanged)."""
    with MATCHER_LOCK:
        try:
            return get_matcher().recommend(opportunity_id, mode=mode, force=force, trigger="admin_refresh")
        except KeyError:
            raise HTTPException(404, "Opportunity not found")


@router.post("/refresh")
def refresh(trigger: str = Query("admin_refresh", pattern="^(admin_refresh|radar_run|faculty_updated)$"), force: bool = False):
    with MATCHER_LOCK:
        m = get_matcher()
        return m.refresh_after_radar_run() if trigger == "radar_run" else m.refresh(trigger, force=force)


@router.get("/model-calls")
def model_calls(limit: int = 100):
    with MATCHER_LOCK:
        return get_matcher().model_call_log(limit)


@router.post("/opportunities/{opportunity_id}/concept")
def concept(opportunity_id: int, team: Optional[str] = None, user: dict = Depends(current_user)):
    """Launchpad: one-page research concept for a proposed team (AI draft when configured; otherwise a documented-facts outline).
    Requires a signed-in user."""
    with MATCHER_LOCK:
        from backend.partners.api import workspace
        from .concept import build_concept
        try:
            ws = workspace(opportunity_id, mode="auto")
            return build_concept(get_matcher(), ws, team)
        except ValueError as e:
            raise HTTPException(422, str(e))
