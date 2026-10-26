"""FastAPI app for Constellation + Global Health Radar.

Run from the project root:
    .venv/bin/uvicorn backend.app.main:app --reload
"""
import json
from pathlib import Path
from backend.app.classification.plain import plain_explanation
from datetime import date
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from backend.auth.api import router as auth_router
from backend.assistant.api import router as assistant_router
from backend.launchpad.api import router as launchpad_router
from backend.nexus.api import router as nexus_router
from backend.partners.api import router as partners_router
from backend.radar.api import router as radar_router

from .constellation_api import router as constellation_router
from .home_api import router as home_router
from .database import get_db
from .matching.config import DEFAULT_MIN_SCORE, load_weights
from .matching.engine import DISCLAIMER, load_profiles, rank_collaborators
from .matching.network import build_network
from .models import (Faculty, FacultyAppointment, FacultyInterest, FacultyKeyword, FacultyPriority, FacultyRegion,
                     Region, ResearchInterest, School, StandardKeyword, StrategicPriority)

app = FastAPI(title="YIGH Constellation & Global Health Radar API")
app.include_router(radar_router)
app.include_router(nexus_router)
app.include_router(partners_router)
app.include_router(constellation_router)
app.include_router(home_router)
app.include_router(auth_router)
app.include_router(assistant_router)
app.include_router(launchpad_router)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://localhost:5180"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])


_PHOTOS = {"mtime": None, "map": {}}


def photo_url(fid: int) -> str | None:
    """Headshot from the public Yale profile (data/faculty_photos.json), or None for the generic avatar."""
    from pathlib import Path
    path = Path(__file__).resolve().parents[2] / "data" / "faculty_photos.json"
    try:
        m = path.stat().st_mtime
    except FileNotFoundError:
        return None
    if m != _PHOTOS["mtime"]:
        import json as _json
        _PHOTOS.update(mtime=m, map=_json.loads(path.read_text()).get("photos", {}))
    return _PHOTOS["map"].get(str(fid))


def _card(f: Faculty) -> dict:
    """Compact record for directory cards."""
    kws = sorted(f.keywords, key=lambda k: -k.confidence)
    return {
        "id": f.id, "name": f.name, "title": f.title,
        "school": f.school.name if f.school else None,
        "department": f.department.name if f.department else None,
        "keywords": [k.keyword.name for k in kws[:6]],
        "priorities": [{"name": p.priority.name, "slug": p.priority.slug, "confidence": p.confidence_label}
                       for p in sorted(f.priorities, key=lambda p: -p.confidence)],
        "regions": [r.region.name for r in sorted(f.regions, key=lambda r: -r.confidence)],
        "has_bio": bool(f.bio),
        "bio_excerpt": (f.bio[:320].rsplit(" ", 1)[0] + "…") if f.bio and len(f.bio) > 320 else f.bio,
        "directory": f.source,
        "photo_url": photo_url(f.id),
    }


def _with_tags(stmt):
    return stmt.options(
        selectinload(Faculty.school), selectinload(Faculty.department),
        selectinload(Faculty.keywords).selectinload(FacultyKeyword.keyword),
        selectinload(Faculty.priorities).selectinload(FacultyPriority.priority),
        selectinload(Faculty.regions).selectinload(FacultyRegion.region))


