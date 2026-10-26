"""Partner discovery: fabricated partnerships, outdated information, mismatched geography,
unsupported recommendations, dedupe and caching."""
import json
from datetime import timedelta

import pytest

from backend.nexus.shortlist import OpportunityProfile
from backend.partners.match import partner_card, partners_for_recommendation
from backend.partners.models import Org, make_session
from backend.partners.ror import Ror
from backend.partners.store import PartnershipEvidenceError, add_evidence, add_yale_link, now, upsert_org
from backend.radar.http import Response


@pytest.fixture
def db(tmp_path):
    return make_session(tmp_path / "partners.db")


def org(db, name, country, *, expertise=(), yale=False, faculty_id=None, verified_days_ago=0, evidence=True):
    o = upsert_org(db, name=name, country=country, origin="test")
    if evidence:
        ev = add_evidence(db, o, "description", f"https://example.org/{name.replace(' ', '-')}", f"{name} works on {', '.join(expertise)}.")
        o.expertise = json.dumps({t: ev.id for t in expertise})
    if yale:
        yev = add_evidence(db, o, "yale_partnership", "https://medicine.yale.edu/yigh/ghes/research-training-sites/x/", "Listed as a GHES site.")
        add_yale_link(db, o, link_type="ghes_training_site", evidence=yev, faculty_id=faculty_id, faculty_name="A Person" if faculty_id else None)
    o.last_verified_at = now() - timedelta(days=verified_days_ago)
    db.flush()
    return o


def card(o, topics=("Malaria",), targets=("Kenya",), team=(), requires_local=False):
    return partner_card(o, opp_topics=set(topics), targets=set(targets), team_ids=set(team), team_facets_missing=[],
                        requires_local=requires_local)


# ---------------------------------------------------------------- fabricated partnerships
def test_yale_relationship_requires_public_evidence(db):
    o = org(db, "Kenya Malaria Institute", "Kenya", expertise=["Malaria"])
    with pytest.raises(PartnershipEvidenceError):
        add_yale_link(db, o, link_type="ghes_training_site", evidence=None)
    desc_only = o.evidence[0]  # a description page is not evidence of a Yale relationship
    with pytest.raises(PartnershipEvidenceError):
        add_yale_link(db, o, link_type="faculty_activity", evidence=desc_only)
    with pytest.raises(PartnershipEvidenceError):
        add_evidence(db, o, "yale_partnership", "not-a-url", "made up")


def test_shared_interests_alone_are_only_proposed(db):
    o = org(db, "Kenya Malaria Institute", "Kenya", expertise=["Malaria"])
    c = card(o)
    assert c["relationship"]["status"] == "proposed" and not c["relationship"]["evidence"]
    assert any("no existing connection with Yale" in v for v in c["needs_verification"])
    documented = org(db, "Kenya Medical Research Institute", "Kenya", expertise=["Malaria"], yale=True)
    assert card(documented)["relationship"]["status"] == "documented"


def test_never_implies_agreement(db):
    o = org(db, "Kenya Medical Research Institute", "Kenya", expertise=["Malaria"], yale=True)
    text = json.dumps({k: v for k, v in card(o).items() if k != "note"}, default=str).lower()  # the note is the disclaimer
    assert "has agreed" not in text and "willing" not in text.replace("willingness to partner are unknown", "")
    assert "has been contacted or has agreed" in card(o)["note"]


# ---------------------------------------------------------------- outdated information
def test_outdated_records_are_flagged_for_reverification(db):
    old = org(db, "Old Institute", "Kenya", expertise=["Malaria"], verified_days_ago=400)
    c = card(old)
    assert c["stale"] and any("check their website" in v for v in c["needs_verification"])
    fresh = org(db, "Fresh Institute", "Kenya", expertise=["Malaria"], verified_days_ago=5)
    assert not card(fresh)["stale"]


