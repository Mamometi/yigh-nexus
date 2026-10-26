"""Scrape YIGH affiliated faculty directory into faculty.json."""
import json, re, time, html
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
from bs4 import BeautifulSoup

BASE = "https://medicine.yale.edu"
LIST_URL = BASE + "/yigh/faculty-support-initiative/affiliated-faculty/"
OUT = Path(__file__).resolve().parent.parent / "data" / "faculty.json"

COUNTRIES = """Afghanistan Albania Algeria Angola Argentina Armenia Australia Austria Bangladesh Belgium Belize Benin Bhutan Bolivia Botswana Brazil Burkina Faso Burundi Cambodia Cameroon Canada Chad Chile China Colombia Congo Costa Rica Cuba Denmark Ecuador Egypt El Salvador Eritrea Eswatini Ethiopia France Gabon Gambia Georgia Germany Ghana Greece Guatemala Guinea Haiti Honduras India Indonesia Iran Iraq Ireland Israel Italy Jamaica Japan Jordan Kazakhstan Kenya Korea Kyrgyzstan Laos Lebanon Lesotho Liberia Libya Madagascar Malawi Malaysia Mali Mexico Mongolia Morocco Mozambique Myanmar Namibia Nepal Netherlands Nicaragua Niger Nigeria Norway Pakistan Palestine Panama Papua New Guinea Paraguay Peru Philippines Poland Portugal Puerto Rico Qatar Russia Rwanda Saudi Arabia Senegal Sierra Leone Singapore Somalia South Africa South Sudan Spain Sri Lanka Sudan Sweden Switzerland Syria Taiwan Tajikistan Tanzania Thailand Timor-Leste Togo Tunisia Turkey Uganda Ukraine United Kingdom Uruguay Uzbekistan Venezuela Vietnam Yemen Zambia Zimbabwe""".split(" ")
# rebuild multi-word names
MULTI = ["Burkina Faso","Costa Rica","El Salvador","Papua New Guinea","Puerto Rico","Saudi Arabia","Sierra Leone","South Africa","South Sudan","Sri Lanka","United Kingdom"]
_multi_parts = {p for m in MULTI for p in m.split()}
COUNTRY_NAMES = MULTI + [c for c in COUNTRIES if c not in _multi_parts] + ["Sudan", "Guinea", "Africa"]
REGIONS = ["Sub-Saharan Africa","East Africa","West Africa","Southern Africa","Latin America","Caribbean","South Asia","Southeast Asia","East Asia","Middle East","Central America","Central Asia","Eastern Europe","Pacific Islands","low- and middle-income countries","LMICs"]


def get(url, tries=5):
    for i in range(tries):
        try:
            out = subprocess.run(["curl", "-sfL", "--max-time", "30", "-A", "Mozilla/5.0", url], capture_output=True, check=True)
            return out.stdout.decode("utf-8", "replace")
        except Exception:
            time.sleep(2 * (i + 1))
    raise RuntimeError(url)


def text(el):
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip() if el else None


def listing():
    soup = BeautifulSoup(get(LIST_URL), "html.parser")
    people = {}
    for item in soup.select(".categorized-list-item"):
        cat_el = item.find(["h2", "h3", "h4", "button"])
        category = text(cat_el)
        for a in item.select("a.hyperlink[href*='/profile/']"):
            url = BASE + a["href"]
            people.setdefault(url, {"listed_name": text(a), "directory_categories": []})
            if category and category not in people[url]["directory_categories"]:
                people[url]["directory_categories"].append(category)
    return people


def geo_from(textblob):
    found = []
    for name in REGIONS + COUNTRY_NAMES:
        if re.search(r"\b" + re.escape(name) + r"\b", textblob) and name not in found:
            if name == "Africa" and any(r for r in found if "Africa" in r):
                continue
            if name in ("Sudan", "Guinea") and any(f.endswith(name) and f != name for f in found):
                continue
            found.append(name)
    return found


