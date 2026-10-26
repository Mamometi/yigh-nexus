"""Global Health Radar discovery pipeline.

weekly  : collect from every enabled source, merge/dedupe, upsert, record changes and verification,
          recompute status, classify by YIGH priority, write a run summary.
deadlines: no network. Close opportunities whose deadline has passed and report what closes soon.

Idempotent: records are keyed by a stable uid and updated in place; a run that sees the same data
creates sightings and verification rows (history) but no new opportunities and no change rows.
One source failing never stops the run.
"""
from __future__ import annotations

import difflib
import json
import logging
import re
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.classification.rules import RULE_VERSION, classify_priorities

from .candidate import MATERIAL_FIELDS, Candidate
from .collectors import grand_challenges, grants_gov, html_listing, nih_rss, page_monitor
from .http import BlockedByRobots, SourceUnavailable, now
from .models import (Change, DiscoveryRun, FundingSource, Opportunity, OpportunityPriority, Organization, PageSnapshot,
                     Sighting, SourceFetch, Verification)

log = logging.getLogger("radar")
ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "config" / "radar_sources.json"
COLLECTORS = {"grants_gov": grants_gov, "nih_rss": nih_rss, "html_listing": html_listing, "grand_challenges": grand_challenges}
METHOD_RANK = {"api": 0, "rss": 1, "html_listing": 2}  # which source wins when the same opportunity appears twice
CLOSING_SOON_DAYS = (7, 14, 30)


def load_registry(path: Path = REGISTRY) -> dict:
    return json.loads(Path(path).read_text())


def classify(text: str) -> dict:
    """YIGH priority classification of opportunity text (same transparent rules as faculty)."""
    return classify_priorities({"opportunity": text})


# ------------------------------------------------------------------ seeding

def seed(db: Session, registry: dict) -> dict[str, FundingSource]:
    curated = ROOT / "data" / "opportunities.json"
    if curated.exists():
        for f in json.loads(curated.read_text()).get("funders", []):
            org = db.scalar(select(Organization).filter_by(slug=f["id"])) or Organization(slug=f["id"], origin="curated")
            org.name, org.org_type, org.website = f["name"], f.get("type"), f.get("website")
            db.add(org)
    db.flush()
    sources = {}
    for s in registry["sources"]:
        src = db.scalar(select(FundingSource).filter_by(slug=s["id"])) or FundingSource(slug=s["id"])
        src.name, src.official_url, src.access_method = s["name"], s["official_url"], s["access_method"]
        src.collector, src.endpoint, src.enabled, src.notes = s.get("collector"), s.get("endpoint"), s.get("enabled", True), s.get("notes")
        if s.get("funder"):
            src.organization = db.scalar(select(Organization).filter_by(slug=s["funder"]))
        db.add(src)
        sources[s["id"]] = src
    db.flush()
    return sources


def organization_for(db: Session, slug: str | None, name: str | None) -> Organization | None:
    if not slug:
        return None
    org = db.scalar(select(Organization).filter_by(slug=slug))
    if org is None:
        org = Organization(slug=slug, name=name or slug, origin="discovered")
        db.add(org)
        db.flush()
    return org


# ------------------------------------------------------------------ merge / dedupe

def _norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", (t or "").lower()).strip()


def merge_candidates(cands: list[Candidate], method_of: dict[str, str]) -> dict[str, list[Candidate]]:
    """Group candidates that describe the same opportunity. Exact: same uid (opportunity number or URL).
    Near-duplicate: same funder, no number on one side, title similarity >= 0.92 and same/unknown deadline."""
    groups: dict[str, list[Candidate]] = {}
    for c in sorted(cands, key=lambda c: METHOD_RANK.get(method_of.get(c.source_slug, ""), 9)):
        uid = c.uid
        if uid not in groups:
            for other_uid, members in groups.items():
                o = members[0]
                if o.funder_slug == c.funder_slug and (not c.opportunity_number or not o.opportunity_number) and \
                        (o.deadline is None or c.deadline is None or o.deadline == c.deadline) and \
                        difflib.SequenceMatcher(None, _norm_title(o.title), _norm_title(c.title)).ratio() >= 0.92:
                    uid = other_uid
                    break
        groups.setdefault(uid, []).append(c)
    return groups


def find_existing(db: Session, uid: str, c: Candidate) -> Opportunity | None:
    opp = db.scalar(select(Opportunity).filter_by(uid=uid))
    if opp:
        return opp
    # near-duplicate of a stored record (e.g. same call announced again under a new URL)
    org_slug = c.funder_slug
    for o in db.scalars(select(Opportunity).where(Opportunity.status != "closed")):
        if o.organization and o.organization.slug == org_slug and \
                difflib.SequenceMatcher(None, _norm_title(o.title), _norm_title(c.title)).ratio() >= 0.92 and \
                (o.deadline is None or c.deadline is None or o.deadline == c.deadline):
            return o
    return None


