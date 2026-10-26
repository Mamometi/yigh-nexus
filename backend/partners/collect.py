"""Collect partner organizations from documented sources.

1. YIGH GHES research training sites (official YIGH pages): each site institution is a documented YIGH
   partner; Yale faculty listed as US mentors there are linked by name to the faculty database.
   Personal contact details (emails, phone numbers) are not stored.
2. Yale faculty profile research activities: an institution named in the activity text and confirmed by
   ROR's affiliation matcher (in the activity's own country) is a documented faculty-level connection.
"""
from __future__ import annotations

import json
import re

from bs4 import BeautifulSoup
from sqlalchemy import select

from backend.app.classification.rules import extract_keywords
from backend.app.models import Faculty, FacultyActivity

from .ror import Ror
from .store import add_evidence, add_yale_link, upsert_org

GHES_BASE = "https://medicine.yale.edu/yigh/ghes/research-training-sites/"
GHES_COUNTRIES = ["burkina-faso", "ethiopia", "kenya", "nigeria", "senegal", "tanzania", "uganda", "colombia", "ecuador", "india",
                  "peru", "bangladesh", "lebanon", "malaysia", "samoa"]
CONTACT = re.compile(r"\S+@\S+|\b\d{3}[.\-\s]\d{3}[.\-\s]\d{4}\b|\bLab\b")


def _clean(t: str) -> str:
    return re.sub(r"\s+", " ", CONTACT.sub("", t)).strip()


def expertise_tags(text: str, ev_id: int) -> dict:
    return {k: ev_id for k in extract_keywords({"research_interests": text})} | {k: ev_id for k in extract_keywords({"bio": text})}


def ghes_sites(db, fetcher, ror: Ror, faculty_by_name: dict[str, int]) -> dict:
    stats = {"pages": 0, "sites": 0, "yale_links": 0, "errors": []}
    for slug in GHES_COUNTRIES:
        url = GHES_BASE + slug + "/"
        try:
            page = fetcher.get(url, min_interval=3.0)
        except Exception as e:  # noqa: BLE001
            stats["errors"].append(f"{slug}: {e}")
            continue
        stats["pages"] += 1
        soup = BeautifulSoup(page.text, "html.parser")
        main = soup.find("main") or soup
        country = (main.find("h1").get_text(strip=True) if main.find("h1") else slug.replace("-", " ").title())
        for h2 in main.find_all("h2"):
            name = h2.get_text(" ", strip=True)
            if not name or re.match(r"(?i)sites in|mentors?\b|faculty|contacts?\b|how to|apply|about|resources|faq", name):
                continue  # section headings, not institutions (a page-level mentor list can't be tied to one site)
            texts, mentors = [], []
            for el in h2.find_all_next():
                if el.name == "h2":
                    break
                if el.name in ("p", "li") and not el.find(["p", "li"]):
                    t = _clean(el.get_text(" ", strip=True))
                    if t and t not in ("Copy Link", "Read More") and not re.fullmatch(r"(US|Research Site) Mentor", t):
                        texts.append(t)
                if el.name == "li" and "US Mentor" in el.get_text(" ", strip=True):
                    mentors.append(el.get_text(" ", strip=True).split(" US Mentor")[0].strip())
            desc = " ".join(t for t in texts if not any(m and t.startswith(m) for m in mentors))[:2000]
            short = re.sub(r"\s*\([A-Z]{2,}\)\s*$", "", name)
            match = ror.match_affiliation(f"{short}, {country}")
            ror_rec = match if match and match.get("country") == country else None
            org = upsert_org(db, name=short, country=country, origin="ghes_site", ror=ror_rec, description=desc,
                             aliases=[name])
            anchor = f"{url}#{re.sub(r'[^a-z0-9]+', '-', short.lower()).strip('-')}"
            ev = add_evidence(db, org, "yale_partnership", url,
                              f"Listed by the Yale Institute for Global Health as a GHES research training site in {country}: {name}.")
            dev = add_evidence(db, org, "description", url, desc[:1500]) if desc else ev
            org.expertise = json.dumps({**json.loads(org.expertise or "{}"), **expertise_tags(desc, dev.id)})
            add_yale_link(db, org, link_type="ghes_training_site", evidence=ev,
                          detail=f"YIGH Global Health Emerging Scholars research training site ({country})")
            for m in mentors:
                fid = faculty_by_name.get(_name_key(m))
                if fid:  # only Yale faculty in our database; other mentors (e.g. from other US universities) are not Yale links
                    add_yale_link(db, org, link_type="ghes_training_site", evidence=ev, faculty_id=fid, faculty_name=m,
                                  detail="Listed as a US mentor for this YIGH training site")
                    stats["yale_links"] += 1
            stats["sites"] += 1
    db.flush()
    return stats


INSTITUTION_PHRASE = re.compile(
    r"((?:[A-Z][\w'’.\-]+ ){0,6}(?:University|Institute|Institut|Ministry of Health|Hospital|College|Centre|Center|Council|"
    r"Foundation|Agency|Laboratory|School of [A-Z][\w ]+)(?: (?:of|for|de|du|and) (?:[A-Z][\w'’.\-]+ ?){1,5})?)")


def faculty_activities(db, fdb, ror: Ror) -> dict:
    stats = {"activities": 0, "orgs": 0, "links": 0}
    faculty_url = "https://medicine.yale.edu"
    acts = fdb.scalars(select(FacultyActivity).where(FacultyActivity.activity_type == "Research")).all()
    for a in acts:
        locs = json.loads(a.locations or "[]")
        if not locs:
            continue
        stats["activities"] += 1
        country = locs[0].split(",")[-1].strip()
        if country in ("United States", "USA"):
            continue
        f = fdb.get(Faculty, a.faculty_id)
        text = f"{a.title or ''}. {a.synopsis or ''}"
        for phrase in dict.fromkeys(m.group(1).strip() for m in INSTITUTION_PHRASE.finditer(text)):
            if len(phrase.split()) < 2:
                continue
            match = ror.match_affiliation(f"{phrase}, {country}")
            if not match or match.get("country") != country:
                continue  # unconfirmed names are not recorded
            org = upsert_org(db, name=match["name"], country=match["country"], origin="faculty_activity", ror=match)
            ev = add_evidence(db, org, "project", f.source_url,
                              f"{f.name}'s Yale profile lists the research activity “{a.title}” ({country}), naming {phrase}.")
            org.expertise = json.dumps({**json.loads(org.expertise or "{}"), **expertise_tags(text, ev.id)})
            add_yale_link(db, org, link_type="faculty_activity", evidence=ev, faculty_id=f.id, faculty_name=f.name,
                          detail=f"Named in the research activity “{a.title}”")
            stats["orgs"] += 1
            stats["links"] += 1
    db.flush()
    return stats


def _name_key(name: str) -> str:
    n = re.sub(r",.*$", "", name)
    parts = [p for p in re.sub(r"[^A-Za-z\- ]", " ", n).split() if len(p) > 1]
    return f"{parts[0].lower()} {parts[-1].lower()}" if len(parts) >= 2 else n.lower()


def faculty_name_index(fdb) -> dict[str, int]:
    return {_name_key(f.name): f.id for f in fdb.scalars(select(Faculty))}