def profile(url, meta):
    soup = BeautifulSoup(get(url), "html.parser")
    appts = []
    for card in soup.select("[class*='profile-details-appointment-card']"):
        unit = card.select_one(".profile-details-appointment-card__academic-unit")
        if not unit:
            continue
        appts.append({
            "academic_unit": text(unit),
            "title": text(card.select_one(".profile-details-appointment-card__title")),
            "type": text(card.select_one(".profile-details-appointment-card__type")),
        })
    # dedupe (nested selectors can repeat)
    appts = [dict(t) for t in dict.fromkeys(tuple(a.items()) for a in appts)]

    interests = {}
    for c in soup.select(".profile-details-research-section-overview__keyword-container"):
        h = text(c.select_one(".profile-details-research-section-overview__keyword-heading"))
        v = text(c.select_one(".profile-details-research-section-overview__keyword"))
        if h and v:
            interests[h] = [s.strip() for s in v.split(";") if s.strip()]
    glance = [text(k) for k in soup.select(".profile-details-interest__keyword")]

    email = None
    for m in soup.select(".profile-details-header-info a[href^='mailto:'], [class*='contact'] a[href^='mailto:']"):
        addr = m["href"][7:].split("?")[0]
        if addr.lower() != "ysm.editor@yale.edu":
            email = addr
            break

    bio = text(soup.select_one(".profile-details-bio-content-section__bio"))
    title = text(soup.select_one(".profile-details-header-info__title"))
    name = text(soup.select_one(".profile-details-header-info__name"))

    explicit_geo = []
    for h, vals in interests.items():
        if re.search(r"countr|region|geograph|global", h, re.I):
            explicit_geo += vals
    geo = explicit_geo or geo_from(" ".join(filter(None, [bio, title])))

    focus = []
    for vals in interests.values():
        focus += [v for v in vals if v not in focus]
    for g in glance:
        if g and g not in focus:
            focus.append(g)

    # International / research activities entered on the profile (dates, places, synopsis).
    activities = []
    for card in soup.select("article.achievement-card--type--activity"):
        card_meta = [text(m) for m in card.select(".achievement-card__metadata")]
        dates = next((m for m in card_meta if re.search(r"\d{2}/\d{2}/\d{4}", m or "")), None)
        start, end = (dates.split(" - ") + [None])[:2] if dates else (None, None)
        loc_text = text(card.select_one(".achievement-activity-card__metadata-item"))
        activities.append({
            "title": text(card.select_one(".achievement-card__title")),
            "type": next((m for m in card_meta if m and m != dates), None),
            "start": start, "end": end,
            "locations": [l.strip() for l in (loc_text or "").split(";") if l.strip()],
            "synopsis": text(card.select_one(".achievement-activity-card__abstract")),
        })

    # Yale co-authors: "frequent collaborators of [name]'s published research" (publication-derived).
    coauthors = []
    for c in soup.select(".profile-details-co-author"):
        link = c.select_one(".profile-details-co-author__profile-link-wrapper a[href]")
        href = link["href"] if link else None
        coauthors.append({"name": text(c.select_one(".profile-details-co-author__name")),
                          "profile_url": urljoin(url, href) if href else None})

    organizations = []
    for a in soup.select(".profile-details-organization-list__list a"):
        org_name = text(a)
        if org_name and org_name not in [o["name"] for o in organizations]:
            organizations.append({"name": org_name, "url": a.get("href")})

    primary = next((a for a in appts if (a["type"] or "").lower() == "primary"), appts[0] if appts else None)
    return {
        "name": name or meta["listed_name"],
        "title": title,
        "school": meta["directory_categories"][0] if meta["directory_categories"] else None,
        "department": primary["academic_unit"] if primary else None,
        "appointments": appts,
        "geographic_focus": geo,
        "geographic_focus_source": "profile" if explicit_geo else ("derived_from_bio" if geo else None),
        "bio": bio,
        "focus_areas": focus,
        "research_interests_by_category": interests,
        "email": email,
        "activities": activities,
        "yale_coauthors": coauthors,
        "organizations": organizations,
        "directory_categories": meta["directory_categories"],
        "profile_url": url,
    }


def main():
    people = listing()
    print(f"{len(people)} faculty listed")
    def work(item):
        url, meta = item
        try:
            return profile(url, meta)
        except Exception as e:
            print("FAILED", url, e)
            return {"name": meta["listed_name"], "profile_url": url, "error": str(e)}
    with ThreadPoolExecutor(2) as ex:
        rows = list(ex.map(work, people.items()))
    rows.sort(key=lambda r: r["name"].split(",")[0].split()[-1] if r.get("name") else "")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"source": LIST_URL, "scraped_on": time.strftime("%Y-%m-%d"), "count": len(rows), "faculty": rows}, indent=2, ensure_ascii=False))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
