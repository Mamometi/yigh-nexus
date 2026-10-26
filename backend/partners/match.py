"""Match external partner organizations to an opportunity and each proposed Yale team.

Ranking favours (1) presence in the countries the opportunity or team works in, (2) documented
expertise overlapping the opportunity, (3) a publicly documented Yale relationship — especially with
someone on the team, and (4) locally based institutions in low/middle-income settings (locally led,
reciprocal partnerships, per YIGH's strategic plan). Every recommendation carries evidence URLs; a
relationship is "documented" only with a YaleLink (which itself requires public evidence).
Nothing states or implies that an organization has agreed to collaborate.
"""
from __future__ import annotations

import json
from datetime import timedelta

from sqlalchemy import select

from backend.app.classification.rules import HIGH_INCOME
from backend.app.matching.config import broader

from .models import Org
from .store import now, upsert_org, add_evidence

STALE_AFTER = timedelta(days=180)
REQUIRES_LOCAL = ("lead_must_be_lmic", "foreign_only")
WEIGHTS = {"geography": 0.4, "expertise": 0.25, "yale": 0.2, "local": 0.15}
NOT_LMIC = HIGH_INCOME | {"United States"}


def _geo_score(org_country: str | None, targets: set[str]) -> tuple[float, str | None]:
    if not org_country or not targets:
        return 0.0, None
    if org_country in targets:
        return 1.0, org_country
    if "LMICs" in targets and org_country not in NOT_LMIC:
        return 0.75, "LMICs"
    for t in targets:
        if t in broader(org_country) or org_country in broader(t) or (broader(t) & broader(org_country) - {"Africa", "Asia"}):
            return 0.5, t
    return 0.0, None


def partner_card(o: Org, *, opp_topics: set[str], targets: set[str], team_ids: set[int], team_facets_missing: list[str],
                 requires_local: bool, require_overlap: bool = False) -> dict | None:
    geo, matched_place = _geo_score(o.country, targets)
    expertise = json.loads(o.expertise or "{}")
    ev_by_id = {e.id: e for e in o.evidence}
    overlap = sorted(t for t in expertise if t in opp_topics)
    links = o.yale_links
    team_links = [l for l in links if l.faculty_id in team_ids]
    yale = 1.0 if team_links else (0.6 if links else 0.0)
    local = 1.0 if o.country and o.country not in NOT_LMIC and geo > 0 else 0.0
    score = WEIGHTS["geography"] * geo + WEIGHTS["expertise"] * min(1.0, 0.5 * len(overlap)) + WEIGHTS["yale"] * yale + WEIGHTS["local"] * local
    if geo == 0 and not overlap:
        return None                       # neither the right place nor relevant documented expertise
    if require_overlap and not overlap:
        return None                       # place came only from the team's past work: expertise must match the opportunity
    if not o.evidence:
        return None                       # unsupported: no source we can show
    stale = o.last_verified_at is None or now() - o.last_verified_at > STALE_AFTER
    verify = []
    if not overlap:
        verify.append("We couldn't find their work in this area in our sources; check what they do before reaching out.")
    if not links:
        verify.append("We found no existing connection with Yale; any collaboration would be new.")
    if stale:
        verify.append(f"Record last verified {o.last_verified_at.date() if o.last_verified_at else 'never'}; check their website for current details.")
    verify.append("We don't know who to contact, their current capacity, or whether they'd want to partner; ask them directly.")
    complements = []
    if geo == 1.0:
        complements.append(f"Based in {o.country}, where this work would happen")
    elif matched_place == "LMICs":
        complements.append(f"Based in {o.country}, a low- or middle-income country, which this call focuses on")
    elif geo == 0.5:
        complements.append(f"Based nearby in {o.country}")
    complements += [f"Works on {t}" for t in overlap if any(t in f for f in team_facets_missing)] or \
                   [f"Works on {t}" for t in overlap[:3]]
    relationship = {
        "status": "documented" if links else "proposed",
        "summary": ("Already connected to Yale: " + "; ".join(sorted({(l.detail or l.link_type) + (f" — {l.faculty_name}" if l.faculty_name else "") for l in links})))
                   if links else "A new suggestion: we found no existing connection with Yale.",
        "with_team_members": sorted({l.faculty_name for l in team_links if l.faculty_name}),
        "evidence": list({(l.evidence.url, l.evidence.quote): {"url": l.evidence.url, "quote": l.evidence.quote} for l in links}.values()),
    }
    return {
        "organization_id": o.id, "name": o.name, "type": o.org_type, "country": o.country, "website": o.website, "ror_id": o.ror_id,
        "score": round(score, 3),
        "why_relevant": "; ".join(filter(None, [
            f"based in {o.country}" + (", where this call focuses" if geo == 1.0 else ", in the same region" if geo == 0.5 else ""),
            f"works on {', '.join(overlap)}" if overlap else None,
            "already connected to Yale" if links else None])),
        "capabilities": [{"area": t, "evidence": ev_by_id[expertise[t]].quote[:300] if expertise[t] in ev_by_id else None,
                          "url": ev_by_id[expertise[t]].url if expertise[t] in ev_by_id else None} for t in overlap],
        "complements_team": complements,
        "geographic_requirement": ("Could help meet the requirement for a locally based applicant/partner"
                                   if requires_local and local and geo == 1.0 else
                                   "Not in a required country" if requires_local and geo < 1.0 else
                                   "No locally-based requirement identified in the opportunity text"),
        "relationship": relationship,
        "needs_verification": verify,
        "last_verified": o.last_verified_at, "stale": stale,
        "evidence_urls": sorted({e.url for e in o.evidence} | ({o.website} if o.website else set())),
        "note": "Suggested partner only. Nothing here indicates that the organization has been contacted or has agreed to collaborate.",
    }


