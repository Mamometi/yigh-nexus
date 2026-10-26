"""YIGH Nexus matching: retrieval grounding, Stage A, eligibility, the PydanticAI agent's guard-rails
(scripted with FunctionModel — no API calls), caching/triggers, fallback and API."""
import json
import os
from datetime import date

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RequestUsage
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

from backend.app.database import SessionLocal
from backend.radar.db import make_engine
from backend.radar.http import FixtureFetcher
from backend.radar.models import Opportunity
from backend.radar.pipeline import run_weekly
from backend.radar.api import PRIORITY_NAMES
from backend.nexus import api as nexus_api
from backend.nexus.retrieval import FacultyIndex, load_dossiers
from backend.nexus.service import Matcher, ModelCall, nexus_session
from backend.nexus.shortlist import eligibility_concerns, profile_opportunity, stage_a

from tests.radar import fixtures as fx


@pytest.fixture(scope="module")
def ix():
    return FacultyIndex(load_dossiers(SessionLocal()))


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    rdb = sessionmaker(bind=make_engine(tmp_path / "radar.db"), autoflush=False, expire_on_commit=False)()
    run_weekly(rdb, FixtureFetcher(fx.write(tmp_path / "w1")), fx.REGISTRY, today=date(2026, 10, 26))
    ndb = nexus_session(str(tmp_path / "nexus.db"))
    opp = rdb.scalar(select(Opportunity).filter_by(opportunity_number="RFA-TW-27-001"))
    return {"rdb": rdb, "ndb": ndb, "opp": opp, "tmp": tmp_path}


def scripted(responses, calls):
    """A FunctionModel that returns the given JSON strings in turn (each one is one model request)."""
    def fn(messages, info):
        calls.append(messages)
        body = responses[min(len(calls) - 1, len(responses) - 1)]
        return ModelResponse(parts=[TextPart(body if isinstance(body, str) else json.dumps(body))],
                             usage=RequestUsage(input_tokens=1200, output_tokens=300), model_name="scripted")
    return FunctionModel(fn, model_name="scripted-test")


def valid_output(shortlist_rows, ix, *, why="Documented pandemic preparedness work.", extra_team_text="", elig=None):
    a, b = shortlist_rows[0]["faculty_id"], shortlist_rows[1]["faculty_id"]
    ev = lambda fid: [next(iter(ix.d[fid].evidence))]
    return {
        "top_faculty": [{"faculty_id": a, "relevance_score": 80, "why_relevant": why, "evidence_ids": ev(a)},
                        {"faculty_id": b, "relevance_score": 70, "why_relevant": "Methods overlap.", "evidence_ids": ev(b)}],
        "teams": [{"name": "Team A", "members": [
            {"faculty_id": a, "proposed_role": "Lead: health security", "contribution_hypothesis": "Could lead the science aims.", "evidence_ids": ev(a)},
            {"faculty_id": b, "proposed_role": "Co-I: methods", "contribution_hypothesis": "Could contribute methods.", "evidence_ids": ev(b)}],
            "complementarity_hypothesis": "Subject plus methods." + extra_team_text, "requirements_covered": ["topic: Pandemic Preparedness"],
            "missing_expertise": ["health economics"], "match_score": 72, "score_explanation": "Two of three facets."}],
        "yigh_alignment": "Health Diplomacy & Security.", "missing_capabilities": ["LMIC lead institution"],
        "additional_eligibility_concerns": elig or [], "overall_match_score": 70, "overall_explanation": "Reasonable fit."}


# ---------------------------------------------------------------- Step 1: retrieval tools
def test_retrieval_is_documented_and_sourced(ix):
    for hits in (ix.by_expertise(["Malaria"]), ix.by_method(["Epidemiology"]), ix.by_priority("Climate & Health"),
                 ix.by_geography("Kenya"), ix.projects("malaria vaccine")):
        assert hits
        for h in hits:
            assert h["profile_url"].startswith("https://")
            for e in h["evidence"]:
                assert e["id"] in ix.d[h["faculty_id"]].evidence and e["source_url"] == h["profile_url"]
    # wider-region matching: someone tagged East Africa/Uganda shows up for Kenya
    assert any("Kenya" not in {e["label"] for e in h["evidence"]} for h in ix.by_geography("Kenya"))


