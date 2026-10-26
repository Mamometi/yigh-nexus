"""Rule-based classification of faculty profiles.

Reads verbatim profile text from faculty_source_texts and writes generated rows to
faculty_priorities, faculty_keywords and faculty_regions, each with an explanation,
JSON evidence (field + matched term + source sentence), a heuristic confidence
score/label and the rule version. Rows with method='manual' are never touched.

Usage (from the project root):
    .venv/bin/python -m backend.scripts.classify_faculty
"""
import json
from collections import Counter
from pathlib import Path

from sqlalchemy import delete, select

from backend.app.classification.rules import (RULE_VERSION, Result, classify_priorities, extract_geography,
                                              extract_keywords)
from backend.app.database import Base, SessionLocal, engine
from backend.app.models import (Faculty, FacultyKeyword, FacultyPriority, FacultyRegion, StandardKeyword,
                                StrategicPriority)
from backend.scripts.init_db import region

REVIEW_FILE = Path(__file__).resolve().parents[2] / "data" / "classifications_review.json"
# appointments are not used: department names aren't research claims. Organization names are kept for
# matching but not used as tag evidence (the audit found membership alone was misleading).
FIELDS = ("research_interests", "title", "bio", "activities", "activity_locations", "organizations")


def provenance(r: Result) -> dict:
    return dict(confidence=r.confidence, confidence_label=r.confidence_label, method="rules",
                rule_version=RULE_VERSION, explanation=r.explanation,
                evidence=json.dumps([e.as_dict() for e in r.evidence], ensure_ascii=False))


def main() -> None:
    Base.metadata.create_all(engine)
    review, counts = [], Counter()
    with SessionLocal() as db, db.begin():
        for model in (FacultyPriority, FacultyKeyword, FacultyRegion):
            db.execute(delete(model).where(model.method == "rules"))
        priorities = {p.slug: p for p in db.scalars(select(StrategicPriority))}
        keywords = {k.name: k for k in db.scalars(select(StandardKeyword))}

        for f in db.scalars(select(Faculty).order_by(Faculty.name)):
            texts = {s.field: s.text for s in f.source_texts if s.field in FIELDS}
            manual_p = {p.priority_id for p in f.priorities}
            manual_k = {k.keyword_id for k in f.keywords}
            manual_r = {r.region_id for r in f.regions}

            topical = {k: v for k, v in texts.items() if k not in ("activity_locations", "organizations")}
            pr = classify_priorities(topical)
            for slug, res in pr.items():
                if priorities[slug].id not in manual_p:
                    f.priorities.append(FacultyPriority(priority=priorities[slug], **provenance(res)))
                    counts[f"priority:{priorities[slug].name}:{res.confidence_label}"] += 1

            kw = extract_keywords(topical)
            for name, res in kw.items():
                if name not in keywords:
                    keywords[name] = StandardKeyword(name=name)
                    db.add(keywords[name]); db.flush()
                if keywords[name].id not in manual_k:
                    f.keywords.append(FacultyKeyword(keyword=keywords[name], **provenance(res)))

            geo = extract_geography({k: v for k, v in texts.items() if k != "organizations"})
            for name, res in geo.items():
                reg = region(db, name)
                if reg.id not in manual_r:
                    f.regions.append(FacultyRegion(region=reg, **provenance(res)))

            counts["faculty"] += 1
            counts["with_priority"] += bool(pr)
            counts["with_keyword"] += bool(kw)
            counts["with_geography"] += bool(geo)
            counts["no_source_text"] += not texts
            review.append({
                "name": f.name, "source_url": f.source_url,
                "priorities": {priorities[s].name: {"confidence": r.confidence_label, "explanation": r.explanation,
                                                    "evidence": [e.as_dict() for e in r.evidence]} for s, r in pr.items()},
                "keywords": {k: r.confidence_label for k, r in kw.items()},
                "geography": {g: {"confidence": r.confidence_label, "explanation": r.explanation,
                                  "evidence": [e.snippet for e in r.evidence]} for g, r in geo.items()},
            })

    REVIEW_FILE.write_text(json.dumps({"rule_version": RULE_VERSION,
        "note": "Confidence labels are heuristic rule strength, not calibrated probabilities.",
        "faculty": review}, indent=2, ensure_ascii=False))
    print(f"{RULE_VERSION}: classified {counts['faculty']} faculty")
    print(f"  with >=1 priority: {counts['with_priority']}, keywords: {counts['with_keyword']}, "
          f"geography: {counts['with_geography']}, no usable profile text: {counts['no_source_text']}")
    for k in sorted(k for k in counts if k.startswith("priority:")):
        print(f"  {k.split(':', 1)[1]}: {counts[k]}")
    print(f"Review file: {REVIEW_FILE}")


if __name__ == "__main__":
    main()