# ---------------------------------------------------------------- mismatched geography
def test_geography_must_match(db):
    kenya = org(db, "Nairobi Health Institute", "Kenya", expertise=["Malaria"])
    uganda = org(db, "Kampala Health Institute", "Uganda", expertise=["Malaria"])
    brazil = org(db, "Sao Paulo Institute", "Brazil", expertise=["Malaria"])
    brazil_noexp = org(db, "Rio Institute", "Brazil", expertise=["Cancer"])
    ck, cu, cb = card(kenya, requires_local=True), card(uganda, requires_local=True), card(brazil, requires_local=True)
    assert ck["score"] > cu["score"] > cb["score"]
    assert ck["geographic_requirement"].startswith("Could help")
    assert cu["geographic_requirement"] == "Not in a required country" and cb["geographic_requirement"] == "Not in a required country"
    assert card(brazil_noexp) is None                     # wrong place and no relevant expertise -> not recommended


def test_local_requirement_gap_is_reported(db):
    org(db, "Sao Paulo Institute", "Brazil", expertise=["Malaria"])
    opp = OpportunityProfile(1, "u", "Malaria call", "malaria", None, topics={"Malaria"}, places={"Kenya"})
    doc = {"teams": [{"name": "T", "members": [], "missing_expertise": []}],
           "eligibility_concerns": [{"code": "lead_must_be_lmic", "concern": "Lead must be in Kenya"}]}
    out = partners_for_recommendation(db, doc, {}, opp)
    assert out["requires_local_partner"]
    assert any("needs a local partner" in g for g in out["teams"][0]["collaboration_gaps"])


# ---------------------------------------------------------------- unsupported recommendations
def test_organizations_without_evidence_are_not_recommended(db):
    o = org(db, "Phantom Institute", "Kenya", expertise=[], evidence=False)
    assert card(o) is None
    opp = OpportunityProfile(1, "u", "Malaria call", "malaria", None, topics={"Malaria"}, places={"Kenya"})
    out = partners_for_recommendation(db, {"teams": [{"name": "T", "members": [], "missing_expertise": []}]}, {}, opp)
    assert all(p["evidence_urls"] for t in out["teams"] for p in t["partners"])
    assert "Phantom Institute" not in json.dumps(out)


def test_team_member_link_ranks_higher(db):
    a = org(db, "Institute A", "Kenya", expertise=["Malaria"], yale=True, faculty_id=7)
    b = org(db, "Institute B", "Kenya", expertise=["Malaria"], yale=True)
    assert card(a, team=[7])["score"] > card(b, team=[7])["score"]
    assert card(a, team=[7])["relationship"]["with_team_members"] == ["A Person"]


# ---------------------------------------------------------------- dedupe and caching
def test_deduplication(db):
    ror = {"id": "https://ror.org/04r1cxt79", "name": "Kenya Medical Research Institute", "names": ["KEMRI"], "types": ["facility"],
           "country": "Kenya", "country_code": "KE", "website": "https://www.kemri.go.ke/"}
    a = upsert_org(db, name="Kenya Medical Research Institute (KEMRI)", country="Kenya", origin="ghes_site", ror=ror)
    b = upsert_org(db, name="KEMRI", country="Kenya", origin="faculty_activity")
    c = upsert_org(db, name="Kenya Medical Research Institute", country="Kenya", origin="faculty_activity", ror=ror)
    assert a.id == b.id == c.id and db.query(Org).count() == 1


class CountingFetcher:
    def __init__(self):
        self.n = 0

    def get(self, url, **_):
        self.n += 1
        return Response(url, 200, json.dumps({"items": [{"chosen": True, "organization": {
            "id": "https://ror.org/x", "names": [{"value": "Test U", "types": ["ror_display"]}], "types": ["education"],
            "locations": [{"geonames_details": {"country_name": "Kenya", "country_code": "KE"}}], "links": [], "status": "active"}}]}), now())


def test_registry_lookups_are_cached(db):
    f = CountingFetcher()
    r = Ror(db, f)
    assert r.match_affiliation("Test U, Kenya")["country"] == "Kenya"
    r.match_affiliation("Test U, Kenya")
    assert f.n == 1


def test_domestic_opportunity_gets_no_external_partners(db):
    org(db, "Kenya Medical Research Institute", "Kenya", expertise=["Health Systems"], yale=True)
    opp = OpportunityProfile(1, "u", "State Occupational Safety Surveillance", "State occupational health surveillance programs in US states.",
                             None, topics={"Health Systems"}, places=set())
    out = partners_for_recommendation(db, {"teams": [{"name": "T", "members": [], "missing_expertise": []}]}, {}, opp)
    assert out["teams"][0]["partners"] == [] and "no international dimension" in out["collaboration_gaps"][0]
