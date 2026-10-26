"""Faculty retrieval over documented profile data only.

Every searchable fact carries an evidence id ("F<faculty>-<kind>-<n>"), the quoted text and the
source URL, so later stages (and the AI agent) can only cite things that are actually on record.
Publication lists were not collected from profiles; "projects" search covers profile activities
(research projects, with dates and places) and bios.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.app.matching.config import METHOD_KEYWORDS, broader
from backend.app.models import (Faculty, FacultyActivity, FacultyAppointment, FacultyInterest, FacultyKeyword,
                                FacultyPriority, FacultyRegion)

PRIORITY_SLUGS = {"Climate & Health": "climate-health", "Digital Health & AI": "digital-health-ai",
                  "Health Diplomacy & Security": "health-diplomacy-security", "Health Sovereignty": "health-sovereignty"}
_TOKEN = re.compile(r"[a-z][a-z\-]{2,}")
STOP = set("the and for with from that this are was were their its into using use used based study studies research health "
           "global public new also has have her his they them which who will can our all more such other these those than "
           "through about between within over under across including include work works program programs".split())


def tokens(text: str) -> list[str]:
    return [t for t in _TOKEN.findall((text or "").lower()) if t not in STOP]


@dataclass
class Evidence:
    id: str
    kind: str          # expertise | method | priority | geography | project | interest | organization | coauthor | appointment | bio
    label: str
    text: str
    source_url: str
    confidence: str | None = None
    origin: str = "profile"  # profile = verbatim/listed; rule-tag = rule-based tag with quoted evidence

    def as_dict(self):
        return self.__dict__.copy()


@dataclass
class Dossier:
    id: int
    name: str
    title: str | None
    school: str | None
    departments: list[str]
    source_url: str
    directory: str
    expertise: dict[str, Evidence] = field(default_factory=dict)
    methods: dict[str, Evidence] = field(default_factory=dict)
    priorities: dict[str, Evidence] = field(default_factory=dict)
    places: dict[str, Evidence] = field(default_factory=dict)
    projects: list[Evidence] = field(default_factory=list)
    interests: list[str] = field(default_factory=list)
    organizations: list[str] = field(default_factory=list)
    coauthor_ids: set[int] = field(default_factory=set)
    bio: str = ""
    evidence: dict[str, Evidence] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return " ".join([self.title or "", self.bio, " ".join(self.interests)] + [p.text for p in self.projects])

    def fingerprint(self) -> str:
        """Changes whenever the documented profile or its tags change (drives cache invalidation)."""
        payload = json.dumps([self.name, self.title, self.bio, sorted(self.expertise), sorted(self.methods), sorted(self.priorities),
                              sorted(self.places), [p.text for p in self.projects], sorted(self.interests)], sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def summary(self, max_evidence: int = 12) -> dict:
        """Compact, citation-ready view for the agent."""
        ev = list(self.expertise.values()) + list(self.methods.values()) + list(self.priorities.values()) + \
            list(self.places.values()) + self.projects[:4]
        return {"faculty_id": self.id, "name": self.name, "title": self.title, "school": self.school,
                "departments": self.departments[:3], "profile_url": self.source_url, "directory": self.directory,
                "expertise": sorted(self.expertise), "methods": sorted(self.methods), "yig_priorities": sorted(self.priorities),
                "places": sorted(self.places), "self_listed_interests": self.interests[:15],
                "evidence": [{"id": e.id, "kind": e.kind, "label": e.label, "quote": e.text[:240]} for e in ev[:max_evidence]]}


def _ev(d: Dossier, kind: str, label: str, text: str, confidence=None, origin="profile") -> Evidence:
    e = Evidence(f"F{d.id}-{kind[:3]}-{len(d.evidence) + 1}", kind, label, text, d.source_url, confidence, origin)
    d.evidence[e.id] = e
    return e


def load_dossiers(db: Session) -> dict[int, Dossier]:
    rows = db.scalars(select(Faculty).options(
        selectinload(Faculty.school), selectinload(Faculty.appointments).selectinload(FacultyAppointment.department),
        selectinload(Faculty.keywords).selectinload(FacultyKeyword.keyword),
        selectinload(Faculty.priorities).selectinload(FacultyPriority.priority),
        selectinload(Faculty.regions).selectinload(FacultyRegion.region),
        selectinload(Faculty.interests).selectinload(FacultyInterest.interest),
        selectinload(Faculty.activities), selectinload(Faculty.organizations), selectinload(Faculty.coauthors)))
    out = {}
    for f in rows:
        d = Dossier(f.id, f.name, f.title, f.school.name if f.school else None,
                    sorted({a.department.name for a in f.appointments if a.department}), f.source_url, f.source, bio=f.bio or "")
        first = lambda row: (json.loads(row.evidence or "[]") or [{}])[0]
        for k in f.keywords:
            ev = first(k)
            target = d.methods if k.keyword.name in METHOD_KEYWORDS else d.expertise
            target[k.keyword.name] = _ev(d, "method" if target is d.methods else "expertise", k.keyword.name,
                                         ev.get("snippet") or k.keyword.name, k.confidence_label, "rule-tag")
        for p in f.priorities:
            d.priorities[p.priority.name] = _ev(d, "priority", p.priority.name, first(p).get("snippet") or p.explanation,
                                                p.confidence_label, "rule-tag")
        for r in f.regions:
            d.places[r.region.name] = _ev(d, "geography", r.region.name, first(r).get("snippet") or r.region.name,
                                          r.confidence_label, "rule-tag")
        for a in f.activities:
            if a.activity_type in ("Research", "PatientCare", "VolunteerActivity") and a.title:
                locs = ", ".join(json.loads(a.locations or "[]"))
                when = f"{a.start_date.year if a.start_date else '?'}–{a.end_date.year if a.end_date else 'present'}"
                d.projects.append(_ev(d, "project", a.title, f"{a.title} ({a.activity_type}, {when}{'; ' + locs if locs else ''})"
                                      f"{': ' + a.synopsis if a.synopsis else ''}"))
        d.interests = [i.interest.name for i in f.interests]
        d.organizations = [o.name for o in f.organizations]
        d.coauthor_ids = {c.coauthor_faculty_id for c in f.coauthors if c.coauthor_faculty_id}
        out[f.id] = d
    return out


# ------------------------------------------------------------------ retrieval tools (Step 1)

class FacultyIndex:
    def __init__(self, dossiers: dict[int, Dossier]):
        self.d = dossiers
        self.N = len(dossiers)
        self.df = Counter()
        self.doc_tokens = {}
        for i, d in dossiers.items():
            toks = tokens(d.text)
            self.doc_tokens[i] = Counter(toks)
            self.df.update(set(toks))
        self.avgdl = sum(sum(c.values()) for c in self.doc_tokens.values()) / max(1, self.N)
        tag_df = Counter()
        for d in dossiers.values():
            tag_df.update(set(d.expertise) | set(d.methods))
        self.tag_spec = {t: math.log((self.N + 1) / (c + 1)) / math.log(self.N + 1) for t, c in tag_df.items()}

    def _hit(self, d: Dossier, evs: list[Evidence]):
        return {"faculty_id": d.id, "name": d.name, "school": d.school, "profile_url": d.source_url,
                "evidence": [e.as_dict() for e in evs]}

    def by_expertise(self, terms: list[str]) -> list[dict]:
        want = {t.lower() for t in terms}
        return [self._hit(d, [e for k, e in d.expertise.items() if k.lower() in want] +
                          [e for e in d.evidence.values() if e.kind == "interest"])
                for d in self.d.values() if want & ({k.lower() for k in d.expertise} | {i.lower() for i in d.interests})]

    def by_method(self, methods: list[str]) -> list[dict]:
        want = {m.lower() for m in methods}
        return [self._hit(d, [e for k, e in d.methods.items() if k.lower() in want]) for d in self.d.values()
                if want & {k.lower() for k in d.methods}]

    def by_school(self, school: str | None = None, department: str | None = None) -> list[dict]:
        return [self._hit(d, []) for d in self.d.values() if (not school or d.school == school)
                and (not department or any(department.lower() in x.lower() for x in d.departments))]

    def by_priority(self, priority: str) -> list[dict]:
        return [self._hit(d, [d.priorities[priority]]) for d in self.d.values() if priority in d.priorities]

    def by_geography(self, place: str) -> list[dict]:
        """Exact place, or places in the same wider region (Kenya ~ East Africa ~ Sub-Saharan Africa)."""
        wanted = {place} | broader(place)
        out = []
        for d in self.d.values():
            evs = [e for p, e in d.places.items() if p == place or p in wanted or place in broader(p)]
            if evs:
                out.append(self._hit(d, evs))
        return out

    def projects(self, query: str, k: int = 20) -> list[dict]:
        q = set(tokens(query))
        scored = []
        for d in self.d.values():
            hits = [p for p in d.projects if q & set(tokens(p.text))]
            if hits:
                scored.append((len(q & set(tokens(" ".join(p.text for p in hits)))), d, hits))
        return [self._hit(d, hits) for _, d, hits in sorted(scored, key=lambda x: -x[0])[:k]]

    def bm25(self, query_tokens: list[str], fid: int, k1=1.4, b=0.75) -> float:
        tf, dl = self.doc_tokens[fid], sum(self.doc_tokens[fid].values()) or 1
        score = 0.0
        for t in set(query_tokens):
            if t in tf:
                idf = math.log(1 + (self.N - self.df[t] + 0.5) / (self.df[t] + 0.5))
                score += idf * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * dl / self.avgdl))
        return score
