"""Evaluation of YIGH Nexus matching against a keyword-search baseline.

    python -m backend.nexus.evaluate pool --n 10        # write blind judging pool (shuffled, no method labels)
    python -m backend.nexus.evaluate score              # compute metrics once judgments exist

Methods compared on the same real, verified opportunities:
  keyword  — count of opportunity-title words in the faculty profile (baseline)
  stage_a  — deterministic documented-overlap shortlist (Stage A)
  rules    — rule-based Stage B teams (no AI)
  ai       — PydanticAI Stage B (only when a model/API key is configured)
Metrics: retrieval relevance (P@5, nDCG@5 from blind 0-2 judgments), team complementarity (requirement
coverage, distinct departments/schools, member reuse across teams), source grounding, unsupported claims,
eligibility accuracy (labelled cases), and model-call latency/tokens/cost.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import re
from pathlib import Path

from sqlalchemy import select

from backend.radar.api import PRIORITY_NAMES
from backend.radar.models import Opportunity

from .agent import UNSUPPORTED
from .service import Matcher, ai_available
from .shortlist import eligibility_concerns, keyword_baseline, profile_opportunity, stage_a

OUT = Path(__file__).resolve().parents[2] / "data" / "nexus_eval"

# Labelled eligibility cases: real Grants.gov/IDRC-style phrasing -> expected concern codes.
ELIGIBILITY_CASES = [
    ("Applicants must be based in a low- or middle-income country.", {"lead_must_be_lmic"}),
    ("Lead applicants must be based in sub-Saharan Africa; partners may be anywhere.", {"lead_must_be_lmic"}),
    ("This is a limited submission: one application per institution.", {"limited_submission"}),
    ("Open to early-stage investigators within 10 years of completing their terminal degree.", {"career_stage"}),
    ("Applicants must be U.S. citizens or permanent residents.", {"us_citizens"}),
    ("Small businesses only (SBIR).", {"small_business"}),
    ("County governments, Small businesses, City or township governments, Nonprofits having a 501(c)(3) status", {"no_higher_ed"}),
    ("Private institutions of higher education, Public and State controlled institutions of higher education, Nonprofits", set()),
    ("Foreign institutions are eligible to apply.", set()),
    ("Unrestricted (i.e., open to any type of entity above), subject to any clarification in text field", set()),
    ("Unrestricted; Please see APS instructions for eligibility criteria.", {"refers_elsewhere"}),
    (None, {"not_stated"}),
]


def pick_opportunities(m: Matcher, n: int) -> list[Opportunity]:
    rows = [o for o in m.rdb.scalars(select(Opportunity).where(Opportunity.status.in_(["open", "forecasted"]),
                                                                Opportunity.verification_status.in_(["verified", "partially_verified"])))
            if o.priorities]
    rows.sort(key=lambda o: (o.verification_status != "verified", o.id))
    return rows[:n]


def pool(n: int):
    m = Matcher()
    OUT.mkdir(parents=True, exist_ok=True)
    items, runs = [], {}
    for o in pick_opportunities(m, n):
        p = profile_opportunity(o, PRIORITY_NAMES)
        ranked = {"keyword": [r["faculty_id"] for r in keyword_baseline(m.ix, p, 5)],
                  "stage_a": [r["faculty_id"] for r in stage_a(m.ix, p, 5)]}
        doc = m.recommend(o.id, mode="rules")
        ranked["rules_top"] = [x["faculty_id"] for x in doc["top_faculty"]]
        if ai_available():
            ranked["ai_top"] = [x["faculty_id"] for x in m.recommend(o.id, mode="ai")["top_faculty"]]
        runs[o.id] = ranked
        cands = list(dict.fromkeys(i for v in ranked.values() for i in v))
        random.Random(o.id).shuffle(cands)  # blind: no method order or labels
        items.append({"opportunity_id": o.id, "title": o.title, "description": (o.description or "")[:2500],
                      "eligibility": (o.eligibility or "")[:600],
                      "candidates": [m.ix.d[i].summary(10) for i in cands]})
    (OUT / "judging_pool.json").write_text(json.dumps(items, indent=1, ensure_ascii=False, default=str))
    (OUT / "rankings.json").write_text(json.dumps(runs, indent=1))
    print(f"pool: {len(items)} opportunities, {sum(len(i['candidates']) for i in items)} (opportunity, faculty) pairs to judge")


def ndcg(rels: list[int], k: int = 5) -> float:
    dcg = sum((2 ** r - 1) / math.log2(i + 2) for i, r in enumerate(rels[:k]))
    ideal = sorted(rels, reverse=True)
    idcg = sum((2 ** r - 1) / math.log2(i + 2) for i, r in enumerate(ideal[:k]))
    return dcg / idcg if idcg else 0.0


def score():
    m = Matcher()
    runs = {int(k): v for k, v in json.loads((OUT / "rankings.json").read_text()).items()}
    judg = {(j["opportunity_id"], j["faculty_id"]): j["relevance"] for j in json.loads((OUT / "judgments.json").read_text())}
    report = {"opportunities": len(runs), "retrieval": {}, "teams": {}, "grounding": {}, "eligibility": {}, "model_calls": {}}

    for method in sorted({k for v in runs.values() for k in v}):
        p5, nd, mean_rel = [], [], []
        for oid, ranked in runs.items():
            ids = ranked.get(method, [])
            if not ids:
                continue
            rels = [judg.get((oid, i), 0) for i in ids[:5]]
            all_rels = [judg.get((oid, i), 0) for i in {x for v in ranked.values() for x in v}]
            p5.append(sum(r >= 1 for r in rels) / 5)
            mean_rel.append(sum(rels) / 5)
            dcg = sum((2 ** r - 1) / math.log2(i + 2) for i, r in enumerate(rels))
            idcg = sum((2 ** r - 1) / math.log2(i + 2) for i, r in enumerate(sorted(all_rels, reverse=True)[:5]))
            nd.append(dcg / idcg if idcg else 0)
        if p5:
            report["retrieval"][method] = {"precision@5": round(sum(p5) / len(p5), 3), "ndcg@5": round(sum(nd) / len(nd), 3),
                                           "mean_relevance@5 (0-2)": round(sum(mean_rel) / len(mean_rel), 3), "n": len(p5)}

    # teams, grounding and unsupported claims, from the stored recommendation documents
    for gen in ("rules", "ai"):
        cov, depts, schools, reuse, grounded, members, claims, rel_members = [], [], [], [], 0, 0, 0, []
        for oid in runs:
            if gen == "ai" and not ai_available():
                continue
            doc = m.recommend(oid, mode=gen)
            seen = []
            for t in doc["teams"]:
                ids = [x["faculty_id"] for x in t["members"]]
                total = len(t["requirements_covered"]) + len(t["missing_expertise"])
                cov.append(len(t["requirements_covered"]) / total if total else 0)
                depts.append(len({x["departments"][0] if x["departments"] else x["school"] for x in t["members"]}))
                schools.append(len(t["schools"]))
                reuse.append(len(set(ids) & set(seen)) / len(ids))
                seen += ids
                for x in t["members"]:
                    members += 1
                    grounded += bool(x["documented_evidence"]) and all(e["source_url"] for e in x["documented_evidence"])
                    rel_members.append(judg.get((oid, x["faculty_id"])))
            # only GENERATED text counts; documented profile quotes may legitimately mention collaborations
            generated = [x["explanation"]["text"] for x in doc["top_faculty"]] + [doc["overall"]["explanation"]["text"],
                         doc["strategic_alignment"]["assessment"]["text"]]
            for t in doc["teams"]:
                generated += [t["complementarity"]["text"], t["score_explanation"]] + \
                             [x for mem in t["members"] for x in (mem["proposed_role"]["text"], mem["contribution"]["text"])]
            claims += sum(len(UNSUPPORTED.findall(g or "")) for g in generated)
        if members:
            judged = [r for r in rel_members if r is not None]
            report["teams"][gen] = {"teams": len(cov), "mean_requirement_coverage": round(sum(cov) / len(cov), 3),
                                    "mean_distinct_departments": round(sum(depts) / len(depts), 2),
                                    "mean_distinct_schools": round(sum(schools) / len(schools), 2),
                                    "member_reuse_across_teams": round(sum(reuse) / len(reuse), 3),
                                    "team_members_judged_relevant": round(sum(r >= 1 for r in judged) / len(judged), 3) if judged else None}
            report["grounding"][gen] = {"members_with_sourced_evidence": round(grounded / members, 3),
                                        "unsupported_claims_in_output": claims}

    tp = fp = fn = 0
    for text, expected in ELIGIBILITY_CASES:
        got = {c["code"] for c in eligibility_concerns(text)}
        tp, fp, fn = tp + len(got & expected), fp + len(got - expected), fn + len(expected - got)
    report["eligibility"] = {"cases": len(ELIGIBILITY_CASES), "precision": round(tp / (tp + fp), 3) if tp + fp else 1.0,
                             "recall": round(tp / (tp + fn), 3) if tp + fn else 1.0}
    report["model_calls"] = m.model_call_log(1000)["totals"]
    report["ai_arm"] = "run" if ai_available() else "not run: no model API key configured"
    (OUT / "report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["pool", "score"])
    ap.add_argument("--n", type=int, default=10)
    a = ap.parse_args()
    pool(a.n) if a.cmd == "pool" else score()
