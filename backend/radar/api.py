"""Global Health Radar feed API (mounted under /api/radar)."""
from __future__ import annotations

from backend.app.classification.plain import plain_explanation

import json
import re
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .db import get_radar_db
from .models import DiscoveryRun, FundingSource, Opportunity, OpportunityPriority, Organization, PageSnapshot, SourceFetch

router = APIRouter(prefix="/api/radar", tags=["Global Health Radar"])
PRIORITY_NAMES = {"climate-health": "Climate & Health", "digital-health-ai": "Digital Health & AI",
                  "health-diplomacy-security": "Health Diplomacy & Security", "health-sovereignty": "Health Sovereignty"}
NOT_VERIFIED_NOTE = "Details are copied from the funder's own page; blank fields weren't stated there. Always check the funder's page before applying."


def _card(o: Opportunity, today: date | None = None) -> dict:
    today = today or date.today()
    return {
        "id": o.id, "uid": o.uid, "opportunity_number": o.opportunity_number, "title": o.title,
        "funder": o.organization.name if o.organization else None,
        "deadline": o.deadline, "deadline_text": o.deadline_text,
        "days_left": (o.deadline - today).days if o.deadline and o.status != "closed" else None,
        "award_text": o.award_text, "status": o.status,
        "priorities": [{"slug": p.priority, "name": PRIORITY_NAMES.get(p.priority, p.priority), "confidence": p.confidence_label}
                       for p in sorted(o.priorities, key=lambda p: -p.confidence)],
        "verification_status": o.verification_status, "needs_review": o.needs_review,
        "official_url": o.official_url, "first_seen_at": o.first_seen_at, "last_changed_at": o.last_changed_at,
    }


GEO_FILTERS = {
    "foreign_eligible": r"foreign|non-domestic|non-U\.?S|international",
    "lmic_lead": r"based in (?:a |an )?(?:low|middle|LMIC|Africa|sub-Saharan)|low- and middle-income|LMIC",
    "us_only": r"U\.?S\.? (?:institutions|organizations) only|domestic",
}


def _filtered(db: Session, *, status=None, priority=None, q=None, funder=None, needs_review=None, deadline_before=None, geo=None):
    # pages people pasted into the Team Launchpad stay out of the shared list
    stmt = select(Opportunity).where(Opportunity.source.has(FundingSource.slug != "user-added"))
    if deadline_before:
        stmt = stmt.where(Opportunity.deadline <= deadline_before)
    if geo in GEO_FILTERS:
        ids = [o.id for o in db.scalars(select(Opportunity))
               if re.search(GEO_FILTERS[geo], " ".join(filter(None, [o.eligibility, o.geographic_restrictions, o.description])), re.I)]
        stmt = stmt.where(Opportunity.id.in_(ids))
    if status:
        stmt = stmt.where(Opportunity.status == status)
    if priority:
        stmt = stmt.where(Opportunity.priorities.any(OpportunityPriority.priority == priority))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Opportunity.title.ilike(like), Opportunity.description.ilike(like)))
    if funder:
        stmt = stmt.where(Opportunity.organization.has(Organization.slug == funder))
    if needs_review is not None:
        stmt = stmt.where(Opportunity.needs_review == needs_review)
    return stmt


def is_full_run(run: DiscoveryRun) -> bool:
    """A scheduled weekly run covers every enabled source; runs limited to a few sources (manual checks) don't count."""
    s = json.loads(run.summary or "{}")
    if "scope" in s:
        return s["scope"] == "all"
    # runs from before 'scope' existed: a full run always includes the core structured sources
    return {"grants-gov", "nih-guide-rss", "idrc"} <= set(s.get("sources", {}))


def _latest_weekly(db: Session) -> Optional[DiscoveryRun]:
    for run in db.scalars(select(DiscoveryRun).filter_by(mode="weekly").order_by(DiscoveryRun.id.desc())):
        if is_full_run(run):
            return run
    return None


@router.get("/opportunities")
def all_opportunities(status: Optional[str] = Query(None, description="open | forecasted | closed | unknown"),
                      priority: Optional[str] = Query(None, description="e.g. climate-health"),
                      q: Optional[str] = None, funder: Optional[str] = None, needs_review: Optional[bool] = None,
                      deadline_before: Optional[date] = None,
                      geo: Optional[str] = Query(None, description="foreign_eligible | lmic_lead | us_only"),
                      limit: int = Query(100, le=500), offset: int = 0, db: Session = Depends(get_radar_db)):
    stmt = _filtered(db, status=status, priority=priority, q=q, funder=funder, needs_review=needs_review,
                     deadline_before=deadline_before, geo=geo)
    rows = db.scalars(stmt.order_by(Opportunity.deadline.is_(None), Opportunity.deadline).offset(offset).limit(limit)).all()
    return {"count": len(rows), "note": NOT_VERIFIED_NOTE, "opportunities": [_card(o) for o in rows]}


