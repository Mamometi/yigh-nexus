"""Global Health Radar pipeline tests (saved fixtures, mocked sources, temporary database)."""
import json
from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from backend.radar.db import make_engine
from backend.radar.http import FixtureFetcher
from backend.radar.models import Change, Opportunity, PageSnapshot, Sighting, SourceFetch, Verification
from backend.radar.pipeline import run_deadlines, run_weekly

from . import fixtures as fx

TODAY = date(2026, 10, 26)


@pytest.fixture
def db(tmp_path):
    engine = make_engine(tmp_path / "radar.db")
    s = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    yield s
    s.close()


def run(db, tmp_path, name="week1", today=TODAY, **kw):
    d = fx.write(tmp_path / name, **kw)
    return run_weekly(db, FixtureFetcher(d), fx.REGISTRY, today=today)


def by_number(db, n):
    return db.scalar(select(Opportunity).filter_by(opportunity_number=n))


def by_title(db, t):
    return db.scalars(select(Opportunity).filter(Opportunity.title == t)).all()


def reasons(o):
    return json.loads(o.review_reasons or "[]")


# ---------------------------------------------------------------- first-time discovery
def test_first_time_discovery(db, tmp_path):
    s = run(db, tmp_path)
    assert s["status"] == "success"
    a = by_number(db, "RFA-TW-27-001")
    assert a.status == "open" and a.deadline == date(2027, 3, 1)
    assert a.award_ceiling == 500000 and "500,000" in a.award_text
    assert "Estimated total" not in (a.award_text or "")          # 2147483647 placeholder is not reported as an amount
    assert "Foreign" in a.eligibility and a.geographic_restrictions
    assert a.verification_status == "verified" and a.verifications[-1].method == "official_api"
    assert {p.priority for p in a.priorities} >= {"health-diplomacy-security"}
    assert a.first_seen_at and a.sightings[0].retrieved_at and a.sightings[0].source_url
    b = by_number(db, "PAR-27-060")
    assert b.status == "forecasted" and any("Forecast" in r for r in reasons(b)) and b.award_text is None
    c = by_number(db, "PAR-27-050")                               # in NIH Guide, not yet on Grants.gov
    assert c.needs_review and c.deadline is None and c.award_text is None
    m = by_title(db, "Maternal health innovation call")[0]
    assert m.deadline == date(2027, 1, 30) and "500,000" in m.award_text and m.verification_status == "partially_verified"
    assert db.scalar(select(func.count()).select_from(Change).filter_by(change_type="created")) == s["new"]
    assert s["sources"]["manual-one"]["status"] == "skipped"
    assert s["sources"]["example-monitor"]["first_snapshot"] is True


# ---------------------------------------------------------------- duplicates
def test_same_opportunity_from_two_sources_is_one_record(db, tmp_path):
    run(db, tmp_path)
    a = by_number(db, "RFA-TW-27-001")
    assert db.scalar(select(func.count()).select_from(Opportunity).filter_by(opportunity_number="RFA-TW-27-001")) == 1
    assert {s.source.slug for s in a.sightings} == {"grants-gov", "nih-guide-rss"}
    assert not any("not yet found on Grants.gov" in r for r in reasons(a))
    # the same call announced at two URLs is one record
    assert len(by_title(db, "Climate-resilient health systems")) == 1


def test_running_twice_creates_no_duplicates_or_changes(db, tmp_path):
    s1 = run(db, tmp_path)
    n1 = db.scalar(select(func.count()).select_from(Opportunity))
    changes1 = db.scalar(select(func.count()).select_from(Change))
    s2 = run(db, tmp_path)
    assert db.scalar(select(func.count()).select_from(Opportunity)) == n1
    assert s2["new"] == 0 and s2["updated"] == 0 and s2["unchanged"] == s1["new"]
    assert db.scalar(select(func.count()).select_from(Change)) == changes1          # nothing reported as changed
    assert db.scalar(select(func.count()).select_from(Sighting)) > n1              # but the re-sighting is recorded
    assert s2["sources"]["example-monitor"]["page_changed"] is False


# ---------------------------------------------------------------- deadline changes
def test_deadline_change_is_detected(db, tmp_path):
    run(db, tmp_path)
    s2 = run(db, tmp_path, name="week2", a_deadline="Apr 15, 2027 12:00:00 AM EDT", a_hit_close="04/15/2027")
    a = by_number(db, "RFA-TW-27-001")
    assert s2["updated"] == 1 and s2["new"] == 0
    assert a.deadline == date(2027, 4, 15)
    ch = [c for c in a.changes if c.field == "deadline"]
    assert len(ch) == 1 and ch[0].old_value == "2027-03-01" and ch[0].new_value == "2027-04-15"
    assert a.last_changed_run_id == s2["run_id"]


def test_listing_and_official_record_disagree_is_flagged(db, tmp_path):
    run(db, tmp_path, a_deadline="Apr 15, 2027 12:00:00 AM EDT", a_hit_close="03/01/2027")
    a = by_number(db, "RFA-TW-27-001")
    assert a.verification_status == "mismatch" and a.needs_review
    assert a.deadline == date(2027, 4, 15)                                         # the official detail record wins


