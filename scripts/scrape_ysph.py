"""Find Yale School of Public Health faculty with global health projects -> data/faculty_ysph.json.

Same profile parser as scrape_faculty.py. A YSPH faculty member is included when at least one
documented signal holds (recorded in `inclusion_reasons`):
  1. listed on the YSPH Global Health faculty directory;
  2. a Research-type profile activity located outside the United States;
  3. "Global Health" in their own research-interest list;
  4. a bio sentence tying a low/middle-income country or region to their research
     (same geography rules as Constellation's classifier, high-income countries excluded).
Faculty already in the YIGH affiliate list are skipped (matched by profile slug).
"""
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))
from scrape_faculty import get, profile  # noqa: E402
from backend.app.classification.rules import HIGH_INCOME, extract_geography  # noqa: E402

YSPH = "https://ysph.yale.edu"
OUT = ROOT / "data" / "faculty_ysph.json"
slug = lambda u: re.search(r"/profile/([a-z0-9-]+)", u).group(1)


def links(path):
    return sorted(set(re.findall(r'href="(?:https://ysph\.yale\.edu)?(/profile/[a-z0-9-]+/?)"', get(YSPH + path))))


# High-income countries/territories don't count as global health research sites on their own.
NOT_GLOBAL_HEALTH_SITES = HIGH_INCOME | {"United States", "Puerto Rico", "Norway", "Israel", "Denmark", "Sweden", "Austria",
                                         "Netherlands", "Belgium", "Finland", "Ireland", "New Zealand", "Singapore", "Romania",
                                         "Hong Kong", "Taiwan", "England", "Scotland"}
NON_RESEARCH_GEO = re.compile(r"visit(?:ing)? (?:her|his|their) family|visiting (?:professor|scholars?|faculty)|"
                              r"as (?:the )?president|university'?s partnerships|amplifying yale", re.I)
REVIEW_FILE = ROOT / "data" / "ysph_inclusion_review.json"


def reasons_for(r, on_gh_page):
    """Documented global-health signals. A 'Global Health' interest checkbox alone is not enough."""
    signals = []
    if on_gh_page:
        signals.append("Listed on the YSPH Global Health faculty directory")
    abroad = sorted({loc for a in r["activities"] if a.get("type") == "Research" for loc in a["locations"]
                     if loc and loc.split(",")[-1].strip() not in NOT_GLOBAL_HEALTH_SITES})
    if abroad:
        signals.append("Research activity in a low/middle-income setting: " + "; ".join(abroad[:4]))
    surname_words = {w.strip(",.").lower() for w in (r.get("name") or "").split()}
    bio = " ".join(s for s in re.split(r"(?<=[.!?])\s+", r.get("bio") or "") if not NON_RESEARCH_GEO.search(s))
    geo = extract_geography({"bio": bio})
    lmic = sorted(g for g, res in geo.items() if g not in NOT_GLOBAL_HEALTH_SITES and res.confidence >= 0.6
                  and g.lower() not in surname_words)
    if lmic:
        signals.append("Bio describes research in: " + ", ".join(lmic[:5]))
    interests = [i for v in (r.get("research_interests_by_category") or {}).values() for i in v]
    if signals and any(i.lower() == "global health" for i in interests):
        signals.append("Lists 'Global Health' as a research interest")
    return signals


def apply_review(rows):
    """Human review decisions (data/ysph_inclusion_review.json) override the rules, with the reason recorded."""
    if not REVIEW_FILE.exists():
        return rows
    decisions = {d["slug"]: d for d in json.loads(REVIEW_FILE.read_text())["decisions"]}
    out = []
    for r in rows:
        d = decisions.get(slug(r["profile_url"]))
        if d and d["decision"] == "exclude":
            continue
        if d and d["decision"] == "include" and not r.get("inclusion_reasons"):
            r["inclusion_reasons"] = [f"Included after manual review: {d['reason']}"]
        out.append(r)
    return out


def reevaluate():
    """Re-apply the current rules and review decisions to the stored records without re-scraping."""
    data = json.loads(OUT.read_text())
    rows = []
    for r in data["faculty"]:
        r["inclusion_reasons"] = reasons_for(r, any("YSPH Global Health faculty directory" in x for x in r.get("inclusion_reasons", [])))
        rows.append(r)
    kept = apply_review([r for r in rows if r["inclusion_reasons"]])
    data.update({"count": len(kept), "faculty": kept, "reevaluated": time.strftime("%Y-%m-%d")})
    OUT.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"re-evaluated {len(rows)} -> kept {len(kept)}")


def main():
    yigh = {slug(f["profile_url"]) for f in json.loads((ROOT / "data" / "faculty.json").read_text())["faculty"]}
    everyone = links("/school-of-public-health-faculty/directory-name/")
    gh_page = {slug(u) for u in links("/school-of-public-health-faculty/global-health/")}
    todo = [u for u in everyone if slug(u) not in yigh]
    print(f"{len(everyone)} YSPH profiles, {len(everyone) - len(todo)} already YIGH affiliates, checking {len(todo)}")

    def work(path):
        url = YSPH + path
        try:
            r = profile(url, {"listed_name": slug(url), "directory_categories": ["Public Health"]})
        except Exception as e:  # noqa: BLE001
            return {"profile_url": url, "error": str(e)}
        r["inclusion_reasons"] = reasons_for(r, slug(url) in gh_page)
        r["source"] = "ysph"
        return r

    with ThreadPoolExecutor(3) as ex:
        rows = list(ex.map(work, todo))
    errors = [r for r in rows if "error" in r]
    kept = apply_review([r for r in rows if r.get("inclusion_reasons")])
    kept.sort(key=lambda r: r["name"].split(",")[0].split()[-1])
    OUT.write_text(json.dumps({"source": YSPH + "/school-of-public-health-faculty/", "scraped_on": time.strftime("%Y-%m-%d"),
                               "checked": len(todo), "errors": len(errors), "count": len(kept), "faculty": kept},
                              indent=2, ensure_ascii=False))
    print(f"checked {len(todo)}, errors {len(errors)}, included {len(kept)} -> {OUT}")


if __name__ == "__main__":
    reevaluate() if "--reevaluate" in sys.argv else main()