# ------------------------------------------------------------------ upsert

def _fmt(v):
    return v.isoformat() if isinstance(v, date) else (None if v is None else str(v))


def apply_status(opp: Opportunity, today: date, run_id: int | None) -> None:
    """Status only changes on evidence: the official record's status, or a deadline that has passed."""
    if opp.status in ("open", "forecasted") and opp.deadline and opp.deadline < today:
        _log_change(opp, run_id, "status", "status", opp.status, "closed")
        opp.status, opp.status_reason = "closed", f"Deadline {opp.deadline.isoformat()} has passed"


def _log_change(opp, run_id, kind, field, old, new):
    opp.changes.append(Change(run_id=run_id, change_type=kind, field=field, old_value=_fmt(old), new_value=_fmt(new),
                              detected_at=now()))


def upsert(db: Session, uid: str, group: list[Candidate], sources: dict, run: DiscoveryRun, today: date) -> tuple[str, Opportunity]:
    c = group[0]  # best source first
    opp = find_existing(db, uid, c)
    org = organization_for(db, c.funder_slug, c.funder_name)
    # Effective status before comparing: a source may still say "open" after the deadline has passed.
    for g in group:
        if g.status in ("open", "forecasted") and g.deadline and g.deadline < today:
            g.status = "closed"
    reasons = list(dict.fromkeys(r for g in group for r in g.review_reasons))
    if len(group) > 1:
        reasons = [r for r in reasons if not r.startswith("Listed in the NIH Guide but not yet")] if any(
            g.verification_method == "official_api" for g in group) else reasons
    status = c.status if c.status else None
    outcome = "unchanged"

    if opp is None:
        opp = Opportunity(uid=uid, source=sources[c.source_slug], first_seen_at=c.retrieved_at, first_seen_run_id=run.id,
                          status=status or "unknown", content_hash="")
        db.add(opp)
        for f in MATERIAL_FIELDS:
            if f != "status":
                setattr(opp, f, getattr(c, f))
        _log_change(opp, run.id, "created", None, None, c.title)
        outcome = "new"
    else:
        for f in MATERIAL_FIELDS:
            new = status if f == "status" else getattr(c, f)
            if f == "status" and new is None:
                continue  # source didn't state a status: keep what we know
            old = getattr(opp, f)
            if _fmt(old) != _fmt(new):
                _log_change(opp, run.id, "status" if f == "status" else "updated", f, old, new)
                setattr(opp, f, new)
                outcome = "updated"
        if outcome == "updated":
            opp.last_changed_at, opp.last_changed_run_id = c.retrieved_at, run.id

    if status:
        opp.status = status
        if status != "closed":
            opp.status_reason = "As listed by the funder"
        elif c.deadline and c.deadline < today:
            opp.status_reason = f"Deadline {c.deadline.isoformat()} has passed"
        else:
            opp.status_reason = "The funder lists it as closed"
    opp.uid = opp.uid or uid
    opp.opportunity_number = c.opportunity_number or opp.opportunity_number
    opp.organization = org or opp.organization
    opp.description, opp.currency, opp.posted_date = c.description, c.currency, c.posted_date or opp.posted_date
    opp.official_url = c.official_url
    opp.last_seen_at = max(g.retrieved_at for g in group)
    opp.suspicious_content = any(g.suspicious for g in group)
    opp.content_hash = c.content_hash()

    for g in {g.source_slug: g for g in reversed(group)}.values():  # one sighting per source per run
        if any(s.run_id == run.id and s.source_id == sources[g.source_slug].id for s in opp.sightings):
            continue
        opp.sightings.append(Sighting(run_id=run.id, source=sources[g.source_slug], source_url=g.official_url,
                                      external_ref=g.external_ref, retrieved_at=g.retrieved_at))
    best = min(group, key=lambda g: {"verified": 0, "partially_verified": 1, "mismatch": 2, "unverified": 3}.get(g.verification_status, 4))
    if best.verification_method:
        opp.verifications.append(Verification(run_id=run.id, checked_at=best.retrieved_at, url=best.verification_url or best.official_url,
                                              method=best.verification_method, status=best.verification_status,
                                              details=json.dumps(best.verification_details, default=str)))
        opp.verification_status, opp.last_verified_at = best.verification_status, best.retrieved_at

    apply_status(opp, today, run.id)
    if opp.status == "unknown" and "Status could not be determined from the page" not in reasons:
        reasons.append("Status not stated by the source")
    if opp.suspicious_content and not any("instruction-like" in r for r in reasons):
        reasons.append("Source text contained instruction-like content")
    opp.review_reasons = json.dumps(reasons)
    opp.needs_review = bool(reasons) or opp.verification_status in ("unverified", "mismatch")

    # Strategic-priority classification (replace rule-based rows each run)
    opp.priorities.clear()
    db.flush()
    for slug, res in classify(f"{opp.title}. {opp.description or ''}").items():
        opp.priorities.append(OpportunityPriority(priority=slug, confidence=res.confidence, confidence_label=res.confidence_label,
                                                  rule_version=RULE_VERSION, explanation=res.explanation,
                                                  evidence=json.dumps([e.as_dict() for e in res.evidence])))
    return outcome, opp


