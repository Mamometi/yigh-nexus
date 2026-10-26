"""Grants.gov official REST API (search2 + fetchOpportunity). No key required."""
from __future__ import annotations

import re

from ..candidate import Candidate
from ..http import SourceUnavailable
from ..extract import money, parse_date
from ..sanitize import html_to_text, strip_injections

GLOBAL_TERMS = re.compile(r"global health|international|low- and middle-income|low and middle income|\bLMICs?\b|"
                          r"developing countries|foreign (?:institutions|organizations|entities)|non-U\.?S\.?|worldwide|global", re.I)
DETAIL_URL = "https://www.grants.gov/search-results-detail/{id}"


def search(fetcher, cfg, keyword: str, rows: int = 25) -> list[dict]:
    r = fetcher.post_json(cfg["endpoint"], {"keyword": keyword, "oppStatuses": "forecasted|posted", "rows": rows},
                          min_interval=cfg.get("min_interval_seconds", 1.0))
    data = r.json()
    if data.get("errorcode", 0) != 0:
        raise RuntimeError(f"Grants.gov error: {data.get('msg')}")
    return data["data"].get("oppHits", [])


def search_number(fetcher, cfg, number: str) -> list[dict]:
    r = fetcher.post_json(cfg["endpoint"], {"oppNum": number, "oppStatuses": "forecasted|posted|closed|archived", "rows": 5},
                          min_interval=cfg.get("min_interval_seconds", 1.0))
    return r.json()["data"].get("oppHits", [])


def fetch_detail(fetcher, cfg, opp_id) -> dict:
    r = fetcher.post_json(cfg["detail_endpoint"], {"opportunityId": int(opp_id)}, min_interval=cfg.get("min_interval_seconds", 1.0))
    data = r.json()
    if data.get("errorcode", 0) != 0 or not data.get("data"):
        raise RuntimeError(f"fetchOpportunity {opp_id}: {data.get('msg')}")
    return data["data"]


