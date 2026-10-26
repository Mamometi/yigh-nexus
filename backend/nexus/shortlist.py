"""Stage A (deterministic shortlist), the keyword-search baseline, and the eligibility checker.

The opportunity is profiled with the SAME transparent rules used for faculty (research areas,
methods, places, YIGH priorities), then faculty are scored on documented overlap. Every point of
score is tied to an evidence id.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from backend.app.classification.rules import extract_geography, extract_keywords
from backend.app.matching.config import METHOD_KEYWORDS, broader

from .retrieval import FacultyIndex, tokens

WEIGHTS = {"expertise": 0.35, "methods": 0.15, "priorities": 0.20, "geography": 0.15, "text": 0.15}
METHOD_HINTS = {
    "Implementation Science": r"implementation (?:science|research)", "Health Economics": r"cost-effectiveness|economic evaluation|health economics",
    "AI & Machine Learning": r"artificial intelligence|machine learning|\bAI\b|deep learning", "Epidemiology": r"epidemiolog\w+|cohort",
    "Biostatistics & Data Science": r"data science|biostatistic\w+|modell?ing|statistical", "Genomics": r"genomic\w*|sequencing",
    "Digital Health": r"digital health|m-?health|mobile health|telemedicine", "Health Policy": r"health policy|policy research",
    "Medical Education & Training": r"research training|training program|capacity building|\bD43\b|mentor\w*",
}


@dataclass
class OpportunityProfile:
    id: int
    uid: str
    title: str
    text: str
    eligibility: str | None
    topics: set[str] = field(default_factory=set)
    methods: set[str] = field(default_factory=set)
    priorities: set[str] = field(default_factory=set)
    places: set[str] = field(default_factory=set)
    official_url: str = ""
    content_hash: str = ""


def profile_opportunity(o, priority_names: dict[str, str]) -> OpportunityProfile:
    text = f"{o.title}. {o.description or ''}"
    kw = extract_keywords({"bio": text})
    methods = {k for k in kw if k in METHOD_KEYWORDS} | {m for m, rx in METHOD_HINTS.items() if re.search(rx, text, re.I)}
    geo_text = " ".join(filter(None, [text, o.geographic_restrictions, o.eligibility]))
    places = {g for g in extract_geography({"activity_locations": "; ".join(re.findall(r"[A-Z][a-z]+(?: [A-Z][a-z]+)*", geo_text))})}
    return OpportunityProfile(o.id, o.uid, o.title, text, o.eligibility, topics={k for k in kw if k not in METHOD_KEYWORDS},
                              methods=methods, priorities={priority_names.get(p.priority, p.priority) for p in o.priorities},
                              places=places - {"United States"}, official_url=o.official_url, content_hash=o.content_hash)


def stage_a(ix: FacultyIndex, opp: OpportunityProfile, k: int = 20) -> list[dict]:
    q = tokens(opp.text)
    bm = {i: ix.bm25(q, i) for i in ix.d}
    top_bm = max(bm.values()) or 1.0
    out = []
    for i, d in ix.d.items():
        ev_ids, parts = [], {}
        exp = [t for t in opp.topics if t in d.expertise]
        parts["expertise"] = min(1.0, sum(ix.tag_spec.get(t, 0.5) for t in exp) / 1.2)
        ev_ids += [d.expertise[t].id for t in exp]
        met = [m for m in opp.methods if m in d.methods]
        parts["methods"] = min(1.0, 0.5 * len(met))
        ev_ids += [d.methods[m].id for m in met]
        pri = [p for p in opp.priorities if p in d.priorities]
        parts["priorities"] = min(1.0, 0.6 * len(pri))
        ev_ids += [d.priorities[p].id for p in pri]
        geo = [p for p in d.places for want in opp.places if p == want or want in broader(p) or p in broader(want)]
        parts["geography"] = 1.0 if any(p in opp.places for p in geo) else (0.5 if geo else 0.0)
        ev_ids += [d.places[p].id for p in dict.fromkeys(geo)]
        parts["text"] = bm[i] / top_bm
        score = sum(WEIGHTS[c] * v for c, v in parts.items())
        if score > 0 and (exp or met or pri or geo or parts["text"] > 0.3):
            out.append({"faculty_id": i, "name": d.name, "score": round(score, 3),
                        "breakdown": {c: round(v, 3) for c, v in parts.items()}, "evidence_ids": ev_ids,
                        "matched": {"expertise": exp, "methods": met, "priorities": pri, "places": list(dict.fromkeys(geo))}})
    return sorted(out, key=lambda r: -r["score"])[:k]


def keyword_baseline(ix: FacultyIndex, opp: OpportunityProfile, k: int = 20) -> list[dict]:
    """Plain keyword search: count of opportunity-title words found in the faculty profile text."""
    q = set(tokens(opp.title))
    scored = [(sum(1 for t in q if t in ix.doc_tokens[i]), i) for i in ix.d]
    return [{"faculty_id": i, "name": ix.d[i].name, "score": s} for s, i in sorted(scored, key=lambda x: -x[0]) if s > 0][:k]


# ------------------------------------------------------------------ eligibility (documented text only)

ELIGIBILITY_RULES = [
    ("lead_must_be_lmic", r"(?:applicants?|lead (?:applicant|institution)s?|organi[sz]ations?|institutions?) (?:must|should) be (?:based|located|registered|headquartered) in "
                          r"(?:a |an )?(?:low|middle|LMIC|Africa|sub-Saharan|Asia|Latin America|the Global South|[A-Z][a-z]+)",
     "The lead applicant must be based in a specific country/region; Yale (a US institution) may only be able to join as a partner."),
    ("foreign_only", r"(?:only|exclusively) (?:foreign|non-U\.?S\.?|international) (?:institutions|organizations|applicants)",
     "Only non-US institutions appear to be eligible."),
    ("us_citizens", r"U\.?S\.? citizens?(?: or (?:permanent residents|nationals))?",
     "Citizenship or residency requirement: confirm for each proposed investigator."),
    ("career_stage", r"early[- ]stage investigators?|new investigators?|early[- ]career|junior faculty|within \d+ years of (?:completing|receiving)",
     "Career-stage restriction: only some proposed team members may qualify as lead."),
    ("limited_submission", r"limited submission|one application per institution|(?:number|limit) of applications per institution",
     "Limited submission: Yale may need to run an internal selection first."),
    ("small_business", r"small business(?:es)? (?:concerns? )?only|SBIR|STTR",
     "Appears restricted to small businesses (SBIR/STTR); universities usually cannot be the applicant."),
    ("refers_elsewhere", r"(?:^|;\s*)(?:please )?(?:see|refer to)\b",
     "The official eligibility statement only refers to another document; confirm the full criteria there."),
]


def eligibility_concerns(eligibility: str | None, description: str | None = None) -> list[dict]:
    """Concerns quoted from the opportunity's own text. Never a statement about any person's eligibility."""
    if not eligibility:
        return [{"code": "not_stated", "concern": "Eligibility is not stated in the official record; confirm with the funder.",
                 "quote": None}]
    out = []
    # Grants.gov lists applicant types. If it lists several and none is a university (and it isn't
    # "unrestricted"), say so — quoting the list, not judging any person.
    types_listed = len(re.findall(r",", eligibility)) >= 2 and re.search(r"governments|nonprofits|businesses|organizations", eligibility, re.I)
    if types_listed and not re.search(r"(?<!other than )institutions of higher education|universit|unrestricted|\bany\b", eligibility, re.I):
        out.append({"code": "no_higher_ed", "quote": eligibility[:240],
                    "concern": "Institutions of higher education do not appear among the eligible applicant types; check the 'Additional Information on Eligibility'."})
    for code, rx, msg in ELIGIBILITY_RULES:
        for field_text in (eligibility, description or ""):
            m = re.search(rx, field_text, re.I | re.M)
            if m:
                start = max(0, m.start() - 60)
                out.append({"code": code, "concern": msg, "quote": field_text[start:m.end() + 60].strip()})
                break
    return out
