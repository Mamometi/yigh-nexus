"""Create the SQLite database and load faculty + funder data.

Usage (from the project root):
    .venv/bin/python -m backend.scripts.init_db          # create tables if missing, upsert data
    .venv/bin/python -m backend.scripts.init_db --reset  # drop everything and rebuild
"""
import json
import re
import sys
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.database import DB_PATH, Base, SessionLocal, engine
from backend.app.classification.rules import GEO_ALIASES, classify_priorities, region_kind
from backend.app.models import (Department, Faculty, FacultyActivity, FacultyAppointment, FacultyCoauthor,
                                FacultyInterest, FacultySourceText, Organization,
                                Funder, Opportunity, Region, ResearchInterest, School, StrategicPriority)

DATA = Path(__file__).resolve().parents[2] / "data"
RESEARCH_ACTIVITY_TYPES = {"Research", "PatientCare", "VolunteerActivity"}

PRIORITIES = [
    ("climate-health", "Climate & Health",
     "Health impacts of climate change, environmental exposures, and planetary health."),
    ("digital-health-ai", "Digital Health & AI",
     "Data science, AI/ML, mHealth, informatics and digital tools for health."),
    ("health-diplomacy-security", "Health Diplomacy & Security",
     "Global health security, pandemic preparedness, governance and diplomacy."),
    ("health-sovereignty", "Health Sovereignty",
     "Country-led health systems, local manufacturing, research capacity and equitable partnerships."),
]


def get_or_create(db: Session, model, **kw):
    obj = db.scalar(select(model).filter_by(**kw))
    if obj is None:
        obj = model(**kw)
        db.add(obj)
        db.flush()
    return obj


def region(db: Session, name: str) -> Region:
    name = GEO_ALIASES.get(name, name)
    kind = "global" if name == "Global" else region_kind(name)
    r = db.scalar(select(Region).filter_by(name=name))
    if r is None:
        r = Region(name=name, kind=kind)
        db.add(r)
        db.flush()
    return r


def regions(db: Session, names: list[str]) -> list[Region]:
    """Map names to Region rows, deduping aliases that resolve to the same region."""
    return list({r.id: r for r in (region(db, n) for n in names)}.values())


def seed_priorities(db: Session) -> dict:
    out = {}
    for slug, name, desc in PRIORITIES:
        p = db.scalar(select(StrategicPriority).filter_by(slug=slug)) or StrategicPriority(slug=slug)
        p.name, p.description = name, desc
        db.add(p)
        db.flush()
        out[slug] = p
    return out


def load_faculty(db: Session, priorities: dict) -> int:
    data = json.loads((DATA / "faculty.json").read_text())
    rows = [dict(r, source="yigh") for r in data["faculty"]]
    scraped_on = date.fromisoformat(data["scraped_on"]) if data.get("scraped_on") else None
    ysph_file = DATA / "faculty_ysph.json"
    if ysph_file.exists():  # YSPH faculty with documented global health work (scripts/scrape_ysph.py)
        yigh_slugs = {_slug(r["profile_url"]) for r in rows}
        rows += [r for r in json.loads(ysph_file.read_text())["faculty"] if _slug(r["profile_url"]) not in yigh_slugs]
    for r in rows:
        school = get_or_create(db, School, name=r["school"]) if r.get("school") else None
        f = db.scalar(select(Faculty).filter_by(source_url=r["profile_url"])) or Faculty(source_url=r["profile_url"])
        db.add(f)
        f.name, f.title, f.email, f.bio, f.school = r["name"], r.get("title"), r.get("email"), r.get("bio"), school
        f.source = r.get("source", "yigh")
        f.inclusion_reasons = json.dumps(r["inclusion_reasons"]) if r.get("inclusion_reasons") else None
        # Source data only. Generated classifications live in faculty_priorities /
        # faculty_keywords / faculty_regions and are written by classify_faculty.py.
        f.appointments.clear(); f.interests.clear(); f.source_texts.clear()
        f.activities.clear(); f.organizations.clear(); f.coauthors.clear()
        db.flush()

        for a in r.get("appointments", []):
            dept = get_or_create(db, Department, name=a["academic_unit"])
            if dept.school_id is None and school:
                dept.school = school
            f.appointments.append(FacultyAppointment(department=dept, title=a.get("title"), appointment_type=a.get("type")))
        if r.get("department"):
            f.department = get_or_create(db, Department, name=r["department"])

        seen = set()
        for category, names in (r.get("research_interests_by_category") or {}).items():
            for n in names:
                if n.lower() not in seen:
                    seen.add(n.lower())
                    f.interests.append(FacultyInterest(interest=get_or_create(db, ResearchInterest, name=n), category=category))
        for n in r.get("focus_areas", []):
            if n.lower() not in seen:
                seen.add(n.lower())
                f.interests.append(FacultyInterest(interest=get_or_create(db, ResearchInterest, name=n)))

        interest_text = "; ".join(n for names in (r.get("research_interests_by_category") or {}).values() for n in names)
        appts = "; ".join(f"{a.get('title')}, {a['academic_unit']} ({a.get('type')})" for a in r.get("appointments", []))
        for a in r.get("activities", []):
            f.activities.append(FacultyActivity(
                title=a.get("title"), activity_type=a.get("type"), start_date=_us_date(a.get("start")),
                end_date=_us_date(a.get("end")), locations=json.dumps(a.get("locations", [])), synopsis=a.get("synopsis")))
        for o in r.get("organizations", []):
            org = db.scalar(select(Organization).filter_by(name=o["name"]))
            if org is None:
                org = Organization(name=o["name"], url=o.get("url"))
                db.add(org)
                db.flush()
            if org not in f.organizations:
                f.organizations.append(org)
        for c in r.get("yale_coauthors", []):
            f.coauthors.append(FacultyCoauthor(coauthor_name=c["name"], coauthor_url=c.get("profile_url")))

        # Only research-type activities describe research. Committees, journal service, peer review and
        # talks (whose location is just where a lecture was given) are stored but not used as evidence.
        research_acts = [a for a in r.get("activities", []) if a.get("type") in RESEARCH_ACTIVITY_TYPES]
        activity_text = " ".join(f"{a.get('title') or ''}. {a.get('synopsis') or ''}" for a in research_acts)
        activity_locs = "; ".join(l for a in research_acts for l in a.get("locations", []))
        org_text = "; ".join(o["name"] for o in r.get("organizations", []))
        for fld, text in [("title", r.get("title")), ("bio", r.get("bio")),
                          ("research_interests", interest_text), ("appointments", appts),
                          ("activities", activity_text.strip()), ("activity_locations", activity_locs),
                          ("organizations", org_text)]:
            if text:
                f.source_texts.append(FacultySourceText(field=fld, text=text, source_url=r["profile_url"],
                                                        retrieved_on=scraped_on))
    db.flush()
    # Link co-authors to directory records by profile URL.
    # Link co-authors to directory records by profile slug (YIGH and YSPH use different hosts).
    by_slug = {_slug(u): i for i, u in db.execute(select(Faculty.id, Faculty.source_url))}
    for c in db.scalars(select(FacultyCoauthor)):
        c.coauthor_faculty_id = by_slug.get(_slug(c.coauthor_url or ""))
    return len(rows)


