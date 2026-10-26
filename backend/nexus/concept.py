"""One-page research concept for a proposed team (Launchpad).

AI mode (PydanticAI, when a model/API key is configured) drafts the narrative from the verified
opportunity text and the team's documented evidence. Without a model, a structured OUTLINE is built
only from documented facts (requirements quoted from the call, team roles, partners, gaps) and is
labelled as an outline, not a draft. Either way nothing is invented: no amounts, deadlines or
eligibility beyond the official record, and no claims about anyone's interest or agreement.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone

from pydantic import BaseModel, Field
from pydantic_ai import Agent, NativeOutput
from sqlalchemy import DateTime, String, Text, select
from sqlalchemy.orm import Mapped, mapped_column

from .agent import DEFAULT_MODEL, UNSUPPORTED
from .service import ModelCall, NexusBase, PRICES, ai_available

CONCEPT_VERSION = "concept-v8"


class Concept(NexusBase):
    __tablename__ = "concepts"
    id: Mapped[int] = mapped_column(primary_key=True)
    cache_key: Mapped[str] = mapped_column(String(64), unique=True)
    opportunity_uid: Mapped[str] = mapped_column(String(200))
    generated_by: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    document: Mapped[str] = mapped_column(Text)


class RequirementFit(BaseModel):
    requirement: str = Field(description="quoted or closely paraphrased from the opportunity text")
    how_addressed: str


class ConceptNote(BaseModel):
    working_title: str
    problem_and_significance: str
    aims: list[str] = Field(min_length=1, max_length=4)
    approach: str
    team_roles: list[str]
    partnerships: str
    requirement_fit: list[RequirementFit]
    yigh_alignment: str
    open_questions: list[str]


REQUIREMENT = re.compile(r"[^.]*\b(?:must|should|will (?:support|fund)|are expected to|is expected to|required|requirement|"
                         r"applicants? (?:should|must)|proposals? (?:should|must)|the purpose of|seeks to|objective)\b[^.]*\.", re.I)


def requirements_from_text(text: str, limit: int = 8) -> list[str]:
    text = re.sub(r"([:;.])(?=[A-Z])", r"\1 ", text or "")  # funder text often drops the space after list markers
    return [re.sub(r"\s+", " ", s).strip() for s in REQUIREMENT.findall(text)][:limit]


def _lc(s: str) -> str:
    return s[:1].lower() + s[1:] if s and not s[:2].isupper() else s


def _problem(o: dict, reqs: list[str], goals: list[str] | None) -> str:
    """Only the call's own words plus the user's goals; the team adds the evidence and significance."""
    parts = []
    purpose = next((r for r in reqs if re.search(r"purpose|seeks|objective|will support|will fund", r, re.I)), reqs[0] if reqs else None)
    if purpose:
        parts.append(f"The call says: “{purpose}”")
    if goals:
        parts.append("In response, this team wants to " + "; ".join(_lc(g.rstrip('.')) for g in goals) + ".")
    parts.append("[Team to add: why this matters, who is affected, and what is already known.]")
    return " ".join(parts)


def _approach(team: dict, goals: list[str] | None) -> str:
    who = ", ".join(f"{m['name'].split(',')[0]} ({_lc(m['proposed_role']['text'])})" for m in team["members"])
    lead = f"Possible team: {who}." if who else ""
    plan = (" Work would be organized around the aims above." if goals else "") + " [Team to add: methods, setting, timeline and how each aim will be measured.]"
    return (lead + plan).strip()


def _outline(ws: dict, team: dict, goals: list[str] | None = None) -> dict:
    o = ws["opportunity"]
    reqs = requirements_from_text(o.get("description") or "")
    partners = next((t["partners"] for t in ws["external_partners"]["teams"] if t["team"] == team["name"]), [])
    return {
        "working_title": f"Concept: {o['title']}",
        "problem_and_significance": _problem(o, reqs, goals),
        "aims": [f"{g.rstrip('.')}." for g in goals] if goals else ["To be defined by the team, addressing each requirement listed below."],
        "approach": _approach(team, goals),
        "team_roles": [f"{m['name']}: {m['proposed_role']['text']}" for m in team["members"]],
        "partnerships": "; ".join(f"{p['name']} ({p['country']}, {'already connected to Yale' if p['relationship']['status'] == 'documented' else 'new suggestion'})" for p in partners[:5]) or
                        "No external partners identified.",
        "requirement_fit": [{"requirement": r, "how_addressed": "To be addressed by the team."} for r in reqs] or
                           [{"requirement": "No explicit requirement sentences found in the official description; read the full announcement.",
                             "how_addressed": "-"}],
        "yigh_alignment": ", ".join(a["priority"] for a in ws["strategic_alignment"]["documented"] if a["priority"]) or "Not determined",
        "open_questions": ws["eligibility_and_collaboration_gaps"][:8],
    }


def build_concept(matcher, ws: dict, team_name: str | None = None, model=None, goals: list[str] | None = None) -> dict:
    team = next((t for t in ws["teams"] if t["name"] == team_name), ws["teams"][0] if ws["teams"] else None)
    if team is None:
        raise ValueError("No team proposed for this opportunity")
    use_ai = model is not None or ai_available()
    from backend import llm
    model_id = getattr(model, "model_name", None) or llm.model_name()
    gen = f"ai:{model_id}" if use_ai else "outline"
    o = ws["opportunity"]
    goals = [g.strip() for g in (goals or []) if g.strip()][:8]
    key = hashlib.sha256(json.dumps([o["uid"], o.get("last_changed_at"), team, gen, CONCEPT_VERSION, goals], default=str).encode()).hexdigest()
    NexusBase.metadata.create_all(bind=matcher.ndb.get_bind(), tables=[Concept.__table__])
    hit = matcher.ndb.scalar(select(Concept).filter_by(cache_key=key))
    if hit:
        return {**json.loads(hit.document), "cache": {"hit": True}}

    removed, err = [], None
    if use_ai:
        agent = Agent(model or llm.model(), output_type=NativeOutput(ConceptNote), defer_model_check=True,
                      instructions=("Draft a ONE-PAGE research concept (≈450 words total) for the Yale team below, aligned with the funding "
                                    "opportunity's stated requirements. Use only the opportunity text and the team's documented evidence. "
                                    "Do not state amounts, deadlines or eligibility beyond the opportunity text. Do not claim anyone is "
                                    "interested, available, eligible, or has agreed to anything; describe roles as proposed. "
                                    "Build the aims around the user's goals when given, and show how each goal meets the call. "
                                    "Write in clear, plain language for busy faculty; avoid jargon such as 'documented' or 'evidence' and say what people work on. "
                                    "List unresolved items in open_questions."))
        prompt = json.dumps({"user_goals": goals, "opportunity": {k: o.get(k) for k in ("title", "description", "eligibility", "deadline_text", "award_text")},
                             "requirements_quoted": requirements_from_text(o.get("description") or ""),
                             "team": [{"name": m["name"], "proposed_role": m["proposed_role"]["text"],
                                       "documented_evidence": [e["quote"][:200] for e in m["documented_evidence"][:3]]} for m in team["members"]],
                             "partners": [{"name": p["name"], "country": p["country"],
                                          "yale_connection": "already connected to Yale (public source)" if p["relationship"]["status"] == "documented"
                                          else "new suggestion, no known Yale connection"}
                                          for t in ws["external_partners"]["teams"] if t["team"] == team["name"] for p in t["partners"]],
                             "gaps": ws["eligibility_and_collaboration_gaps"]}, default=str)
        t0, call = time.perf_counter(), ModelCall(opportunity_uid=o["uid"], model=model_id, started_at=datetime.now(timezone.utc).replace(tzinfo=None),
                                                  latency_ms=0, status="ok")
        try:
            r = agent.run_sync(prompt, usage_limits=llm.limits("one_pager"))
            note = r.output.model_dump()
            llm.record("one_pager", r.usage, latency_s=time.perf_counter() - t0)
            call.requests, call.input_tokens, call.output_tokens = r.usage.requests, r.usage.input_tokens, r.usage.output_tokens
        except Exception as e:  # noqa: BLE001
            note, err, gen = None, f"{type(e).__name__}: {e}", "outline (AI error)"
            llm.record("one_pager", None, latency_s=time.perf_counter() - t0, status="error", error=err)
            call.status, call.error = "error", err[:2000]
        call.latency_ms = int((time.perf_counter() - t0) * 1000)
        p = PRICES.get(model_id.split(":")[-1])
        if p:
            call.est_cost_usd = round((call.input_tokens * p[0] + call.output_tokens * p[1]) / 1e6, 5)
        matcher.ndb.add(call)
        if note:
            def scrub(v):
                if isinstance(v, str):
                    removed.extend(m.group(0) for m in UNSUPPORTED.finditer(v))
                    return UNSUPPORTED.sub(" [removed: unsupported claim] ", v)
                if isinstance(v, list):
                    return [scrub(x) for x in v]
                if isinstance(v, dict):
                    return {k: scrub(x) for k, x in v.items()}
                return v
            note = scrub(note)
    if not use_ai or note is None:
        note = _outline(ws, team, goals)
    doc = {"opportunity": {k: o.get(k) for k in ("id", "title", "funder", "deadline", "deadline_text", "award_text", "official_url")},
           "team": team["name"], "generated_by": gen, "concept": note, "goals": goals,
           "label": "AI draft: check every statement before using it" if gen.startswith("ai:") else
                    "An outline to fill in: it lists what the call asks for and who could do what (no AI was used)",
           "removed_unsupported_claims": removed, "model_error": err,
           "sources": ws["sources"]}
    matcher.ndb.add(Concept(cache_key=key, opportunity_uid=o["uid"], generated_by=gen,
                            created_at=datetime.now(timezone.utc).replace(tzinfo=None), document=json.dumps(doc, default=str)))
    matcher.ndb.commit()
    return {**doc, "cache": {"hit": False}}
