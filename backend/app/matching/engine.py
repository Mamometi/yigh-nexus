"""Collaboration matching engine for Constellation.

Each candidate pair gets five criterion scores in [0, 1]; the match score is their
weighted sum (weights from config, normalized to 1). Every reason in the explanation
points to stored evidence (a profile sentence or listed interest). The engine never
asserts that two people already know each other or have collaborated: no such data
is stored.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import Faculty, FacultyCoauthor, FacultyInterest, FacultyKeyword, FacultyPriority, FacultyRegion
from .config import (CRITERIA, DEFAULT_MIN_SCORE, METHOD_KEYWORDS, MIN_CONTEXT_SPECIFICITY, MIN_SUBSTANTIVE,
                     OVERLAP_SATURATION,
                     RELATED_TOPICS, broader)

DISCLAIMER = ("Suggestions come from public Yale profile text. 'Already co-authors' is taken from the Yale Co-Authors "
              "list on public profiles (based on publications); people without that label may still know or work with each other.")


@dataclass
class Tag:
    name: str
    confidence: float
    label: str
    field: str | None
    snippet: str | None


@dataclass
class Profile:
    id: int
    name: str
    title: str | None
    school: str | None
    departments: set[str]
    source_url: str
    keywords: dict[str, Tag]
    interests: dict[str, str]          # lowercased -> as listed on profile (source data, not generated)
    regions: dict[str, Tag]
    priorities: dict[str, Tag]         # priority name -> tag
    organizations: dict[str, str] = field(default_factory=dict)   # lowercased -> as listed (source data)
    coauthor_ids: set[int] = field(default_factory=set)            # verified, from "Yale Co-Authors"
    specificity: dict[str, float] = field(default_factory=dict, repr=False)  # shared across profiles

    def spec(self, term: str) -> float:
        """How distinctive a keyword/interest is across all faculty (IDF scaled to 0-1).
        A theme nearly everyone lists ('Global Health') says little about fit."""
        return self.specificity.get(term.lower(), 1.0)

    @property
    def methods(self):
        return {k for k in self.keywords if k in METHOD_KEYWORDS}

    @property
    def topics(self):
        return {k for k in self.keywords if k not in METHOD_KEYWORDS}


def _tag(name, row) -> Tag:
    ev = json.loads(row.evidence or "[]")
    first = ev[0] if ev else {}
    return Tag(name, row.confidence, row.confidence_label, first.get("field"), first.get("snippet"))


def load_profiles(db: Session) -> dict[int, Profile]:
    rows = db.scalars(select(Faculty).options(
        selectinload(Faculty.school), selectinload(Faculty.department),
        selectinload(Faculty.appointments),
        selectinload(Faculty.keywords).selectinload(FacultyKeyword.keyword),
        selectinload(Faculty.interests).selectinload(FacultyInterest.interest),
        selectinload(Faculty.regions).selectinload(FacultyRegion.region),
        selectinload(Faculty.priorities).selectinload(FacultyPriority.priority),
        selectinload(Faculty.organizations), selectinload(Faculty.coauthors),
    ))
    out = {}
    for f in rows:
        depts = {a.department.name for a in f.appointments if a.department} | ({f.department.name} if f.department else set())
        out[f.id] = Profile(
            id=f.id, name=f.name, title=f.title, school=f.school.name if f.school else None,
            departments=depts, source_url=f.source_url,
            keywords={k.keyword.name: _tag(k.keyword.name, k) for k in f.keywords},
            interests={i.interest.name.lower(): i.interest.name for i in f.interests},
            regions={r.region.name: _tag(r.region.name, r) for r in f.regions},
            priorities={p.priority.name: _tag(p.priority.name, p) for p in f.priorities},
            organizations={o.name.lower(): o.name for o in f.organizations},
            coauthor_ids={c.coauthor_faculty_id for c in f.coauthors if c.coauthor_faculty_id},
        )
    # Specificity = inverse document frequency over keywords + profile interests.
    n = len(out)
    df = Counter()
    for p in out.values():
        df.update({k.lower() for k in p.keywords} | set(p.interests) | {f"org:{o}" for o in p.organizations})
    spec = {t: math.log((n + 1) / (c + 1)) / math.log(n + 1) for t, c in df.items()}
    for p in out.values():
        p.specificity = spec
    return out


# ---------------------------------------------------------------- evidence helpers

def _ev(p: Profile, tag: Tag | None, fallback: str | None = None) -> dict:
    if tag and tag.snippet:
        return {"faculty_id": p.id, "faculty": p.name, "field": tag.field, "text": tag.snippet}
    return {"faculty_id": p.id, "faculty": p.name, "field": "research_interests", "text": fallback}


@dataclass
class Reason:
    criterion: str
    text: str
    evidence: list[dict] = field(default_factory=list)
    strength: float = 0.0
    tag: str | None = None  # short label for UI chips, e.g. "Malaria" or "Health Economics"

    def as_dict(self):
        return {"criterion": self.criterion, "text": self.text, "evidence": self.evidence, "tag": self.tag}


# ---------------------------------------------------------------- criteria

def shared_interests(a: Profile, b: Profile) -> tuple[float, list[Reason]]:
    reasons, total = [], 0.0
    for k in sorted(set(a.keywords) & set(b.keywords)):
        s = min(a.keywords[k].confidence, b.keywords[k].confidence) * a.spec(k)
        total += s
        reasons.append(Reason("shared_interests", f"Both work on {k}.",
                              [_ev(a, a.keywords[k]), _ev(b, b.keywords[k])], s, k))
    covered = {k.lower() for k in a.keywords} & {k.lower() for k in b.keywords}
    for low in sorted(set(a.interests) & set(b.interests) - covered):
        s = 0.9 * a.spec(low)  # both listed it themselves on their profiles
        total += s
        reasons.append(Reason("shared_interests", f"Both list '{a.interests[low]}' as a research interest on their profiles.",
                              [_ev(a, None, a.interests[low]), _ev(b, None, b.interests[low])], s, a.interests[low]))
    for low in sorted(set(a.organizations) & set(b.organizations)):
        s = 0.8 * a.spec(f"org:{low}")  # listed on both profiles; common ones (e.g. YIGH itself) count little
        if s < 0.2:  # skip near-universal listings (YIGH itself, the school of public health, ...)
            continue
        total += s
        reasons.append(Reason("shared_interests",
                              f"Both list {a.organizations[low]} under Other Departments & Organizations on their profiles.",
                              [_ev(a, None, a.organizations[low]) | {"field": "organizations"},
                               _ev(b, None, b.organizations[low]) | {"field": "organizations"}], s, a.organizations[low]))
    reasons.sort(key=lambda r: -r.strength)
    return min(1.0, total / OVERLAP_SATURATION), reasons


def _shared_context(a: Profile, b: Profile) -> list[str]:
    """Common ground that makes a methods complement meaningful."""
    ctx = [f"shared work on {t}" for t in sorted(a.topics & b.topics, key=a.spec, reverse=True) if a.spec(t) >= MIN_CONTEXT_SPECIFICITY]
    ctx += [f"related topics ({x} / {y})" for x in a.topics for y in b.topics if (x, y) in RELATED_TOPICS or (y, x) in RELATED_TOPICS]
    ctx += [f"a shared focus on {g}" for g in sorted(set(a.regions) & set(b.regions))]
    ctx += [f"the {p} priority" for p in sorted(set(a.priorities) & set(b.priorities))]
    return ctx


def complementary_expertise(a: Profile, b: Profile) -> tuple[float, list[Reason]]:
    reasons, points = [], 0.0
    ctx = _shared_context(a, b)
    # (1) one brings a method the other lacks, given some common ground
    if ctx:
        for giver, taker in ((a, b), (b, a)):
            if not taker.topics:
                continue
            offers = sorted(giver.methods - taker.methods, key=lambda m: -giver.keywords[m].confidence * giver.spec(m))
            for m in offers[:2]:  # at most two methods per direction
                s = 0.5 * giver.keywords[m].confidence * giver.spec(m)
                points += s
                reasons.append(Reason("complementary_expertise",
                    f"{giver.name} brings {m} expertise that {taker.name}'s profile does not mention; "
                    f"common ground: {ctx[0]}.", [_ev(giver, giver.keywords[m])], s,
                    f"{giver.name.split(',')[0]} brings {m}"))
    # (2) adjacent but different topics
    for x in sorted(a.topics - b.topics):
        for y in sorted(b.topics - a.topics):
            why = RELATED_TOPICS.get((x, y)) or RELATED_TOPICS.get((y, x))
            if why:
                s = 0.6 * min(a.keywords[x].confidence, b.keywords[y].confidence) * (a.spec(x) + b.spec(y)) / 2
                points += s
                reasons.append(Reason("complementary_expertise",
                    f"{a.name} works on {x} and {b.name} on {y}, which are linked: {why}.",
                    [_ev(a, a.keywords[x]), _ev(b, b.keywords[y])], s, f"{x} ↔ {y}"))
    reasons.sort(key=lambda r: -r.strength)
    return min(1.0, points), reasons


def geography(a: Profile, b: Profile) -> tuple[float, list[Reason]]:
    reasons, best, n = [], 0.0, 0
    for g in sorted(set(a.regions) & set(b.regions)):
        s = min(a.regions[g].confidence, b.regions[g].confidence)
        best, n = max(best, s), n + 1
        reasons.append(Reason("geography", f"Both profiles describe work in or on {g}.",
                              [_ev(a, a.regions[g]), _ev(b, b.regions[g])], s, g))
    if not reasons:  # related geography only counts when nothing is shared exactly
        for x in sorted(a.regions):
            for y in sorted(b.regions):
                common = (broader(x) | {x}) & (broader(y) | {y})
                if x != y and common:
                    s = 0.5 * min(a.regions[x].confidence, b.regions[y].confidence)
                    best = max(best, s)
                    reasons.append(Reason("geography",
                        f"{a.name}'s work in {x} and {b.name}'s work in {y} are both in {sorted(common)[0]}.",
                        [_ev(a, a.regions[x]), _ev(b, b.regions[y])], s, f"{x} / {y}"))
    reasons.sort(key=lambda r: -r.strength)
    return min(1.0, best + 0.15 * max(0, n - 1)), reasons[:3]


def strategic_priorities(a: Profile, b: Profile) -> tuple[float, list[Reason]]:
    reasons, total = [], 0.0
    for p in sorted(set(a.priorities) & set(b.priorities)):
        s = min(a.priorities[p].confidence, b.priorities[p].confidence)
        total += s
        reasons.append(Reason("strategic_priorities",
            f"Both align with YIGH's {p} priority ({a.name}: {a.priorities[p].label}, {b.name}: {b.priorities[p].label} confidence).",
            [_ev(a, a.priorities[p]), _ev(b, b.priorities[p])], s, p))
    return min(1.0, total), reasons


def cross_school(a: Profile, b: Profile) -> tuple[float, list[Reason]]:
    if a.school and b.school and a.school != b.school:
        return 1.0, [Reason("cross_school", f"Cross-school pairing: {a.school} and {b.school}.", [], 1.0)]
    if a.departments & b.departments:
        return 0.0, []
    if a.departments and b.departments:
        return 0.5, [Reason("cross_school", "Same school, different departments: "
                            f"{sorted(a.departments)[0]} and {sorted(b.departments)[0]}.", [], 0.5)]
    return 0.0, []


SCORERS = {"shared_interests": shared_interests, "complementary_expertise": complementary_expertise,
           "geography": geography, "strategic_priorities": strategic_priorities, "cross_school": cross_school}


# ---------------------------------------------------------------- ranking

def _dedupe(tags) -> list[str]:
    """Drop near-duplicate labels ('Infectious Diseases' vs 'Infectious Disease')."""
    seen, out = set(), []
    for t in tags:
        key = re.sub(r"[^a-z]", "", t.lower()).rstrip("s")
        if key not in seen:
            seen.add(key)
            out.append(t)
    return out


def score_pair(a: Profile, b: Profile, weights: dict) -> dict | None:
    parts, reasons = {}, []
    for c in CRITERIA:
        s, r = SCORERS[c](a, b)
        parts[c] = s
        reasons += r
    substantive_w = sum(weights[c] for c in CRITERIA if c != "cross_school")
    substantive = sum(weights[c] * parts[c] for c in CRITERIA if c != "cross_school")
    if substantive_w == 0 or substantive / substantive_w < MIN_SUBSTANTIVE:
        return None  # nothing documented in common: don't recommend on school difference alone
    total = sum(weights[c] * parts[c] for c in CRITERIA)
    coauthors = b.id in a.coauthor_ids or a.id in b.coauthor_ids
    top = sorted((r for r in reasons if r.criterion != "cross_school"), key=lambda r: -weights[r.criterion] * r.strength)
    return {
        "score": round(total, 3),
        # Verified from the profiles' "Yale Co-Authors" lists. Informational only: does not change the score.
        "already_coauthors": coauthors,
        "breakdown": {c: {"score": round(parts[c], 3), "weight": weights[c],
                          "contribution": round(weights[c] * parts[c], 3)} for c in CRITERIA},
        "summary": " ".join(r.text for r in top[:2]),
        "highlights": {c: _dedupe(r.tag for r in sorted(reasons, key=lambda r: -r.strength) if r.criterion == c and r.tag)
                       for c in CRITERIA if c != "cross_school"},
        "reasons": [r.as_dict() for r in sorted(reasons, key=lambda r: (CRITERIA.index(r.criterion), -r.strength))],
    }


def rank_collaborators(profiles: dict[int, Profile], faculty_id: int, weights: dict, limit: int = 10,
                       min_score: float = DEFAULT_MIN_SCORE, cross_school_only: bool = False,
                       new_connections_only: bool = False) -> list[dict]:
    me = profiles[faculty_id]
    results = []
    for other in profiles.values():
        if other.id == me.id:
            continue
        if cross_school_only and (not me.school or me.school == other.school):
            continue
        m = score_pair(me, other, weights)
        if m and new_connections_only and m["already_coauthors"]:
            continue
        if m and m["score"] >= min_score:
            results.append({"faculty": {"id": other.id, "name": other.name, "title": other.title,
                                        "school": other.school, "departments": sorted(other.departments),
                                        "profile_url": other.source_url}, **m})
    results.sort(key=lambda r: -r["score"])
    for i, r in enumerate(results[:limit], 1):
        r["rank"] = i
    return results[:limit]
