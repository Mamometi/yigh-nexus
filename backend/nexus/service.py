"""Matching service: cache, triggers, model-call logging, and the final recommendation document.

Cache key = sha256(opportunity content hash + fingerprints of the shortlisted faculty profiles + generator
(model id or "rules") + PROMPT_VERSION). A changed requirement, a changed faculty profile, a new model or
a new prompt therefore produces a new key and a rerun; anything else is served from cache (no API cost).
"""
from __future__ import annotations

from backend.app.classification.plain import plain_explanation

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from backend.app.database import SessionLocal as FacultySession
from backend.radar.api import PRIORITY_NAMES
from backend.radar.db import get_session as radar_session
from backend.radar.models import Opportunity

from .agent import (DEFAULT_MODEL, PROMPT_VERSION, Deps, MatchResult, build_agent, opportunity_prompt, rule_based_result,
                    scrub_unsupported, validated_eligibility_notes)
from .retrieval import FacultyIndex, load_dossiers
from .shortlist import eligibility_concerns, profile_opportunity, stage_a

# Claude Opus 5.5 list prices (USD per million tokens) — used only to estimate cost in logs.
PRICES = {"claude-opus-5-5": (4.00, 20.00), "claude-sonnet-5-5": (2.00, 10.00), "claude-haiku-5-5": (0.10, 0.50)}
SHORTLIST_SIZE = 15


class NexusBase(DeclarativeBase):
    pass


class Recommendation(NexusBase):
    __tablename__ = "recommendations"
    id: Mapped[int] = mapped_column(primary_key=True)
    opportunity_uid: Mapped[str] = mapped_column(String(200), index=True)
    cache_key: Mapped[str] = mapped_column(String(64), unique=True)
    generated_by: Mapped[str] = mapped_column(String(80))
    trigger: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    document: Mapped[str] = mapped_column(Text)


class ModelCall(NexusBase):
    __tablename__ = "model_calls"
    id: Mapped[int] = mapped_column(primary_key=True)
    opportunity_uid: Mapped[str] = mapped_column(String(200))
    model: Mapped[str] = mapped_column(String(80))
    started_at: Mapped[datetime] = mapped_column(DateTime)
    latency_ms: Mapped[int] = mapped_column(Integer)
    requests: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0)
    est_cost_usd: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(20))
    error: Mapped[Optional[str]] = mapped_column(Text)
    recommendation_id: Mapped[Optional[int]] = mapped_column(ForeignKey("recommendations.id"))


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


_sessions = {}


def nexus_session(path: str | None = None) -> Session:
    path = path or os.environ.get("NEXUS_DB_PATH") or str(Path(__file__).resolve().parents[2] / "data" / "nexus.db")
    if path not in _sessions:
        eng = create_engine(f"sqlite:///{path}")
        NexusBase.metadata.create_all(eng)
        _sessions[path] = sessionmaker(bind=eng, expire_on_commit=False)
    return _sessions[path]()


def _llm_name() -> str:
    from backend import llm
    return llm.model_name()


def ai_available() -> bool:
    from backend import llm
    return llm.ai_available() and (llm.provider() == "test" or llm.within_budget())