# ---------------------------------------------------------------- closed opportunities
def test_deadline_passing_closes_opportunity(db, tmp_path):
    run(db, tmp_path)
    s = run_deadlines(db, today=date(2027, 3, 2))
    a = by_number(db, "RFA-TW-27-001")
    assert a.status == "closed" and "2027-03-01" in a.status_reason
    assert any(c.field == "status" and c.new_value == "closed" for c in a.changes)
    assert any(x["id"] == a.id for x in s["closed_today"])


def test_page_that_says_closed(db, tmp_path):
    run(db, tmp_path)
    run(db, tmp_path, name="week2", maternal=fx.CALL_CLOSED)
    m = by_title(db, "Maternal health innovation call")[0]
    assert m.status == "closed" and any(c.field == "status" and c.new_value == "closed" for c in m.changes)


def test_opportunity_withdrawn_from_grants_gov(db, tmp_path):
    run(db, tmp_path)
    run(db, tmp_path, name="week2", include_b_in_search=False, b_detail_error=True)
    b = by_number(db, "PAR-27-060")
    assert b.status == "closed" and "No longer available" in b.status_reason


def test_closing_soon_report(db, tmp_path):
    run(db, tmp_path)
    s = run_deadlines(db, today=date(2027, 1, 20))
    soon = [x["title"] for v in s["closing_soon"].values() for x in v]
    assert "Maternal health innovation call" in soon


# ---------------------------------------------------------------- unavailable sources
def test_unavailable_source_does_not_stop_the_run_or_close_records(db, tmp_path):
    run(db, tmp_path)
    s = run(db, tmp_path, name="week2", search_error=True)
    assert s["status"] == "partial"
    assert s["sources"]["grants-gov"]["status"] == "failed" and "503" in s["sources"]["grants-gov"]["error"]
    assert s["sources"]["example-funder"]["status"] == "ok"
    assert by_number(db, "RFA-TW-27-001").status == "open"                          # not closed just because the source was down
    assert db.scalar(select(SourceFetch).filter_by(status="failed")) is not None


# ---------------------------------------------------------------- missing information
def test_missing_eligibility_is_flagged_not_invented(db, tmp_path):
    run(db, tmp_path)
    c = by_title(db, "Climate-resilient health systems")[0]
    assert c.eligibility is None and c.award_text is None
    assert c.needs_review and "Eligibility not found on the official page" in reasons(c)
    assert c.deadline == date(2026, 12, 15)
    b = by_number(db, "PAR-27-060")
    assert b.eligibility is None and any("Eligibility" in r for r in reasons(b))


# ---------------------------------------------------------------- malicious content
def test_instructions_in_external_pages_are_ignored(db, tmp_path):
    run(db, tmp_path)
    o = by_title(db, "Community health workers call")[0]
    assert o.deadline == date(2027, 3, 15)                    # visible, labelled deadline — not 2099 from hidden text/comments/script
    assert o.award_text is None                               # neither "$10 billion" (hidden) nor "$5 billion" (injected sentence)
    assert o.suspicious_content and o.needs_review
    assert o.verification_status != "verified"
    assert "Ignore" not in (o.description or "") and "2099" not in (o.description or "")
    assert any("instruction-like" in r for r in reasons(o))


def test_page_monitor_detects_change_for_review(db, tmp_path):
    run(db, tmp_path)
    s = run(db, tmp_path, name="week2", monitor=fx.MONITOR_V2)
    assert s["monitored_pages_changed"] == ["example-monitor"]
    snaps = db.scalars(select(PageSnapshot)).all()
    assert len(snaps) == 2 and snaps[-1].changed and not snaps[-1].reviewed


# ---------------------------------------------------------------- regressions found in the live runs
def test_reordered_applicant_types_are_not_a_change(db, tmp_path):
    run(db, tmp_path)
    s = run(db, tmp_path, name="week2", reverse_types=True)   # Grants.gov returns types in arbitrary order
    assert s["updated"] == 0
    assert not [c for c in by_number(db, "RFA-TW-27-001").changes if c.field == "eligibility"]


def test_past_deadline_listing_does_not_flap_between_runs(db, tmp_path):
    later = date(2027, 3, 10)                                   # source still says "open" after its deadline
    run(db, tmp_path, today=later)
    a = by_number(db, "RFA-TW-27-001")
    assert a.status == "closed" and "2027-03-01" in a.status_reason
    n_changes = len(a.changes)
    s2 = run(db, tmp_path, name="week2", today=later)
    assert s2["updated"] == 0 and len(by_number(db, "RFA-TW-27-001").changes) == n_changes


def test_far_future_placeholder_deadline_means_no_fixed_deadline(db, tmp_path):
    run(db, tmp_path, a_deadline="Jan 01, 2099 12:00:00 AM EST", a_hit_close="01/01/2099")
    a = by_number(db, "RFA-TW-27-001")
    assert a.deadline is None and a.deadline_text.startswith("No fixed deadline")
    assert a.status == "open" and a.verification_status == "verified"