def build(hit: dict, detail: dict, source_slug: str, retrieved_at) -> Candidate:
    """Map the official API record to a Candidate. Only values present in the record are used."""
    syn = detail.get("synopsis") or {}
    fc = detail.get("forecast") or {}
    is_forecast = bool(fc) and not syn
    rec = fc if is_forecast else syn
    agency = (detail.get("agencyDetails") or {}).get("agencyName") or hit.get("agency") or syn.get("agencyName")
    agency_code = hit.get("agencyCode") or detail.get("owningAgencyCode") or "unknown"

    raw_desc = html_to_text(rec.get("synopsisDesc") or rec.get("forecastDesc") or "")
    desc, removed = strip_injections(raw_desc)

    if is_forecast:
        deadline = parse_date(fc.get("estApplicationResponseDate"))
        deadline_text = f"Estimated: {fc.get('estApplicationResponseDateStr') or fc.get('estApplicationResponseDate')}" if deadline else None
    else:
        deadline = parse_date(syn.get("responseDate"))
        deadline_text = syn.get("responseDateStr") or syn.get("responseDate")
        if syn.get("responseDateDesc"):
            deadline_text = f"{deadline_text or ''} {html_to_text(syn['responseDateDesc'])}".strip()

    # Some agencies enter a far-future placeholder (e.g. Jan 1, 2099) meaning "no fixed deadline".
    if deadline and deadline.year >= 2090:
        deadline_text = f"No fixed deadline (Grants.gov lists a placeholder date of {deadline.strftime('%b %-d, %Y')})"
        deadline = None

    floor, ceiling = money(rec.get("awardFloor")), money(rec.get("awardCeiling"))
    award_bits = []
    if floor:
        award_bits.append(f"Award floor: {rec.get('awardFloorFormatted') or f'${floor:,.0f}'}")
    if ceiling:
        award_bits.append(f"Award ceiling: {rec.get('awardCeilingFormatted') or f'${ceiling:,.0f}'}")
    total = money(rec.get("estimatedFunding"))
    if total:
        award_bits.append(f"Estimated total program funding: ${total:,.0f}")

    # Grants.gov returns applicant types in arbitrary order; sort so re-ordering is never reported as a change.
    types = sorted(t.get("description", "") for t in (rec.get("applicantTypes") or []) if isinstance(t, dict))
    elig_desc = html_to_text(rec.get("applicantEligibilityDesc") or "")
    eligibility = "; ".join(filter(None, [", ".join(types) if types else None, elig_desc])) or None
    geo = None
    if re.search(r"foreign|non-domestic|non-U\.?S", " ".join(types) + " " + elig_desc, re.I):
        geo = "Foreign (non-US) organizations mentioned in eligibility: " + (elig_desc[:300] or ", ".join(types))

    status = "forecasted" if is_forecast or hit.get("oppStatus") == "forecasted" else \
        {"posted": "open", "closed": "closed", "archived": "closed"}.get(hit.get("oppStatus"), None)

    c = Candidate(
        source_slug=source_slug, title=detail.get("opportunityTitle") or hit.get("title"),
        official_url=DETAIL_URL.format(id=detail.get("id") or hit.get("id")), retrieved_at=retrieved_at,
        external_ref=str(detail.get("id") or hit.get("id")), opportunity_number=detail.get("opportunityNumber") or hit.get("number"),
        funder_slug=f"agency-{agency_code.lower()}", funder_name=agency, description=desc[:5000] or None,
        deadline=deadline, deadline_text=deadline_text, award_floor=floor, award_ceiling=ceiling,
        award_text="; ".join(award_bits) or None, currency="USD" if award_bits else None,
        eligibility=eligibility, geographic_restrictions=geo,
        application_url=DETAIL_URL.format(id=detail.get("id") or hit.get("id")),
        posted_date=parse_date(rec.get("postingDate")), status=status,
        verification_method="official_api", verification_url="https://api.grants.gov/v1/api/fetchOpportunity",
    )
    # Verification: the detail record IS the official source; cross-check the search listing against it.
    details = {}
    hit_close = parse_date(hit.get("closeDate"))
    if hit_close and hit_close.year >= 2090:
        hit_close = None
    details["deadline"] = {"verified": (deadline is not None or (deadline_text or "").startswith("No fixed deadline"))
                                       and (hit_close is None or hit_close == deadline),
                           "evidence": deadline_text, "listing_value": hit.get("closeDate")}
    details["award"] = {"verified": bool(award_bits), "evidence": c.award_text}
    details["eligibility"] = {"verified": bool(eligibility), "evidence": (eligibility or "")[:200]}
    c.verification_details = details
    if hit_close and deadline and hit_close != deadline:
        c.verification_status = "mismatch"
        c.review_reasons.append(f"Search listing close date {hit.get('closeDate')} doesn't match the full announcement ({deadline_text})")
    elif all(v["verified"] for v in details.values()):
        c.verification_status = "verified"
    else:
        c.verification_status = "partially_verified"
    if not deadline and not (deadline_text or "").startswith("No fixed deadline"):
        c.review_reasons.append("The funder didn't list an application deadline")
    if not award_bits:
        c.review_reasons.append("The funder didn't state an award amount")
    if not eligibility or re.fullmatch(r"(?i)\s*(?:please )?see .{0,80}", elig_desc or "") and not types:
        c.review_reasons.append("Eligibility missing or only refers to another document")
    if is_forecast:
        c.review_reasons.append("Forecast only: dates are estimates and may change")
    if removed:
        c.suspicious = True
        c.review_reasons.append(f"Removed {len(removed)} instruction-like sentence(s) from the source text")
    return c


def is_relevant(c: Candidate, classify) -> bool:
    text = f"{c.title}. {c.description or ''}"
    return bool(classify(text)) or bool(GLOBAL_TERMS.search(text))


def collect(fetcher, cfg, ctx) -> list[Candidate]:
    queries = ctx["queries"]
    hits: dict[str, dict] = {}
    for q in queries:
        for h in search(fetcher, cfg, q, rows=ctx.get("rows", 25)):
            hits.setdefault(str(h["id"]), h)
    out = []
    for i, (hid, hit) in enumerate(hits.items()):
        if i >= ctx.get("max_details", 150):
            break
        detail = fetch_detail(fetcher, cfg, hid)
        c = build(hit, detail, cfg["id"], ctx["now"]())
        if is_relevant(c, ctx["classify"]):
            out.append(c)
    return out


def recheck(fetcher, cfg, external_ref: str, ctx) -> Candidate | None:
    """Re-read one opportunity that didn't appear in this week's searches (search is keyword-based,
    so absence doesn't mean it closed). Returns None if Grants.gov no longer has it."""
    try:
        detail = fetch_detail(fetcher, cfg, external_ref)
    except RuntimeError:
        return None  # API answered: no such opportunity
    except SourceUnavailable as e:
        if e.status in (404, 410):
            return None  # official source says it's gone
        raise        # temporary failure: don't conclude anything
    number = detail.get("opportunityNumber")
    hits = search_number(fetcher, cfg, number) if number else []
    hit = next((h for h in hits if str(h["id"]) == str(external_ref)), {"id": external_ref, "oppStatus": None})
    return build(hit, detail, cfg["id"], ctx["now"]())