# ------------------------------------------------------------------ runs

def run_weekly(db: Session, fetcher, registry: dict, today: date | None = None, only: list[str] | None = None,
               max_details: int = 150) -> dict:
    today = today or date.today()
    sources = seed(db, registry)
    cfgs = {s["id"]: s for s in registry["sources"]}
    run = DiscoveryRun(mode="weekly", started_at=now())
    db.add(run)
    db.flush()
    queries = list(dict.fromkeys(registry.get("baseline_queries", []) + [q for qs in registry["priority_queries"].values() for q in qs]))
    ctx = {"queries": queries, "classify": classify, "now": now, "sources": cfgs, "max_details": max_details}

    per_source, candidates, ok_sources, snapshots_changed = {}, [], set(), []
    for slug, cfg in cfgs.items():
        if only and slug not in only:
            continue
        src = sources[slug]
        if not cfg.get("enabled", True) or not cfg.get("collector"):
            per_source[slug] = {"status": "skipped", "reason": cfg.get("access_method")}
            continue
        fetch = SourceFetch(run_id=run.id, source=src, status="running", started_at=now())
        db.add(fetch)
        try:
            if cfg["collector"] == "page_monitor":
                snap = page_monitor.snapshot(fetcher, cfg)
                # compare with the last snapshot of the SAME page (a registry URL change is not a content change)
                last = db.scalar(select(PageSnapshot).filter_by(source_id=src.id, url=snap["url"]).order_by(PageSnapshot.id.desc()))
                changed = last is not None and last.content_hash != snap["hash"]
                if last is None or changed:
                    db.add(PageSnapshot(source_id=src.id, url=snap["url"], content_hash=snap["hash"], retrieved_at=snap["retrieved_at"],
                                        changed=changed, excerpt=snap["excerpt"]))
                if changed:
                    snapshots_changed.append(slug)
                fetch.items_found = 0
                per_source[slug] = {"status": "ok", "page_changed": changed, "first_snapshot": last is None}
            else:
                found = COLLECTORS[cfg["collector"]].collect(fetcher, cfg, ctx)
                candidates += found
                fetch.items_found = len(found)
                per_source[slug] = {"status": "ok", "items": len(found)}
            fetch.status, src.last_status, src.last_success_at = "ok", "ok", now()
            ok_sources.add(slug)
        except BlockedByRobots as e:
            fetch.status, fetch.error, src.last_status = "blocked", str(e), "blocked"
            per_source[slug] = {"status": "blocked", "error": str(e)}
        except Exception as e:  # noqa: BLE001 — one source must not stop the run
            fetch.status, fetch.error, src.last_status = "failed", f"{type(e).__name__}: {e}", "failed"
            per_source[slug] = {"status": "failed", "error": f"{type(e).__name__}: {e}"}
            log.warning("source %s failed: %s", slug, traceback.format_exc(limit=2))
        fetch.finished_at = now()
        db.flush()

    method_of = {s: c.get("access_method") for s, c in cfgs.items()}
    groups = merge_candidates(candidates, method_of)
    outcomes = {"new": [], "updated": [], "unchanged": []}
    seen_ids = set()
    for uid, group in groups.items():
        outcome, opp = upsert(db, uid, group, sources, run, today)
        db.flush()
        seen_ids.add(opp.id)
        outcomes[outcome].append(opp.id)
    db.flush()

    # Records not seen this run: confirm with the source instead of assuming anything.
    rechecked, unlisted = 0, []
    for opp in db.scalars(select(Opportunity).where(Opportunity.status.in_(["open", "forecasted", "unknown"]))):
        if opp.id in seen_ids or opp.source.slug not in ok_sources:
            continue
        if opp.source.slug in ("grants-gov", "nih-guide-rss") and "grants-gov" in ok_sources:
            ref = next((s.external_ref for s in reversed(opp.sightings) if s.external_ref and s.external_ref.isdigit()), None)
            if ref:
                try:
                    c = grants_gov.recheck(fetcher, cfgs["grants-gov"], ref, ctx)
                    rechecked += 1
                except SourceUnavailable:
                    continue
                if c is None:
                    _log_change(opp, run.id, "status", "status", opp.status, "closed")
                    opp.status, opp.status_reason = "closed", "No longer available from Grants.gov"
                else:
                    if upsert(db, c.uid, [c], sources, run, today)[0] == "updated":
                        outcomes["updated"].append(opp.id)
                continue
        if opp.source.access_method == "html_listing":
            reasons = json.loads(opp.review_reasons or "[]")
            msg = "No longer listed on the source page (may have closed): please confirm"
            if msg not in reasons:
                opp.review_reasons = json.dumps(reasons + [msg])
                opp.needs_review = True
                unlisted.append(opp.id)
        apply_status(opp, today, run.id)

    for opp in db.scalars(select(Opportunity).where(Opportunity.status.in_(["open", "forecasted"]))):
        apply_status(opp, today, run.id)

    failed = [s for s, v in per_source.items() if v["status"] in ("failed", "blocked")]
    run.status = "success" if not failed else ("partial" if ok_sources else "failed")
    run.finished_at = now()
    summary = _summary(db, run, per_source, outcomes, today, extra={"rechecked_unlisted": rechecked, "now_unlisted": unlisted,
                                                                     "monitored_pages_changed": snapshots_changed,
                                                                     "scope": "partial" if only else "all",
                                                                     "sources_attempted": sum(1 for v in per_source.values() if v["status"] != "skipped")})
    run.summary = json.dumps(summary, default=str)
    db.commit()
    return summary