def discover_proposed(db, ror, country: str, country_code: str | None, topics: set[str], limit: int = 3) -> list[Org]:
    """When no documented partner exists in a needed country, look up candidate institutions in ROR
    (official registry). They are stored as 'proposed' with registry evidence only."""
    out = []
    queries = ["ministry of health"] + [t.split(" &")[0].split(" (")[0] for t in sorted(topics)[:2]] + ["university"]
    for q in queries:
        for rec in ror.search(q, country_code=country_code, rows=3):
            if rec["country"] != country:
                continue
            o = upsert_org(db, name=rec["name"], country=rec["country"], origin="ror_search", ror=rec)
            add_evidence(db, o, "registry", rec["id"], f"Research Organization Registry record ({', '.join(rec['types'])}), {rec['country']}.")
            out.append(o)
        if len(out) >= limit:
            break
    db.flush()
    return out[:limit]


def partners_for_recommendation(db, doc: dict, dossiers: dict, opp_profile, ror=None, per_team: int = 5) -> dict:
    """Attach up to `per_team` external partners to each team in a Nexus recommendation document."""
    from backend.radar.collectors.grants_gov import GLOBAL_TERMS
    if not opp_profile.places and not GLOBAL_TERMS.search(opp_profile.text or ""):
        gap = "The opportunity names no countries and has no international dimension, so no external partners are suggested."
        return {"teams": [{"team": t["name"], "target_countries": [], "partners": [], "collaboration_gaps": [gap]} for t in doc.get("teams", [])],
                "requires_local_partner": False, "collaboration_gaps": [gap] if doc.get("teams") else [],
                "method": "Not applicable: domestic opportunity."}
    concerns = {c.get("code") for c in doc.get("eligibility_concerns", [])}
    requires_local = bool(concerns & set(REQUIRES_LOCAL))
    opp_places = set(opp_profile.places)
    orgs = db.scalars(select(Org)).all()
    teams_out, gaps = [], []
    for t in doc.get("teams", []):
        ids = {m["faculty_id"] for m in t["members"]}
        team_places = {p for i in ids if i in dossiers for p in dossiers[i].places if p not in NOT_LMIC}
        targets = opp_places or team_places
        cards = [c for o in orgs if (c := partner_card(o, opp_topics=opp_profile.topics, targets=targets, team_ids=ids,
                                                      team_facets_missing=t.get("missing_expertise", []), requires_local=requires_local,
                                                      require_overlap=not opp_places))]
        countries_covered = {c["country"] for c in cards if c["score"] > 0 and c["country"] in targets}
        if ror is not None:
            for country in sorted(targets - countries_covered)[:2]:
                code = next((o.country_code for o in orgs if o.country == country and o.country_code), None)
                for o in discover_proposed(db, ror, country, code, opp_profile.topics):
                    c = partner_card(o, opp_topics=opp_profile.topics, targets=targets, team_ids=ids,
                                     team_facets_missing=t.get("missing_expertise", []), requires_local=requires_local)
                    if c and c["organization_id"] not in {x["organization_id"] for x in cards}:
                        cards.append(c)
        cards.sort(key=lambda c: (-c["score"], c["relationship"]["status"] != "documented"))
        picked, types = [], []
        for c in cards:  # prefer a mix of institution types
            if len(picked) >= per_team:
                break
            if types.count(c["type"]) >= 2 and len(cards) > per_team:
                continue
            picked.append(c)
            types.append(c["type"])
        team_gaps = []
        if requires_local and not any(c["geographic_requirement"].startswith("Could help") for c in picked):
            team_gaps.append("This call needs a local partner, and we didn't find one in the required countries.")
        covered_targets = targets & {c["country"] for c in picked}
        if "LMICs" in targets and any(c["country"] not in NOT_LMIC for c in picked):
            covered_targets.add("LMICs")
        if targets and not covered_targets:
            team_gaps.append(f"We didn't find a partner in {', '.join(sorted(targets))}.")
        if not targets:
            team_gaps.append("This call doesn't name specific countries, so partners weren't matched by location.")
        teams_out.append({"team": t["name"], "target_countries": sorted(targets), "partners": picked, "collaboration_gaps": team_gaps})
        gaps += team_gaps
    return {"teams": teams_out, "requires_local_partner": requires_local, "collaboration_gaps": sorted(set(gaps)),
            "method": "Partners come from YIGH training sites and organizations named on Yale faculty profiles. "
                      "Ones marked 'new suggestion' come from a global registry of research institutions and have no known Yale connection."}