@app.get("/api/faculty")
def list_faculty(
    q: Optional[str] = None,
    school: Optional[str] = None,
    keyword: Optional[str] = None,
    priority: Optional[str] = None,
    region: Optional[str] = None,
    directory: Optional[str] = Query(None, description="'yigh' or 'ysph'"),
    db: Session = Depends(get_db),
):
    """Directory search. q matches name, title, bio and research interests. Filters combine with AND."""
    stmt = select(Faculty).order_by(Faculty.name)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Faculty.name.ilike(like), Faculty.title.ilike(like), Faculty.bio.ilike(like),
                              Faculty.interests.any(FacultyInterest.interest.has(ResearchInterest.name.ilike(like))),
                              Faculty.keywords.any(FacultyKeyword.keyword.has(StandardKeyword.name.ilike(like)))))
    if school:
        stmt = stmt.where(Faculty.school.has(School.name == school))
    if keyword:
        stmt = stmt.where(Faculty.keywords.any(FacultyKeyword.keyword.has(StandardKeyword.name == keyword)))
    if priority:
        stmt = stmt.where(Faculty.priorities.any(FacultyPriority.priority.has(StrategicPriority.slug == priority)))
    if region:
        stmt = stmt.where(Faculty.regions.any(FacultyRegion.region.has(Region.name == region)))
    if directory:
        stmt = stmt.where(Faculty.source == directory)
    return [_card(f) for f in db.scalars(_with_tags(stmt))]


@app.get("/api/filters")
def filters(db: Session = Depends(get_db)):
    """Filter options with the number of faculty for each, so empty options can be hidden."""
    def counts(model, join_col, name_col, extra=()):
        rows = db.execute(select(name_col, *extra, func.count(func.distinct(join_col)))
                          .select_from(model).join(*{
                              FacultyKeyword: (StandardKeyword,), FacultyPriority: (StrategicPriority,),
                              FacultyRegion: (Region,)}[model]).group_by(name_col, *extra).order_by(name_col))
        return rows.all()
    schools = db.execute(select(School.name, func.count(Faculty.id)).join(Faculty).group_by(School.name)
                         .order_by(School.name)).all()
    return {
        "schools": [{"value": n, "label": n, "count": c} for n, c in schools],
        "keywords": [{"value": n, "label": n, "count": c} for n, c in counts(FacultyKeyword, FacultyKeyword.faculty_id, StandardKeyword.name)],
        "priorities": [{"value": slug, "label": n, "count": c} for n, slug, c in
                       counts(FacultyPriority, FacultyPriority.faculty_id, StrategicPriority.name, (StrategicPriority.slug,))],
        "regions": [{"value": n, "label": n, "count": c, "kind": k} for n, k, c in
                    counts(FacultyRegion, FacultyRegion.faculty_id, Region.name, (Region.kind,))],
        "total_faculty": db.scalar(select(func.count(Faculty.id))),
        "directories": [{"value": v, "label": {"yigh": "YIGH affiliated faculty", "ysph": "YSPH faculty with global health work"}.get(v, v),
                     "count": c} for v, c in db.execute(select(Faculty.source, func.count(Faculty.id)).group_by(Faculty.source))],
    }


@app.get("/api/faculty/{faculty_id}")
def faculty_detail(faculty_id: int, db: Session = Depends(get_db)):
    """Full profile: source data (verbatim) kept separate from generated classifications."""
    f = db.scalar(_with_tags(select(Faculty).where(Faculty.id == faculty_id)).options(
        selectinload(Faculty.appointments).selectinload(FacultyAppointment.department),
        selectinload(Faculty.interests).selectinload(FacultyInterest.interest),
        selectinload(Faculty.activities), selectinload(Faculty.organizations), selectinload(Faculty.coauthors)))
    if f is None:
        raise HTTPException(404, "Faculty member not found")
    gen = lambda row, name: {"name": name, "confidence": row.confidence_label, "explanation": plain_explanation(row.explanation),
                             "evidence": json.loads(row.evidence or "[]"), "method": row.method}
    return {
        **_card(f),
        "email": f.email, "profile_url": f.source_url,
        "inclusion_reasons": json.loads(f.inclusion_reasons) if f.inclusion_reasons else [],
        "source": {
            "bio": f.bio,
            "appointments": [{"department": a.department.name, "title": a.title, "type": a.appointment_type}
                             for a in f.appointments],
            "research_interests": [i.interest.name for i in f.interests],
            "activities": [{"title": a.title, "type": a.activity_type,
                            "start": a.start_date.isoformat() if a.start_date else None,
                            "end": a.end_date.isoformat() if a.end_date else None,
                            "locations": json.loads(a.locations or "[]"), "synopsis": a.synopsis}
                           for a in sorted(f.activities, key=lambda a: a.start_date or date.min, reverse=True)],
            "organizations": [{"name": o.name, "url": o.url} for o in sorted(f.organizations, key=lambda o: o.name)],
            "yale_coauthors": [{"name": c.coauthor_name, "profile_url": c.coauthor_url, "faculty_id": c.coauthor_faculty_id}
                               for c in f.coauthors],
        },
        "generated": {
            "priorities": [gen(p, p.priority.name) for p in sorted(f.priorities, key=lambda p: -p.confidence)],
            "keywords": [gen(k, k.keyword.name) for k in sorted(f.keywords, key=lambda k: -k.confidence)],
            "regions": [gen(r, r.region.name) for r in sorted(f.regions, key=lambda r: -r.confidence)],
        },
    }