def run_deadlines(db: Session, today: date | None = None) -> dict:
    """Daily lightweight check: no network calls."""
    today = today or date.today()
    run = DiscoveryRun(mode="deadlines", started_at=now())
    db.add(run)
    db.flush()
    closed = []
    for opp in db.scalars(select(Opportunity).where(Opportunity.status.in_(["open", "forecasted"]))):
        before = opp.status
        apply_status(opp, today, run.id)
        if before != opp.status:
            closed.append({"id": opp.id, "title": opp.title, "deadline": opp.deadline})
    run.status, run.finished_at = "success", now()
    summary = {"run_id": run.id, "mode": "deadlines", "date": today, "closed_today": closed, "closing_soon": closing_soon(db, today)}
    run.summary = json.dumps(summary, default=str)
    db.commit()
    return summary


def closing_soon(db: Session, today: date, days: int = max(CLOSING_SOON_DAYS)) -> dict:
    rows = db.scalars(select(Opportunity).where(Opportunity.status.in_(["open", "forecasted"]),
                                                Opportunity.deadline >= today,
                                                Opportunity.deadline <= today + timedelta(days=days)).order_by(Opportunity.deadline))
    out = {f"within_{d}_days": [] for d in CLOSING_SOON_DAYS}
    for o in rows:
        left = (o.deadline - today).days
        for d in CLOSING_SOON_DAYS:
            if left <= d:
                out[f"within_{d}_days"].append({"id": o.id, "title": o.title, "deadline": o.deadline, "days_left": left})
                break
    return out


def _summary(db, run, per_source, outcomes, today, extra) -> dict:
    total = db.query(Opportunity).count()
    status_counts = {s: db.query(Opportunity).filter_by(status=s).count() for s in ("open", "forecasted", "closed", "unknown")}
    return {
        "run_id": run.id, "mode": run.mode, "status": run.status, "started_at": run.started_at, "finished_at": run.finished_at,
        "sources": per_source,
        "new": len(outcomes["new"]), "updated": len(set(outcomes["updated"])), "unchanged": len(outcomes["unchanged"]),
        "total_opportunities": total, "by_status": status_counts,
        "needs_review": db.query(Opportunity).filter_by(needs_review=True).count(),
        "closing_soon": {k: len(v) for k, v in closing_soon(db, today).items()},
        **extra,
    }


def summary_markdown(s: dict) -> str:
    lines = [f"## Global Health Radar — {s['mode']} run #{s['run_id']} ({s.get('status', 'success')})", ""]
    if s["mode"] == "weekly":
        lines += [f"- **New:** {s['new']}  **Updated:** {s['updated']}  **Unchanged:** {s['unchanged']}",
                  f"- **Total:** {s['total_opportunities']} ({', '.join(f'{k} {v}' for k, v in s['by_status'].items())})",
                  f"- **Needs review:** {s['needs_review']}",
                  f"- **Closing soon:** " + ", ".join(f"{k.replace('_', ' ')}: {v}" for k, v in s["closing_soon"].items()),
                  f"- **Monitored pages changed:** {', '.join(s['monitored_pages_changed']) or 'none'}", "",
                  "| Source | Status | Detail |", "|---|---|---|"]
        for k, v in s["sources"].items():
            lines.append(f"| {k} | {v['status']} | {v.get('items', v.get('error', v.get('reason', '')))} |")
    else:
        lines += [f"- Closed today (deadline passed): {len(s['closed_today'])}"] + \
                 [f"- {k.replace('_', ' ')}: {len(v)}" for k, v in s["closing_soon"].items()]
    return "\n".join(lines)
