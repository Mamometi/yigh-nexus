"""Stage B: a PydanticAI agent that evaluates the Stage A shortlist and proposes interdisciplinary teams.

Grounding rules enforced in code (not just in the prompt):
  * the agent can only pick faculty from the shortlist and must cite evidence ids from their dossiers
    (output_validator -> ModelRetry otherwise);
  * claims that faculty are interested, available, eligible or already collaborating are removed unless
    the collaboration is a verified Yale co-authorship;
  * extra eligibility concerns must quote the opportunity's own text, or they are dropped.
When no model/API key is configured, `rule_based_result` builds the same structure deterministically and
is labelled as such.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

from pydantic import BaseModel, Field
from pydantic_ai import Agent, ModelRetry, NativeOutput, RunContext

from .retrieval import Dossier
from .shortlist import OpportunityProfile

PROMPT_VERSION = "nexus-v3"
DEFAULT_MODEL = "anthropic:claude-opus-5-5"  # used only when an Anthropic key is the one configured; see backend/llm.py


def _default_model():
    from backend import llm
    return llm.model()


# ------------------------------------------------------------------ output schema

class FacultyPick(BaseModel):
    faculty_id: int
    relevance_score: int = Field(ge=0, le=100)
    why_relevant: str = Field(description="1-2 sentences tying documented evidence to the opportunity")
    evidence_ids: list[str] = Field(min_length=1, description="ids from this person's dossier evidence list")


class Member(BaseModel):
    faculty_id: int
    proposed_role: str = Field(description="e.g. 'Lead: malaria epidemiology', 'Co-I: health economics'")
    contribution_hypothesis: str = Field(description="How they COULD contribute (a hypothesis, not a claim about their intentions)")
    evidence_ids: list[str] = Field(min_length=1)


class TeamProposal(BaseModel):
    name: str
    members: list[Member] = Field(min_length=2, max_length=5)
    complementarity_hypothesis: str
    requirements_covered: list[str]
    missing_expertise: list[str]
    match_score: int = Field(ge=0, le=100)
    score_explanation: str


class EligibilityNote(BaseModel):
    concern: str
    quote: str = Field(description="verbatim text from the opportunity that raises the concern")


class MatchResult(BaseModel):
    top_faculty: list[FacultyPick] = Field(max_length=5)
    teams: list[TeamProposal] = Field(max_length=3)
    yigh_alignment: str
    missing_capabilities: list[str]
    additional_eligibility_concerns: list[EligibilityNote] = []
    overall_match_score: int = Field(ge=0, le=100)
    overall_explanation: str


@dataclass
class Deps:
    opp: OpportunityProfile
    shortlist: dict[int, Dossier]
    stage_a: dict[int, dict]


INSTRUCTIONS = """You help the Yale Institute for Global Health (YIGH) assemble interdisciplinary research teams for a funding opportunity.