# ---------------------------------------------------------------- Stage A
def test_stage_a_scores_are_tied_to_evidence(env, ix):
    p = profile_opportunity(env["opp"], PRIORITY_NAMES)
    rows = stage_a(ix, p, 10)
    assert rows and rows == sorted(rows, key=lambda r: -r["score"])
    for r in rows:
        assert all(e in ix.d[r["faculty_id"]].evidence for e in r["evidence_ids"])
    assert "Pandemic Preparedness & Health Security" in p.topics


# ---------------------------------------------------------------- eligibility accuracy
@pytest.mark.parametrize("text,expected", [
    ("Applicants must be based in a low- or middle-income country.", {"lead_must_be_lmic"}),
    ("This is a limited submission: one application per institution.", {"limited_submission"}),
    ("Open to early-stage investigators within 10 years of completing their terminal degree.", {"career_stage"}),
    ("Applicants must be U.S. citizens or permanent residents.", {"us_citizens"}),
    ("Small businesses only (SBIR).", {"small_business"}),
    ("County governments, Small businesses, City or township governments, Nonprofits having a 501(c)(3) status", {"no_higher_ed"}),
    ("Private institutions of higher education, Public and State controlled institutions of higher education, Nonprofits", set()),
    ("Foreign institutions are eligible to apply.", set()),
    (None, {"not_stated"}),
])
def test_eligibility_checker(text, expected):
    got = {c["code"] for c in eligibility_concerns(text)}
    assert got == expected
    for c in eligibility_concerns(text):
        assert c["quote"] is None or c["quote"] in (text or "")


# ---------------------------------------------------------------- Stage B agent guard-rails
def _matcher(env, model=None):
    return Matcher(SessionLocal(), env["rdb"], env["ndb"], model=model)


def test_agent_valid_output_is_accepted_and_logged(env, ix):
    m = _matcher(env)
    rows = stage_a(m.ix, profile_opportunity(env["opp"], PRIORITY_NAMES), 15)
    calls = []
    m.model = scripted([valid_output(rows, m.ix)], calls)
    doc = m.recommend(env["opp"].id)
    assert doc["generated_by"] == "ai:scripted-test" and not doc["validation"]["model_error"]
    t = doc["teams"][0]
    assert t["members"][0]["proposed_role"]["label"] == "AI suggestion: please check"
    assert t["members"][0]["documented_evidence"][0]["source_url"].startswith("https://")
    log = env["ndb"].scalars(select(ModelCall)).all()
    assert len(log) == 1 and log[0].input_tokens == 1200 and log[0].output_tokens == 300 and log[0].latency_ms >= 0


def test_agent_must_use_shortlist_and_real_evidence(env):
    m = _matcher(env)
    rows = stage_a(m.ix, profile_opportunity(env["opp"], PRIORITY_NAMES), 15)
    bad = valid_output(rows, m.ix)
    bad["top_faculty"][0]["faculty_id"] = 999999                       # not shortlisted
    bad["teams"][0]["members"][1]["evidence_ids"] = ["F1-exp-999"]     # invented evidence
    calls = []
    m.model = scripted([bad, valid_output(rows, m.ix)], calls)
    doc = m.recommend(env["opp"].id)
    assert len(calls) == 2                                              # validator forced a retry
    shortlisted = {r["faculty_id"] for r in rows}
    assert {p["faculty_id"] for p in doc["top_faculty"]} <= shortlisted


def test_unsupported_claims_are_removed(env):
    m = _matcher(env)
    rows = stage_a(m.ix, profile_opportunity(env["opp"], PRIORITY_NAMES), 15)
    out = valid_output(rows, m.ix, why="Dr. X is very interested and available to lead this. Documented outbreak work.",
                       extra_team_text=" They have previously collaborated on outbreaks.")
    m.model = scripted([out], [])
    doc = m.recommend(env["opp"].id)
    text = json.dumps(doc["top_faculty"]) + json.dumps(doc["teams"])
    assert "interested" not in text and "previously collaborated" not in text
    assert len(doc["validation"]["unsupported_claims_removed"]) == 2


