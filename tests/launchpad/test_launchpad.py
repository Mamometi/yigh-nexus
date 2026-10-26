"""Team Launchpad: links resolve to existing records first, other pages are saved only with what they say,
user-added items stay out of the shared list, and the one-pager is built around the user's goals."""
from datetime import date

import pytest
from sqlalchemy.orm import sessionmaker

from backend.launchpad import importer as L
from backend.radar.db import make_engine
from backend.radar.http import FixtureFetcher
from backend.radar.models import Opportunity
from backend.radar.pipeline import run_weekly
from backend.radar.api import _filtered
from backend.nexus.concept import _outline

from tests.radar import fixtures as fx

PAGE = "<html><head><title>Heat Resilience Fund 2027</title></head><body><h1>Heat Resilience Fund 2027</h1>" + \
       "<p>" + "We support research on extreme heat and health in cities. " * 10 + "</p></body></html>"


@pytest.fixture
def db(tmp_path, monkeypatch):
    engine = make_engine(tmp_path / "radar.db")
    s = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    run_weekly(s, FixtureFetcher(fx.write(tmp_path / "w1")), fx.REGISTRY, today=date.today())
    s.commit()
    monkeypatch.setattr(L, "_registry", lambda: fx.REGISTRY)
    return s


def test_known_link_reuses_existing_record(db):
    o = db.query(Opportunity).filter_by(opportunity_number="RFA-TW-27-001").one()
    before = db.query(Opportunity).count()
    got, how = L.import_link(db, o.official_url, fetcher=FixtureFetcher(".", {}))
    assert (got.id, how) == (o.id, "existing")
    got, how = L.import_link(db, "https://grants.nih.gov/grants/guide/rfa-files/RFA-TW-27-001.html", fetcher=FixtureFetcher(".", {}))
    assert got.id == o.id and db.query(Opportunity).count() == before


def test_other_page_is_saved_with_only_what_it_says_and_kept_out_of_shared_list(db, tmp_path):
    (tmp_path / "heat.html").write_text(PAGE)
    url = "https://heatfund.example.org/call"
    got, how = L.import_link(db, url, fetcher=FixtureFetcher(tmp_path, {f"GET {url}": "heat.html"}))
    assert how == "page" and got.title == "Heat Resilience Fund 2027"
    assert got.deadline is None and got.award_text is None and got.verification_status == "unverified" and got.needs_review
    assert got.id not in {o.id for o in db.scalars(_filtered(db))}
    again, how2 = L.import_link(db, url, fetcher=FixtureFetcher(tmp_path, {}))
    assert (again.id, how2) == (got.id, "existing")


def test_bad_links_get_a_plain_message(db):
    with pytest.raises(L.ImportError_, match="web link"):
        L.import_link(db, "not a link")
    with pytest.raises(L.ImportError_, match="couldn't open"):
        L.import_link(db, "https://blocked.example.org/x", fetcher=FixtureFetcher(".", {"GET https://blocked.example.org/x": {"error": "HTTP 403"}}))


def test_outline_uses_the_users_goals():
    ws = {"opportunity": {"title": "Heat", "description": "Applicants must address heat."},
          "external_partners": {"teams": [{"team": "Team option 1", "partners": []}]},
          "strategic_alignment": {"documented": [{"priority": "Climate & Health"}]}, "eligibility_and_collaboration_gaps": []}
    team = {"name": "Team option 1", "members": [{"name": "A", "proposed_role": {"text": "Could lead"}}]}
    out = _outline(ws, team, ["Map heat risk in Accra", "Train local health workers"])
    assert out["aims"] == ["Map heat risk in Accra.", "Train local health workers."]


def test_api_requires_sign_in():
    from fastapi.testclient import TestClient
    from backend.app.main import app
    c = TestClient(app)
    assert c.post("/api/launchpad/import", json={"url": "https://x.org"}).status_code == 401
    assert c.post("/api/launchpad/one-pager", json={"opportunity_id": 1, "goals": ["x"]}).status_code == 401