@router.get("/opportunities/new")
def new_opportunities(since: Optional[date] = Query(None, description="default: found in the latest weekly run"),
                      db: Session = Depends(get_radar_db)):
    if since:
        stmt = select(Opportunity).where(Opportunity.first_seen_at >= datetime.combine(since, datetime.min.time()))
    else:
        run = _latest_weekly(db)
        stmt = select(Opportunity).where(Opportunity.first_seen_run_id == (run.id if run else -1))
    rows = db.scalars(stmt.order_by(Opportunity.first_seen_at.desc())).all()
    return {"count": len(rows), "opportunities": [_card(o) for o in rows]}


@router.get("/opportunities/updated")
def updated_opportunities(since: Optional[date] = Query(None, description="default: changed in the latest weekly run"),
                          db: Session = Depends(get_radar_db)):
    if since:
        stmt = select(Opportunity).where(Opportunity.last_changed_at >= datetime.combine(since, datetime.min.time()))
    else:
        run = _latest_weekly(db)
        stmt = select(Opportunity).where(Opportunity.last_changed_run_id == (run.id if run else -1))
    out = []
    for o in db.scalars(stmt.order_by(Opportunity.last_changed_at.desc())):
        card = _card(o)
        card["changes"] = [{"field": c.field, "old": c.old_value, "new": c.new_value, "detected_at": c.detected_at}
                           for c in o.changes if c.change_type in ("updated", "status") and c.run_id == o.last_changed_run_id]
        out.append(card)
    return {"count": len(out), "opportunities": out}


@router.get("/opportunities/closing-soon")
def closing_soon(days: int = Query(30, ge=1, le=365), priority: Optional[str] = None, db: Session = Depends(get_radar_db)):
    today = date.today()
    stmt = _filtered(db, priority=priority).where(Opportunity.status.in_(["open", "forecasted"]),
                                                  Opportunity.deadline >= today, Opportunity.deadline <= today + timedelta(days=days))
    rows = db.scalars(stmt.order_by(Opportunity.deadline)).all()
    return {"count": len(rows), "days": days, "opportunities": [_card(o, today) for o in rows]}


@router.get("/opportunities/priority/{slug}")
def by_priority(slug: str, status: Optional[str] = "open", db: Session = Depends(get_radar_db)):
    if slug not in PRIORITY_NAMES:
        raise HTTPException(404, f"Unknown priority. Use one of: {', '.join(PRIORITY_NAMES)}")
    rows = db.scalars(_filtered(db, priority=slug, status=status).order_by(Opportunity.deadline.is_(None), Opportunity.deadline)).all()
    return {"priority": PRIORITY_NAMES[slug], "count": len(rows), "opportunities": [_card(o) for o in rows]}


@router.get("/opportunities/{opp_id}")
def opportunity_detail(opp_id: int, db: Session = Depends(get_radar_db)):
    o = db.get(Opportunity, opp_id)
    if o is None:
        raise HTTPException(404, "Opportunity not found")
    return {
        **_card(o),
        "description": o.description, "award_floor": o.award_floor, "award_ceiling": o.award_ceiling, "currency": o.currency,
        "eligibility": o.eligibility, "geographic_restrictions": o.geographic_restrictions,
        "application_url": o.application_url, "posted_date": o.posted_date, "status_reason": o.status_reason,
        "review_reasons": json.loads(o.review_reasons or "[]"), "suspicious_content": o.suspicious_content,
        "verification": {
            "status": o.verification_status, "last_verified_at": o.last_verified_at,
            "history": [{"checked_at": v.checked_at, "method": v.method, "url": v.url, "status": v.status,
                         "fields": json.loads(v.details or "{}")} for v in o.verifications[-10:]],
        },
        "priority_evidence": [{"priority": PRIORITY_NAMES.get(p.priority), "confidence": p.confidence_label,
                               "explanation": plain_explanation(p.explanation), "evidence": json.loads(p.evidence)} for p in o.priorities],
        "sources": [{"source": s.source.name, "url": s.source_url, "retrieved_at": s.retrieved_at} for s in o.sightings[-10:]],
        "changes": [{"type": c.change_type, "field": c.field, "old": c.old_value, "new": c.new_value, "detected_at": c.detected_at}
                    for c in o.changes],
        "note": NOT_VERIFIED_NOTE,
    }