You receive the opportunity (verified from the funder's official record) and a shortlist of Yale faculty. Each faculty dossier lists DOCUMENTED evidence items with ids (quotes from their public Yale profile, or rule-based tags with the quote they came from).

Your job:
1. Pick up to 5 faculty most relevant to this opportunity and say why, citing evidence ids.
2. Propose up to 3 teams of 2-5 people whose documented expertise is complementary: subject matter, methods, field/geographic experience, and different departments or schools where that genuinely helps. Give each member a proposed role and a contribution hypothesis, citing evidence ids.
3. Say how the opportunity aligns with YIGH's priorities (Climate & Health; Digital Health & AI; Health Diplomacy & Security; Health Sovereignty), what expertise or institutional capability is missing from the shortlist, and any further eligibility concerns, quoting the opportunity text.

Rules:
- Only use faculty ids from the shortlist and evidence ids from that person's dossier. Use the tools to look things up.
- Roles and contributions are hypotheses about how expertise could fit. Never state or imply that anyone is interested, available, eligible, or has collaborated with anyone; you do not know that.
- Do not invent expertise, projects, publications or places that are not in the evidence.
- If the shortlist is a weak fit, say so and give low scores. Fewer, well-supported teams are better than padded ones.
- Write for busy faculty in plain, everyday language. Don't use words like "documented", "evidence", "facet" or
  "rule-based"; say what the person works on ("works on genomic surveillance in Kenya")."""

UNSUPPORTED = re.compile(
    r"[^.]*\b(?:(?:is|are|would be|will be) (?:very )?(?:interested|available|eager|keen|willing|eligible)|"
    r"(?:has|have|had) (?:previously |already )?(?:collaborated|worked (?:together|with))|existing collaboration|"
    r"long-standing partnership|already (?:collaborat|work)\w*|has agreed|have agreed|confirmed (?:interest|participation))[^.]*\.?", re.I)



def _and(items) -> str:
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1] if items else ""


def _n(k: int, word: str) -> str:
    return f"{k} {word}{'' if k == 1 else 's'}"

def build_agent(model=None) -> Agent:
    agent = Agent(model or _default_model(), output_type=NativeOutput(MatchResult),
                  deps_type=Deps, instructions=INSTRUCTIONS, retries=2, defer_model_check=True)

    @agent.tool
    def get_faculty_dossier(ctx: RunContext[Deps], faculty_id: int) -> dict:
        """Full documented dossier (evidence items with ids and quotes) for a shortlisted faculty member."""
        d = ctx.deps.shortlist.get(faculty_id)
        if d is None:
            raise ModelRetry(f"{faculty_id} is not on the shortlist. Shortlisted ids: {sorted(ctx.deps.shortlist)}")
        s = d.summary(max_evidence=30)
        s["stage_a"] = ctx.deps.stage_a.get(faculty_id)
        return s

    @agent.tool
    def find_in_shortlist(ctx: RunContext[Deps], kind: str, value: str) -> list[dict]:
        """Search the shortlist. kind: expertise | method | priority | place | project. Returns matching people and evidence ids."""
        out = []
        for d in ctx.deps.shortlist.values():
            pool = {"expertise": d.expertise, "method": d.methods, "priority": d.priorities, "place": d.places}.get(kind)
            if pool is not None:
                evs = [e for k, e in pool.items() if value.lower() in k.lower()]
            elif kind == "project":
                evs = [p for p in d.projects if value.lower() in p.text.lower()]
            else:
                raise ModelRetry("kind must be expertise, method, priority, place or project")
            if evs:
                out.append({"faculty_id": d.id, "name": d.name, "evidence": [{"id": e.id, "quote": e.text[:200]} for e in evs]})
        return out

    @agent.output_validator
    def grounded(ctx: RunContext[Deps], out: MatchResult) -> MatchResult:
        problems = []
        people = [(p.faculty_id, p.evidence_ids) for p in out.top_faculty] + \
                 [(m.faculty_id, m.evidence_ids) for t in out.teams for m in t.members]
        for fid, ev_ids in people:
            d = ctx.deps.shortlist.get(fid)
            if d is None:
                problems.append(f"faculty {fid} is not on the shortlist")
                continue
            bad = [e for e in ev_ids if e not in d.evidence]
            if bad:
                problems.append(f"evidence ids {bad} do not belong to faculty {fid}")
        for t in out.teams:
            if len({m.faculty_id for m in t.members}) != len(t.members):
                problems.append(f"team '{t.name}' lists the same person twice")
        if problems:
            raise ModelRetry("Fix these grounding problems: " + "; ".join(problems))
        return out

    return agent


def opportunity_prompt(opp: OpportunityProfile, shortlist: dict[int, Dossier], stage_a_rows: list[dict], concerns: list[dict]) -> str:
    rows = "\n".join(f"- {r['faculty_id']}: {r['name']} (stage A score {r['score']}; matched {r['matched']})" for r in stage_a_rows)
    dossiers = "\n".join(str(shortlist[r["faculty_id"]].summary(8)) for r in stage_a_rows)
    return (f"OPPORTUNITY (official record)\nTitle: {opp.title}\nDescription: {opp.text[:3500]}\nEligibility: {opp.eligibility or 'not stated'}\n"
            f"Rule-based profile: topics={sorted(opp.topics)}, methods={sorted(opp.methods)}, YIGH priorities={sorted(opp.priorities)}, "
            f"places={sorted(opp.places)}\nEligibility concerns already found (quoted): {[c['concern'] for c in concerns]}\n\n"
            f"SHORTLIST (Stage A)\n{rows}\n\nDOSSIER SUMMARIES\n{dossiers}")


# ------------------------------------------------------------------ post-processing

def scrub_unsupported(result: MatchResult, shortlist: dict[int, Dossier]) -> list[str]:
    """Remove sentences claiming interest/availability/eligibility/collaboration without evidence.
    A collaboration statement is kept only when every pair in that team is a verified Yale co-author pair."""
    removed = []

    def clean(text: str, team_ids: list[int] | None = None) -> str:
        def repl(m):
            s = m.group(0)
            if team_ids and re.search(r"collaborat|worked (?:together|with)", s, re.I):
                pairs = [(a, b) for i, a in enumerate(team_ids) for b in team_ids[i + 1:]]
                if pairs and all(b in shortlist[a].coauthor_ids or a in shortlist[b].coauthor_ids for a, b in pairs):
                    return s
            removed.append(s.strip())
            return " [removed: unsupported claim] "
        return re.sub(r"\s+", " ", UNSUPPORTED.sub(repl, text)).strip()

    for p in result.top_faculty:
        p.why_relevant = clean(p.why_relevant)
    for t in result.teams:
        ids = [m.faculty_id for m in t.members]
        t.complementarity_hypothesis = clean(t.complementarity_hypothesis, ids)
        t.score_explanation = clean(t.score_explanation, ids)
        for m in t.members:
            m.contribution_hypothesis = clean(m.contribution_hypothesis)
            m.proposed_role = clean(m.proposed_role)
    result.yigh_alignment = clean(result.yigh_alignment)
    result.overall_explanation = clean(result.overall_explanation)
    return removed


def validated_eligibility_notes(result: MatchResult, opp: OpportunityProfile) -> tuple[list[dict], list[dict]]:
    """Keep agent eligibility notes only if their quote appears in the opportunity text."""
    hay = re.sub(r"\s+", " ", f"{opp.eligibility or ''} {opp.text}").lower()
    kept, dropped = [], []
    for n in result.additional_eligibility_concerns:
        q = re.sub(r"\s+", " ", n.quote).lower().strip(" .\"'")
        (kept if q and q in hay else dropped).append({"concern": n.concern, "quote": n.quote})
    return kept, dropped


# ------------------------------------------------------------------ rule-based fallback (no AI model)

def rule_based_result(opp: OpportunityProfile, shortlist: dict[int, Dossier], stage_a_rows: list[dict]) -> MatchResult:
    """Deterministic teams: greedy coverage of the opportunity's documented requirements, preferring
    different departments/schools. Roles are rule-based suggestions, labelled as such downstream."""
    facets = [("topic", t) for t in sorted(opp.topics)] + [("method", m) for m in sorted(opp.methods)] + \
             [("place", p) for p in sorted(opp.places)] + [("priority", p) for p in sorted(opp.priorities)]

    def covers(r):
        m = r["matched"]
        return {("topic", t) for t in m["expertise"]} | {("method", x) for x in m["methods"]} | \
               {("place", p) for p in opp.places if any(p == q or p in q for q in m["places"])} | {("priority", p) for p in m["priorities"]}

    def ev(r):
        return r["evidence_ids"][:4] or [next(iter(shortlist[r["faculty_id"]].evidence), "")]

    def plain(m):  # "works on X; uses Y; has worked in Z; fits YIGH's W priority"
        bits = []
        if m.get("expertise"): bits.append("works on " + _and(m["expertise"]))
        if m.get("methods"): bits.append("uses " + _and(m["methods"]))
        if m.get("places"): bits.append("has worked in " + _and(m["places"]))
        if m.get("priorities"): bits.append("fits YIGH's " + _and(m["priorities"]) + (" priorities" if len(m["priorities"]) > 1 else " priority"))
        return "; ".join(bits)

    rows = [r for r in stage_a_rows if r["evidence_ids"]]
    top = [FacultyPick(faculty_id=r["faculty_id"], relevance_score=min(100, int(r["score"] * 100)),
                       why_relevant="Their Yale profile shows they " + plain(r["matched"]) + ".",
                       evidence_ids=ev(r)) for r in rows[:5]]
    teams, used_leads, used_members = [], set(), set()
    for variant in range(3):
        pool = [r for r in rows if r["faculty_id"] not in used_leads]
        if len(pool) < 2:
            break
        team, covered, depts = [], set(), set()
        for _ in range(4):
            best = max(pool, key=lambda r: (len(covers(r) - covered) + (0.5 if not (set(shortlist[r["faculty_id"]].departments) & depts) else 0)
                                            + (0.3 if variant == 2 and shortlist[r["faculty_id"]].school not in {shortlist[x["faculty_id"]].school for x in team} else 0)
                                            - (1.5 if r["faculty_id"] in used_members else 0)  # alternatives should differ
                                            + r["score"]), default=None)
            if best is None:
                break
            if team and not (covers(best) - covered):
                if len(team) > 1:
                    break
                # nobody adds a new facet: pair the lead with the best-matched person from another department
                other = [r for r in pool if not (set(shortlist[r["faculty_id"]].departments) & depts)]
                if not other:
                    break
                best = max(other, key=lambda r: r["score"])
            team.append(best)
            covered |= covers(best)
            depts |= set(shortlist[best["faculty_id"]].departments)
            pool = [r for r in pool if r is not best]
        if len(team) < 2:
            break
        used_leads.add(team[0]["faculty_id"])
        used_members |= {r["faculty_id"] for r in team}
        members = []
        for i, r in enumerate(team):
            new = covers(r)
            label = next((v for k, v in sorted(new) if k in ("topic", "method")), None) or \
                next((f"experience in {v}" for k, v in sorted(new) if k == "place"), None)
            role = (f"Could lead, bringing {label}" if label else "Could lead the team") if i == 0 else \
                   (f"Could bring {label}" if label else "Could add a related perspective")
            members.append(Member(faculty_id=r["faculty_id"], proposed_role=role,
                                  contribution_hypothesis="Suggested because their Yale profile shows they " + plain(r["matched"]) + ".",
                                  evidence_ids=ev(r)))
        missing = [f"{k}: {v}" for k, v in facets if (k, v) not in covered]
        score = int(100 * len(covered) / max(1, len(facets)))
        teams.append(TeamProposal(name=f"Team option {variant + 1}", members=members,
                                  complementarity_hypothesis=f"Between them, they cover {len(covered)} of the {len(facets)} things this call asks for, "
                                                             f"with people from {_n(len({shortlist[r['faculty_id']].school for r in team}), 'school')}.",
                                  requirements_covered=[f"{k}: {v}" for k, v in sorted(covered)], missing_expertise=missing,
                                  match_score=score, score_explanation="How much of what the call asks for (topics, methods, places and YIGH priorities) "
                                                                       "shows up in this team's Yale profiles."))
    all_cov = set().union(*(covers(r) for r in rows)) if rows else set()
    return MatchResult(top_faculty=top, teams=teams,
                       yigh_alignment=(f"This call fits YIGH's {_and(sorted(opp.priorities))} priorities." if len(opp.priorities) > 1 else
                                       f"This call fits YIGH's {next(iter(opp.priorities))} priority." if opp.priorities else
                                       "This call doesn't clearly fit one of YIGH's priorities."),
                       missing_capabilities=[f"{k}: {v}" for k, v in facets if (k, v) not in all_cov],
                       overall_match_score=max([t.match_score for t in teams], default=0),
                       overall_explanation="Suggested automatically by matching the call against Yale profiles (no AI was used).")