def _slug(url: str) -> str:
    m = re.search(r"/profile/([a-z0-9-]+)", url or "")
    return m.group(1) if m else url


def _us_date(s):
    """'09/01/2004' -> date."""
    try:
        m, d, y = (int(x) for x in s.split("/"))
        return date(y, m, d)
    except (AttributeError, ValueError):
        return None


def load_funders(db: Session, priorities: dict) -> tuple[int, int]:
    data = json.loads((DATA / "opportunities.json").read_text())
    n_opp = 0
    for r in data["funders"]:
        fu = db.scalar(select(Funder).filter_by(slug=r["id"])) or Funder(slug=r["id"])
        db.add(fu)
        fu.name, fu.funder_type, fu.headquarters = r["name"], r.get("type"), r.get("headquarters")
        fu.website, fu.funding_url = r.get("website"), r.get("funding_opportunities_url")
        fu.accepts_unsolicited, fu.notes = r.get("accepts_unsolicited_proposals"), r.get("notes")
        fu.source = r.get("source", "curated")
        fu.interests = [get_or_create(db, ResearchInterest, name=n) for n in dict.fromkeys(r.get("focus_areas", []))]
        fu.regions = regions(db, r.get("geographic_focus", []))
        fu.opportunities.clear()
        db.flush()
        for o in r.get("opportunities", []):  # present once scripts/opportunities.py has run
            opp = Opportunity(
                title=o["title"], description=o.get("description"), url=o["url"],
                deadline=date.fromisoformat(o["deadline"]) if o.get("deadline") else None,
                deadline_type=o.get("deadline_type", "unknown"), amount=o.get("amount"),
                eligibility=o.get("eligibility"), us_institutions_eligible=o.get("us_institutions_eligible"),
                status=o.get("status", "open"),
                source_checked_on=date.fromisoformat(o["source_checked_on"]) if o.get("source_checked_on") else None,
                interests=[get_or_create(db, ResearchInterest, name=n) for n in dict.fromkeys(o.get("focus_areas", []))],
                regions=regions(db, o.get("geographic_focus", [])),
            )
            text = " ".join(filter(None, [opp.title, opp.description, " ".join(o.get("focus_areas", []))]))
            opp.priorities = [priorities[slug] for slug in classify_priorities({"bio": text})]
            fu.opportunities.append(opp)
            n_opp += 1
    return len(data["funders"]), n_opp


def main(reset: bool) -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if reset:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db, db.begin():
        priorities = seed_priorities(db)
        n_fac = load_faculty(db, priorities)
        n_fun, n_opp = load_funders(db, priorities)
    print(f"{DB_PATH}: {n_fac} faculty, {n_fun} funders, {n_opp} opportunities")


if __name__ == "__main__":
    main("--reset" in sys.argv)