@router.get("/review")
def review_queue(db: Session = Depends(get_radar_db)):
    """Items a person should check: flagged opportunities and monitored pages that changed."""
    opps = db.scalars(select(Opportunity).filter_by(needs_review=True).order_by(Opportunity.first_seen_at.desc())).all()
    pages = db.scalars(select(PageSnapshot).filter_by(changed=True, reviewed=False)).all()
    return {"opportunities": [{**_card(o), "review_reasons": json.loads(o.review_reasons or "[]")} for o in opps],
            "changed_pages": [{"id": p.id, "source_id": p.source_id, "source": db.get(FundingSource, p.source_id).name, "url": p.url,
                               "retrieved_at": p.retrieved_at, "excerpt": p.excerpt} for p in pages]}


@router.get("/runs/latest")
def latest_runs(db: Session = Depends(get_radar_db)):
    out = {}
    for mode in ("weekly", "deadlines"):
        r = db.scalar(select(DiscoveryRun).filter_by(mode=mode).order_by(DiscoveryRun.id.desc()))
        out[mode] = json.loads(r.summary) if r and r.summary else None
    return out


@router.get("/sources")
def sources(db: Session = Depends(get_radar_db)):
    """The agent's watchlist: every funder source, how it is collected, and its latest outcome."""
    from backend.radar.pipeline import load_registry, seed
    seed(db, load_registry())  # keep the DB in sync with config/radar_sources.json
    db.commit()
    out = []
    for src in db.scalars(select(FundingSource).order_by(FundingSource.name)):
        snap = db.scalar(select(PageSnapshot).filter_by(source_id=src.id).order_by(PageSnapshot.id.desc()))
        last_fetch = db.scalar(select(SourceFetch).filter_by(source_id=src.id).order_by(SourceFetch.id.desc()))
        out.append({
            "id": src.slug, "name": src.name, "official_url": src.official_url, "endpoint": src.endpoint,
            "access_method": src.access_method, "enabled": src.enabled, "notes": src.notes,
            "funder": src.organization.name if src.organization else None,
            "last_status": src.last_status, "last_checked_at": last_fetch.started_at if last_fetch else None,
            "last_success_at": src.last_success_at, "last_error": last_fetch.error if last_fetch and last_fetch.status != "ok" else None,
            "opportunities": {"total": db.query(Opportunity).filter_by(source_id=src.id).count(),
                              "open": db.query(Opportunity).filter(Opportunity.source_id == src.id,
                                                                   Opportunity.status.in_(["open", "forecasted"])).count()},
            "page_change_pending": bool(snap and snap.changed and not snap.reviewed),
            "last_snapshot_at": snap.retrieved_at if snap else None,
        })
    return out


@router.post("/page-changes/{snapshot_id}/reviewed")
def mark_page_change_reviewed(snapshot_id: int, db: Session = Depends(get_radar_db)):
    snap = db.get(PageSnapshot, snapshot_id)
    if snap is None:
        raise HTTPException(404, "Snapshot not found")
    snap.reviewed = True
    db.commit()
    return {"id": snap.id, "reviewed": True}


@router.get("/funders")
def funders(db: Session = Depends(get_radar_db)):
    """Every funder the Radar watches or has found opportunities for, with its opportunity count (0 included)."""
    counts = dict(db.execute(select(Opportunity.organization_id, func.count(Opportunity.id)).group_by(Opportunity.organization_id)).all())
    watched = set(db.scalars(select(FundingSource.organization_id).where(FundingSource.organization_id.is_not(None))))
    orgs = [o for o in db.scalars(select(Organization)) if o.id in watched or counts.get(o.id)]
    orgs.sort(key=lambda o: (-counts.get(o.id, 0), o.name.lower()))
    return [{"value": o.slug, "label": o.name, "count": counts.get(o.id, 0)} for o in orgs]


def _brief_opp(o: Opportunity) -> dict:
    return {"id": o.id, "title": o.title, "status": o.status, "posted_date": o.posted_date, "deadline": o.deadline,
            "deadline_text": o.deadline_text, "first_seen_at": o.first_seen_at, "official_url": o.official_url}