def test_eligibility_notes_need_a_real_quote(env):
    m = _matcher(env)
    rows = stage_a(m.ix, profile_opportunity(env["opp"], PRIORITY_NAMES), 15)
    out = valid_output(rows, m.ix, elig=[{"concern": "Foreign institutions eligible", "quote": "Foreign institutions are eligible to apply"},
                                         {"concern": "Only Harvard may apply", "quote": "Only Harvard University may apply"}])
    m.model = scripted([out], [])
    doc = m.recommend(env["opp"].id)
    assert any(c.get("code") == "ai_noted" for c in doc["eligibility_concerns"])
    assert [d["concern"] for d in doc["validation"]["eligibility_notes_dropped"]] == ["Only Harvard may apply"]


# ---------------------------------------------------------------- Step 4: cache and triggers
def test_cache_and_reruns(env):
    m = _matcher(env)
    rows = stage_a(m.ix, profile_opportunity(env["opp"], PRIORITY_NAMES), 15)
    calls = []
    m.model = scripted([valid_output(rows, m.ix)], calls)
    first = m.recommend(env["opp"].id)
    again = m.recommend(env["opp"].id)
    assert not first["cache"]["hit"] and again["cache"]["hit"] and len(calls) == 1     # unchanged -> no model call
    # requirements change materially -> rerun
    env["opp"].content_hash = "changed-requirements"
    env["rdb"].commit()
    assert not m.recommend(env["opp"].id)["cache"]["hit"] and len(calls) == 2
    # a shortlisted faculty profile is updated -> rerun
    m.ix.d[rows[0]["faculty_id"]].bio += " Updated profile text."
    assert not m.recommend(env["opp"].id)["cache"]["hit"] and len(calls) == 3
    # admin refresh forces a rerun even with nothing changed
    assert not m.recommend(env["opp"].id, force=True, trigger="admin_refresh")["cache"]["hit"] and len(calls) == 4
    # a radar run triggers only the opportunities it found or changed
    res = m.refresh_after_radar_run()
    assert res["trigger"] == "radar_run" and res["opportunities"] >= 1


def test_no_key_uses_rule_based_fallback(env):
    m = _matcher(env)                                    # no model, no API key
    doc = m.recommend(env["opp"].id)
    assert doc["generated_by"] == "rules"
    assert doc["teams"] and doc["teams"][0]["members"][0]["proposed_role"]["label"] == "Suggestion: please check"
    assert env["ndb"].scalar(select(ModelCall)) is None


def test_model_error_falls_back_and_is_logged(env):
    def boom(messages, info):
        raise RuntimeError("upstream 529 overloaded")
    m = _matcher(env, FunctionModel(boom, model_name="broken"))
    doc = m.recommend(env["opp"].id)
    assert doc["generated_by"].startswith("rules (AI fallback")
    assert "529" in doc["validation"]["model_error"]
    assert env["ndb"].scalar(select(ModelCall)).status == "error"


# ---------------------------------------------------------------- API
def test_api(env):
    nexus_api.get_matcher.cache_clear()
    m = _matcher(env)
    from backend.app.main import app
    app.dependency_overrides = {}
    nexus_api.get_matcher = lambda: m  # noqa: E731 — swap in the test matcher
    c = TestClient(app)
    r = c.get("/api/nexus/faculty/search", params={"expertise": "Malaria", "place": "Kenya"}).json()
    assert r["count"] >= 1 and all(h["profile_url"] for h in r["faculty"])
    assert c.get("/api/nexus/faculty/search").status_code == 400
    doc = c.get(f"/api/nexus/opportunities/{env['opp'].id}/recommendation", params={"mode": "rules"}).json()
    assert doc["opportunity"]["number"] == "RFA-TW-27-001" and len(doc["top_faculty"]) <= 5 and len(doc["teams"]) <= 3
    assert c.get("/api/nexus/opportunities/999999/recommendation").status_code == 404
    assert c.post(f"/api/nexus/opportunities/{env['opp'].id}/refresh", params={"mode": "rules"}).json()["cache"]["hit"] is False
    assert "totals" in c.get("/api/nexus/model-calls").json()