class Matcher:
    def __init__(self, faculty_db: Session | None = None, radar_db: Session | None = None, nexus_db: Session | None = None,
                 model=None):
        self.fdb = faculty_db or FacultySession()
        self.rdb = radar_db or radar_session()
        self.ndb = nexus_db or nexus_session()
        self.model = model
        self.ix = FacultyIndex(load_dossiers(self.fdb))

    def reload_faculty(self):
        self.ix = FacultyIndex(load_dossiers(self.fdb))

    # -------------------------------------------------------------- core
    def recommend(self, opportunity_id: int, *, mode: str = "auto", force: bool = False, trigger: str = "request") -> dict:
        o = self.rdb.get(Opportunity, opportunity_id)
        if o is None:
            raise KeyError(opportunity_id)
        opp = profile_opportunity(o, PRIORITY_NAMES)
        rows = stage_a(self.ix, opp, SHORTLIST_SIZE)
        shortlist = {r["faculty_id"]: self.ix.d[r["faculty_id"]] for r in rows}
        use_ai = mode == "ai" or (mode == "auto" and (self.model is not None or ai_available()))
        model_id = (getattr(self.model, "model_name", None) or str(self.model)) if self.model is not None else \
            _llm_name()
        generator = f"ai:{model_id}" if use_ai else "rules"
        key = hashlib.sha256(json.dumps([o.content_hash, sorted((i, d.fingerprint()) for i, d in shortlist.items()),
                                         generator, PROMPT_VERSION]).encode()).hexdigest()
        cached = self.ndb.scalar(select(Recommendation).filter_by(cache_key=key))
        if cached and not force:
            doc = json.loads(cached.document)
            doc["cache"] = {"hit": True, "created_at": cached.created_at.isoformat(), "key": key[:12]}
            return doc

        concerns = eligibility_concerns(o.eligibility, o.description)
        validation = {"unsupported_claims_removed": [], "eligibility_notes_dropped": [], "model_error": None}
        result = None
        if use_ai:
            result, call = self._run_agent(opp, shortlist, rows, concerns, o.uid)
            if result is None:
                validation["model_error"] = call.error
        if result is None:
            generator = "rules" if not use_ai else f"rules (AI fallback after error)"
            result = rule_based_result(opp, shortlist, rows)
        validation["unsupported_claims_removed"] = scrub_unsupported(result, shortlist)
        extra, dropped = validated_eligibility_notes(result, opp)
        validation["eligibility_notes_dropped"] = dropped

        doc = self._document(o, opp, rows, shortlist, result, concerns + [dict(e, code="ai_noted") for e in extra], generator, validation)
        rec = self.ndb.scalar(select(Recommendation).filter_by(cache_key=key)) or Recommendation(cache_key=key)
        rec.opportunity_uid, rec.generated_by, rec.trigger, rec.created_at = o.uid, generator, trigger, _now()
        rec.document = json.dumps(doc, default=str)
        self.ndb.add(rec)
        self.ndb.commit()
        if use_ai:
            for c in self.ndb.scalars(select(ModelCall).filter_by(opportunity_uid=o.uid, recommendation_id=None)):
                c.recommendation_id = rec.id
            self.ndb.commit()
        doc["cache"] = {"hit": False, "created_at": rec.created_at.isoformat(), "key": key[:12]}
        return doc

    def _run_agent(self, opp, shortlist, rows, concerns, uid):
        agent = build_agent(self.model)
        started, t0 = _now(), time.perf_counter()
        call = ModelCall(opportunity_uid=uid, model=str(getattr(self.model, "model_name", None) or _llm_name()),
                         started_at=started, latency_ms=0, status="ok")
        result = None
        try:
            from backend import llm
            run = agent.run_sync(opportunity_prompt(opp, shortlist, rows, concerns),
                                 deps=Deps(opp, shortlist, {r["faculty_id"]: r for r in rows}), usage_limits=llm.limits("team_matching"))
            result, u = run.output, run.usage
            llm.record("team_matching", u, latency_s=time.perf_counter() - t0)
            call.requests, call.input_tokens, call.output_tokens = u.requests, u.input_tokens, u.output_tokens
            call.cache_read_tokens = u.cache_read_tokens
        except Exception as e:  # noqa: BLE001 — logged; the rule-based result is used instead
            call.status, call.error = "error", f"{type(e).__name__}: {e}"[:2000]
            from backend import llm
            llm.record("team_matching", None, latency_s=time.perf_counter() - t0, status="error", error=call.error)
        call.latency_ms = int((time.perf_counter() - t0) * 1000)
        price = PRICES.get(call.model.split(":")[-1])
        if price:
            call.est_cost_usd = round((call.input_tokens * price[0] + call.output_tokens * price[1]) / 1e6, 5)
        self.ndb.add(call)
        self.ndb.commit()
        return result, call

    # -------------------------------------------------------------- document
    def _document(self, o, opp, rows, shortlist, r: MatchResult, concerns, generator, validation) -> dict:
        ai = generator.startswith("ai:")
        hyp_label = "AI suggestion: please check" if ai else "Suggestion: please check"
        stage = {x["faculty_id"]: x for x in rows}

        def person(fid):
            d = shortlist[fid]
            return {"faculty_id": fid, "name": d.name, "title": d.title, "school": d.school, "departments": d.departments[:3],
                    "profile_url": d.source_url, "directory": d.directory}

        def documented(fid, ids):
            d = shortlist[fid]
            return [{**d.evidence[i].as_dict(), "quote": d.evidence[i].text} for i in ids if i in d.evidence]

        def coauthor_pairs(ids):
            return [[shortlist[a].name, shortlist[b].name] for i, a in enumerate(ids) for b in ids[i + 1:]
                    if b in shortlist[a].coauthor_ids or a in shortlist[b].coauthor_ids]

        top = [{**person(p.faculty_id), "match_score": p.relevance_score, "stage_a_score": stage[p.faculty_id]["score"],
                "explanation": {"text": p.why_relevant, "label": hyp_label},
                "documented_evidence": documented(p.faculty_id, p.evidence_ids)} for p in r.top_faculty]
        teams = []
        for t in r.teams:
            ids = [m.faculty_id for m in t.members]
            teams.append({
                "name": t.name, "match_score": t.match_score, "score_explanation": t.score_explanation,
                "complementarity": {"text": t.complementarity_hypothesis, "label": hyp_label},
                "members": [{**person(m.faculty_id), "proposed_role": {"text": m.proposed_role, "label": hyp_label},
                             "contribution": {"text": m.contribution_hypothesis, "label": hyp_label},
                             "documented_evidence": documented(m.faculty_id, m.evidence_ids)} for m in t.members],
                "requirements_covered": t.requirements_covered, "missing_expertise": t.missing_expertise,
                "schools": sorted({shortlist[i].school for i in ids if shortlist[i].school}),
                "verified_existing_coauthors": coauthor_pairs(ids),
            })
        return {
            "opportunity": {"id": o.id, "uid": o.uid, "number": o.opportunity_number, "title": o.title,
                            "funder": o.organization.name if o.organization else None, "deadline": o.deadline, "status": o.status,
                            "verification_status": o.verification_status, "official_url": o.official_url},
            "generated_by": generator, "prompt_version": PROMPT_VERSION,
            "strategic_alignment": {
                "documented": [{"priority": PRIORITY_NAMES.get(p.priority), "confidence": p.confidence_label, "explanation": plain_explanation(p.explanation)}
                               for p in o.priorities],
                "assessment": {"text": r.yigh_alignment, "label": hyp_label}},
            "overall": {"match_score": r.overall_match_score, "explanation": {"text": r.overall_explanation, "label": hyp_label}},
            "top_faculty": top, "teams": teams,
            "missing_capabilities": {"items": r.missing_capabilities, "label": hyp_label},
            "eligibility_concerns": concerns,
            "shortlist": [{"faculty_id": x["faculty_id"], "name": x["name"], "stage_a_score": x["score"], "matched": x["matched"]} for x in rows],
            "sources": sorted({o.official_url} | {shortlist[x["faculty_id"]].source_url for x in rows}),
            "validation": validation,
            "notes": [
                "Everything about a person is quoted from their public Yale profile, with a link so you can check it.",
                "Roles, team fit and scores are suggestions about how people's work could fit together, not facts.",
                "Nothing here means anyone is interested, available or eligible. People marked as past co-authors are listed together on their Yale profiles.",
                "Confirm the opportunity's requirements on the funder's official page before acting.",
            ],
        }

    # -------------------------------------------------------------- triggers (Step 4)
    def refresh(self, trigger: str, opportunity_ids: list[int] | None = None, force: bool = False) -> dict:
        """new/updated opportunities (from a Radar run), faculty profile updates, or an admin request.
        Unchanged inputs hit the cache, so only genuinely affected opportunities cost a model call."""
        if trigger == "faculty_updated":
            self.reload_faculty()
        ids = opportunity_ids or [o.id for o in self.rdb.scalars(select(Opportunity).where(Opportunity.status.in_(["open", "forecasted"])))
                                  if o.priorities]
        hits = misses = 0
        for i in ids:
            doc = self.recommend(i, force=force, trigger=trigger)
            hits += doc["cache"]["hit"]
            misses += not doc["cache"]["hit"]
        return {"trigger": trigger, "opportunities": len(ids), "cache_hits": hits, "recomputed": misses}

    def refresh_after_radar_run(self, run_id: int | None = None) -> dict:
        from backend.radar.models import DiscoveryRun
        from backend.radar.api import _latest_weekly
        run = self.rdb.get(DiscoveryRun, run_id) if run_id else _latest_weekly(self.rdb)
        if run is None:
            return {"trigger": "radar_run", "opportunities": 0}
        ids = [o.id for o in self.rdb.scalars(select(Opportunity).where(
            (Opportunity.first_seen_run_id == run.id) | (Opportunity.last_changed_run_id == run.id))) if o.status != "closed"]
        return self.refresh("radar_run", ids)

    def model_call_log(self, limit: int = 100) -> dict:
        calls = self.ndb.scalars(select(ModelCall).order_by(ModelCall.id.desc()).limit(limit)).all()
        return {"totals": {"calls": len(calls), "input_tokens": sum(c.input_tokens for c in calls),
                           "output_tokens": sum(c.output_tokens for c in calls), "est_cost_usd": round(sum(c.est_cost_usd for c in calls), 4),
                           "errors": sum(c.status != "ok" for c in calls)},
                "calls": [{"opportunity_uid": c.opportunity_uid, "model": c.model, "started_at": c.started_at, "latency_ms": c.latency_ms,
                           "requests": c.requests, "input_tokens": c.input_tokens, "output_tokens": c.output_tokens,
                           "est_cost_usd": c.est_cost_usd, "status": c.status, "error": c.error} for c in calls]}