@router.get("/funders/{slug}/timing")
def funder_timing(slug: str, db: Session = Depends(get_radar_db)):
    """When this funder last opened a call and whether a next one is announced, using only dates the Radar has recorded
    from official sources. Nothing is predicted: if no forecast exists, the response says so."""
    org = db.scalar(select(Organization).filter_by(slug=slug))
    if not org:
        raise HTTPException(404, "Funder not found")
    opps = db.scalars(select(Opportunity).filter_by(organization_id=org.id)).all()
    today = date.today()
    open_now = sorted([o for o in opps if o.status == "open"], key=lambda o: o.deadline or date.max)
    forecast = sorted([o for o in opps if o.status == "forecasted"], key=lambda o: o.deadline or date.max)
    dated = [o for o in opps if o.posted_date]
    last_opened = max(dated, key=lambda o: o.posted_date) if dated else None
    first_recorded = max(opps, key=lambda o: o.first_seen_at) if opps and not dated else None
    closed = [o for o in opps if o.status == "closed" and o.deadline and o.deadline <= today]
    last_closed = max(closed, key=lambda o: o.deadline) if closed else None

    srcs = db.scalars(select(FundingSource).filter_by(organization_id=org.id)).all()
    watch = []
    for src in srcs:
        last_fetch = db.scalar(select(SourceFetch).filter_by(source_id=src.id).order_by(SourceFetch.id.desc()))
        snap = db.scalar(select(PageSnapshot).filter_by(source_id=src.id).order_by(PageSnapshot.id.desc()))
        watch.append({"name": src.name, "official_url": src.official_url, "access_method": src.access_method,
                      "last_checked_at": last_fetch.started_at if last_fetch else None, "last_status": src.last_status,
                      "page_change_pending": bool(snap and snap.changed and not snap.reviewed),
                      "page_last_changed_at": snap.retrieved_at if snap and snap.changed else None, "notes": src.notes})

    if open_now:
        headline = f"{len(open_now)} call{'s are' if len(open_now) > 1 else ' is'} open now."
    elif forecast:
        headline = "Nothing is open now, but a forecasted call has been announced."
    elif last_opened or last_closed or first_recorded:
        headline = "Nothing is open now, and no next round has been announced in the sources the Radar checks."
    else:
        headline = "The Radar has not recorded any calls from this funder yet."
    return {
        "funder": {"slug": org.slug, "name": org.name, "website": org.website},
        "headline": headline,
        "open_now": [_brief_opp(o) for o in open_now],
        "forecasted": [_brief_opp(o) for o in forecast],
        "last_opened": _brief_opp(last_opened) if last_opened else None,
        "first_recorded": _brief_opp(first_recorded) if first_recorded else None,
        "last_closed": _brief_opp(last_closed) if last_closed else None,
        "watch": watch,
        "note": "Dates come from the funder's own announcements. Forecast dates are the funder's own estimates "
                "and may change. The Radar does not predict future rounds.",
    }


@router.get("/brief")
def weekly_brief(db: Session = Depends(get_radar_db)):
    """The weekly brief: what the latest discovery run found, what changed, what closes soon, and what needs review.
    Links to faculty/teams/partners are fetched per opportunity from the workspace endpoint (cached)."""
    run = _latest_weekly(db)
    summary = json.loads(run.summary) if run and run.summary else None
    new = db.scalars(select(Opportunity).where(Opportunity.first_seen_run_id == (run.id if run else -1),
                                               Opportunity.status.in_(["open", "forecasted"]))).all()
    upd = db.scalars(select(Opportunity).where(Opportunity.last_changed_run_id == (run.id if run else -1))).all()
    today = date.today()
    soon = db.scalars(select(Opportunity).where(Opportunity.status.in_(["open", "forecasted"]), Opportunity.deadline >= today,
                                                Opportunity.deadline <= today + timedelta(days=30)).order_by(Opportunity.deadline)).all()
    by_priority = {name: sum(1 for o in db.scalars(select(Opportunity).where(Opportunity.status.in_(["open", "forecasted"]),
                                                                          Opportunity.priorities.any(OpportunityPriority.priority == slug))))
                   for slug, name in PRIORITY_NAMES.items()}
    def rank(o):  # verified, priority-aligned, soonest deadline first
        return (o.verification_status != "verified", -len(o.priorities), o.deadline or date.max)
    return {"run": summary, "generated_at": run.finished_at if run else None,
            "highlights": [_card(o) for o in sorted([o for o in db.scalars(select(Opportunity).where(
                Opportunity.status.in_(["open", "forecasted"]))) if o.priorities], key=rank)[:6]],
            "new": [_card(o) for o in new], "updated": [_card(o) for o in upd], "closing_soon": [_card(o) for o in soon],
            "open_by_priority": by_priority,
            "review_queue": db.query(Opportunity).filter_by(needs_review=True).filter(Opportunity.status != "closed").count()}