@app.get("/api/matching/weights")
def get_weights():
    return load_weights()


@app.get("/api/faculty/{faculty_id}/collaborators")
def collaborators(
    faculty_id: int,
    limit: int = Query(10, ge=1, le=50),
    min_score: float = Query(DEFAULT_MIN_SCORE, ge=0, le=1),
    cross_school_only: bool = False,
    new_connections_only: bool = Query(False, description="hide people already listed as Yale co-authors"),
    w_shared_interests: Optional[float] = Query(None, ge=0),
    w_complementary_expertise: Optional[float] = Query(None, ge=0),
    w_geography: Optional[float] = Query(None, ge=0),
    w_strategic_priorities: Optional[float] = Query(None, ge=0),
    w_cross_school: Optional[float] = Query(None, ge=0),
    db: Session = Depends(get_db),
):
    """Ranked collaborators for one faculty member, each with a score breakdown and evidence."""
    try:
        weights = load_weights({"shared_interests": w_shared_interests,
                                "complementary_expertise": w_complementary_expertise,
                                "geography": w_geography, "strategic_priorities": w_strategic_priorities,
                                "cross_school": w_cross_school})
    except ValueError as e:
        raise HTTPException(400, str(e))
    profiles = load_profiles(db)
    if faculty_id not in profiles:
        raise HTTPException(404, "Faculty member not found")
    me = profiles[faculty_id]
    return {
        "faculty": {"id": me.id, "name": me.name, "school": me.school, "profile_url": me.source_url},
        "weights": weights,
        "disclaimer": DISCLAIMER,
        "matches": rank_collaborators(profiles, faculty_id, weights, limit, min_score, cross_school_only,
                                      new_connections_only),
    }


@app.get("/api/network")
def network(
    school: Optional[str] = None,
    keyword: Optional[str] = None,
    priority: Optional[str] = Query(None, description="priority name, e.g. 'Climate & Health'"),
    size: int = Query(25, ge=5, le=40),
    edges_per_node: int = Query(3, ge=1, le=6),
    min_score: float = Query(DEFAULT_MIN_SCORE, ge=0, le=1),
    new_connections_only: bool = False,
    db: Session = Depends(get_db),
):
    """Faculty collaboration network: nodes = faculty, edges = suggested (not verified) matches."""
    data = build_network(load_profiles(db), load_weights(), school=school, keyword=keyword, priority=priority,
                         size=size, edges_per_node=edges_per_node, min_score=min_score,
                         new_connections_only=new_connections_only)
    return {**data, "disclaimer": "Connections are algorithm-generated suggestions based on public profile text. "
                                  "They are not verified collaborations. Dashed lines mark pairs already listed as Yale co-authors."}


# ------------------------------------------------------------------ website
# Serve the built React app (frontend/dist) from the same server, so the whole site runs with one command.
# Registered last: every /api route above takes precedence; any other path returns index.html (client-side routing).
_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if (_DIST / "index.html").exists():
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def website(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Not found")
        f = (_DIST / path).resolve()
        if path and f.is_file() and _DIST in f.parents:
            return FileResponse(f)
        return FileResponse(_DIST / "index.html")
