"""Feed API endpoints over a database built by the pipeline from fixtures."""
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from backend.app.main import app
from backend.radar.db import get_radar_db, make_engine
from backend.radar.http import FixtureFetcher
from backend.radar.pipeline import run_weekly

from . import fixtures as fx


@pytest.fixture
def client(tmp_path):
    engine = make_engine(tmp_path / "radar.db")
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = Session()
    run_weekly(db, FixtureFetcher(fx.write(tmp_path / "w1")), fx.REGISTRY, today=date.today())
    run_weekly(db, FixtureFetcher(fx.write(tmp_path / "w2", a_deadline="Apr 15, 2027 12:00:00 AM EDT", a_hit_close="04/15/2027")),
               fx.REGISTRY, today=date.today())

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[get_radar_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_endpoints(client):
    allo = client.get("/api/radar/opportunities").json()
    assert allo["count"] >= 5 and "note" in allo
    open_ = client.get("/api/radar/opportunities", params={"status": "open"}).json()
    assert all(o["status"] == "open" for o in open_["opportunities"])

    assert client.get("/api/radar/opportunities/new").json()["count"] == 0        # second run found nothing new
    upd = client.get("/api/radar/opportunities/updated").json()
    assert upd["count"] == 1
    assert upd["opportunities"][0]["changes"][0] == {**upd["opportunities"][0]["changes"][0],
                                                     "field": "deadline", "old": "2027-03-01", "new": "2027-04-15"}

    pr = client.get("/api/radar/opportunities/priority/health-diplomacy-security").json()
    assert any(o["opportunity_number"] == "RFA-TW-27-001" for o in pr["opportunities"])
    assert client.get("/api/radar/opportunities/priority/nonsense").status_code == 404

    soon = client.get("/api/radar/opportunities/closing-soon", params={"days": 365}).json()
    assert all(o["days_left"] is not None and 0 <= o["days_left"] <= 365 for o in soon["opportunities"])

    oid = next(o["id"] for o in allo["opportunities"] if o["opportunity_number"] == "RFA-TW-27-001")
    d = client.get(f"/api/radar/opportunities/{oid}").json()
    assert d["verification"]["status"] == "verified" and d["verification"]["history"][0]["method"] == "official_api"
    assert {s["source"] for s in d["sources"]} >= {"Grants.gov", "NIH Guide"}
    assert any(c["field"] == "deadline" for c in d["changes"])
    assert client.get("/api/radar/opportunities/999999").status_code == 404

    review = client.get("/api/radar/review").json()
    assert any(o["title"] == "Community health workers call" for o in review["opportunities"])
    runs = client.get("/api/radar/runs/latest").json()
    assert runs["weekly"]["updated"] == 1
    assert any(s["id"] == "manual-one" and s["access_method"] == "manual" for s in client.get("/api/radar/sources").json())


def test_funder_timing_uses_recorded_dates_only(client):
    funders = client.get("/api/radar/funders").json()
    assert funders and all({"value", "label", "count"} <= set(f) for f in funders)
    with_opps = next(f for f in funders if f["count"] > 0)
    t = client.get(f"/api/radar/funders/{with_opps['value']}/timing").json()
    assert t["funder"]["slug"] == with_opps["value"] and t["headline"]
    recorded = {o["id"] for o in client.get("/api/radar/opportunities", params={"funder": with_opps["value"]}).json()["opportunities"]}
    listed = [o["id"] for k in ("open_now", "forecasted") for o in t[k]] + \
             [t[k]["id"] for k in ("last_opened", "last_closed", "first_recorded") if t[k]]
    assert set(listed) <= recorded                    # never cites an opportunity the Radar has not recorded for this funder
    assert all(o["status"] == "open" for o in t["open_now"]) and all(o["status"] == "forecasted" for o in t["forecasted"])
    assert "does not predict" in t["note"]
    assert client.get("/api/radar/funders/not-a-funder/timing").status_code == 404
