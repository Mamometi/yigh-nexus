"""Award-letter reader: pulls the key facts out of an award letter and flags the Yale agreements and approvals it points to.

Every fact comes with the sentence it was found in, so people can check it. Nothing is guessed: if a fact isn't in the
letter, it is left out. With an AI model configured, an agent reads the letter first; any fact whose quote can't be found
word-for-word in the letter is dropped. Without AI (or if the call fails), the rules below do the reading.
"""
from __future__ import annotations

import re
import time

from pydantic import BaseModel, Field

from backend import llm

FUNDERS = [
    "National Institutes of Health", "Fogarty International Center", "National Institute of Allergy and Infectious Diseases",
    "National Cancer Institute", "National Heart, Lung, and Blood Institute", "National Institute of Mental Health",
    "Eunice Kennedy Shriver National Institute of Child Health and Human Development", "National Institute on Drug Abuse",
    "Centers for Disease Control and Prevention", "U.S. Agency for International Development", "USAID",
    "National Science Foundation", "Department of Defense", "Bill & Melinda Gates Foundation", "Gates Foundation",
    "Wellcome Trust", "Wellcome", "World Health Organization", "Rockefeller Foundation", "Doris Duke", "PEPFAR",
    "Global Fund", "UNICEF", "World Bank", "Fogarty", "Patient-Centered Outcomes Research Institute",
]
COUNTRIES = [
    "Afghanistan", "Argentina", "Bangladesh", "Benin", "Bolivia", "Botswana", "Brazil", "Burkina Faso", "Burundi", "Cambodia",
    "Cameroon", "Chile", "China", "Colombia", "Côte d'Ivoire", "Democratic Republic of the Congo", "Dominican Republic",
    "Ecuador", "Egypt", "Ethiopia", "Ghana", "Guatemala", "Guinea", "Haiti", "Honduras", "India", "Indonesia", "Jordan",
    "Kenya", "Lebanon", "Lesotho", "Liberia", "Madagascar", "Malawi", "Malaysia", "Mali", "Mexico", "Mozambique", "Myanmar",
    "Nepal", "Nicaragua", "Niger", "Nigeria", "Pakistan", "Peru", "Philippines", "Rwanda", "Samoa", "Senegal", "Sierra Leone",
    "South Africa", "Sri Lanka", "Sudan", "Tanzania", "Thailand", "Uganda", "Ukraine", "Vietnam", "Zambia", "Zimbabwe",
]

# What a phrase in the letter suggests you'll need at Yale. Each maps to a GRAPPH guide (and its office).
NEEDS = [
    ("subcontracts-and-subawards", "A subaward to a partner institution",
     r"subaward|sub-award|subrecipient|sub-recipient|consortium|foreign component|collaborating institution|partner institution"),
    ("supplier-gateway", "Setting up suppliers or vendors to be paid",
     r"\bvendors?\b|\bsuppliers?\b|contractor|consultant|consulting fees?"),
    ("purchasing-goods-and-services", "Buying goods or services for the project",
     r"\bpurchas\w*|procure\w*|\bequipment\b|\bsupplies\b"),
    ("irb-international-research", "Ethics (IRB) approval for human participants",
     r"human subjects?|human participants?|\bparticipants\b|\benrol\w*|\bIRB\b|clinical trial|informed consent"),
    ("international-shipping", "Shipping materials or specimens",
     r"\bship\w*|specimens?|biospecimens?|\bsamples?\b"),
    ("export-controls", "Export controls for equipment, data or sanctioned places",
     r"export control|\bequipment\b.*(abroad|overseas|to [A-Z])|sanction\w*"),
    ("hiring-and-paying-people-internationally", "Hiring or paying people abroad",
     r"in-country staff|field (staff|workers?)|community health workers?|local staff|stipends?|salar(y|ies) .*abroad|personnel .*(abroad|overseas)"),
    ("international-travel", "Travel abroad",
     r"\btravel\w*|site visits?"),
    ("data-sharing-and-repositories", "A data management and sharing plan",
     r"data management and sharing|data sharing|\bDMS\b|data management plan"),
    ("memoranda-of-understanding", "A partnership agreement or MOU",
     r"memorandum of understanding|\bMOU\b|collaboration agreement|partnership agreement"),
]


class Fact(BaseModel):
    value: str = Field(description="The fact, as short as possible")
    quote: str = Field(description="The exact sentence or line from the letter that states it, copied word for word")


class AILetter(BaseModel):
    funder: Fact | None = None
    award_number: Fact | None = None
    project_title: Fact | None = None
    principal_investigator: Fact | None = None
    project_period: Fact | None = None
    amount: Fact | None = None
    countries: list[Fact] = []
    partner_institutions: list[Fact] = []
    summary: str = Field(default="", description="Two sentences on what the project will do, only from the letter")


AI_RULES = """You read grant award letters (notices of award) for Yale researchers. Extract only facts that are stated in the
letter. For every fact give the exact sentence or line from the letter, copied word for word, as `quote`. If a fact is not in
the letter, leave it empty. Never guess, infer or add anything. partner_institutions: organizations other than Yale and the
funder that will do part of the work (for example subrecipients or collaborating sites)."""


def _sentence(text: str, start: int, end: int) -> str:
    """The sentence (or line) around a match, trimmed for display."""
    a = max(text.rfind(". ", 0, start), text.rfind("\n", 0, start)) + 1
    ends = [i for i in (text.find(". ", end), text.find("\n", end)) if i != -1]
    b = min(ends) + 1 if ends else len(text)
    s = " ".join(text[a:b].split())
    return s if len(s) <= 260 else s[:257] + "…"


def _labelled(text: str, labels: str) -> tuple[str, str] | None:
    """Value after a label such as 'Project Title:' on the same line."""
    m = re.search(rf"(?im)^\s*(?:{labels})\s*[:#]?\s*(.+)$", text)
    if not m:
        return None
    v = re.sub(r"^\(?(?:FAIN|no\.?|number)\)?\s*[:#]?\s*", "", m.group(1).strip(" .;"), flags=re.I)
    return (v[:200], _sentence(text, m.start(), m.end())) if len(v) > 1 else None


def rules_read(text: str, partner_names: list[str]) -> dict:
    facts: dict = {}

    def put(key: str, found):
        if found:
            facts[key] = {"value": found[0], "quote": found[1]}

    low = text.lower()
    found = [(f, low.find(f.lower())) for f in FUNDERS if low.find(f.lower()) != -1]
    if found:
        f, i = found[0]
        # NIH plus a named institute or center: say both, e.g. "National Institutes of Health (Fogarty International Center)"
        inst = next((g for g, _ in found[1:] if re.search(r"institute|center", g, re.I) and g != f), None) if f == "National Institutes of Health" else None
        put("funder", (f"{f} ({inst})" if inst else f, _sentence(text, i, i + len(f))))
    num = _labelled(text, r"award\s*(?:number|no\.?|#|id)|grant\s*(?:number|no\.?|id)|federal award (?:identification )?number|FAIN|investment id")
    if not num:
        m = re.search(r"\b(\d?[A-Z]\d{2}\s?[A-Z]{2}\d{6}(?:-\d{2})?|INV-\d{5,}|OPP\d{6,})\b", text)
        num = (m.group(1), _sentence(text, m.start(), m.end())) if m else None
    put("award_number", num)
    put("project_title", _labelled(text, r"project title|title of (?:the )?project|title"))
    put("principal_investigator", _labelled(text, r"(?:program director/)?principal investigator|PI|PD/PI|grantee contact"))
    put("project_period", _labelled(text, r"project period|period of performance|award period|grant period|budget period"))
    m = re.search(r"(?i)(total|amount|award(?:ed)?|approved|budget)[^\n$]{0,60}(\$\s?[\d,]+(?:\.\d{2})?)", text)
    if m:
        put("amount", (m.group(2).replace(" ", ""), _sentence(text, m.start(), m.end())))
    countries = []
    for c in COUNTRIES:
        m = re.search(rf"\b{re.escape(c)}\b", text)
        if m:
            countries.append({"value": c, "quote": _sentence(text, m.start(), m.end())})
    facts["countries"] = countries
    partners = []
    for n in partner_names:
        i = low.find(n.lower())
        if i != -1 and len(n) > 6:
            partners.append({"value": n, "quote": _sentence(text, i, i + len(n))})
    facts["partner_institutions"] = partners
    return facts


def ai_read(text: str) -> dict | None:
    """The agent's reading, keeping only facts whose quote really is in the letter."""
    if not (llm.ai_available() and llm.within_budget()):
        return None
    from pydantic_ai import Agent
    t0 = time.perf_counter()
    try:
        r = Agent(llm.model(), instructions=AI_RULES, output_type=AILetter, defer_model_check=True).run_sync(
            text[:12000], usage_limits=llm.limits("one_pager"))
        llm.record("award_letter", r.usage, latency_s=time.perf_counter() - t0)
    except Exception as e:  # no model, bad key, timeout: the rules take over
        llm.record("award_letter", None, latency_s=time.perf_counter() - t0, status="error", error=str(e))
        return None
    flat = " ".join(text.split()).lower()
    ok = lambda f: f and f.value.strip() and " ".join(f.quote.split()).lower().strip(" .…") in flat
    out = {k: {"value": getattr(r.output, k).value, "quote": getattr(r.output, k).quote}
           for k in ("funder", "award_number", "project_title", "principal_investigator", "project_period", "amount") if ok(getattr(r.output, k))}
    out["countries"] = [{"value": f.value, "quote": f.quote} for f in r.output.countries if ok(f)]
    out["partner_institutions"] = [{"value": f.value, "quote": f.quote} for f in r.output.partner_institutions if ok(f)]
    out["summary"] = r.output.summary.strip()
    return out


def needs(text: str, topics: list[dict], facts: dict) -> list[dict]:
    by_slug = {t["slug"]: t for t in topics}
    out = []
    for slug, title, pattern in NEEDS:
        m = re.search(pattern, text, re.I)
        why = _sentence(text, m.start(), m.end()) if m else None
        # a partner institution named abroad means money will likely go to them: flag a subaward even without the word
        if not why and slug == "subcontracts-and-subawards" and facts.get("partner_institutions"):
            why = f"Your letter names {facts['partner_institutions'][0]['value']} as part of the work."
        if why and slug in by_slug:
            t = by_slug[slug]
            o = t.get("office") or {}
            out.append({"slug": slug, "title": title, "quote": why, "guide": {"title": t["title"], "path": f"/hub/{t['section']}/{slug}"},
                        "office": {"name": o.get("name"), "email": o.get("email"), "url": o.get("url")}})
    if facts.get("countries"):   # any work abroad: research security and in-country operations are worth a look
        for slug, title in (("research-security", "Research security review for foreign collaboration"),
                            ("in-country-operations", "Running operations in another country")):
            if slug in by_slug and slug not in {n["slug"] for n in out}:
                t = by_slug[slug]; o = t.get("office") or {}
                out.append({"slug": slug, "title": title, "quote": f"Your letter mentions work in {', '.join(c['value'] for c in facts['countries'][:3])}.",
                            "guide": {"title": t["title"], "path": f"/hub/{t['section']}/{slug}"},
                            "office": {"name": o.get("name"), "email": o.get("email"), "url": o.get("url")}})
    return out


def analyze(text: str, topics: list[dict], partner_names: list[str]) -> dict:
    rules = rules_read(text, partner_names)
    ai = ai_read(text)
    facts = rules if ai is None else {**rules, **{k: v for k, v in ai.items() if v}}
    if ai is not None:   # keep partners the rules matched to known organizations as well
        seen = {p["value"].lower() for p in facts.get("partner_institutions", [])}
        facts["partner_institutions"] = facts.get("partner_institutions", []) + [p for p in rules["partner_institutions"] if p["value"].lower() not in seen]
    # text used to match people, partners and resources: the substance, not the standard terms and conditions
    focus = " ".join(filter(None, [facts.get("project_title", {}).get("value"), facts.get("summary"),
                                   " ".join(c["value"] for c in facts.get("countries", [])),
                                   " ".join(p["value"] for p in facts.get("partner_institutions", [])), text[:1500]]))
    return {"facts": facts, "needs": needs(text, topics, facts), "match_text": focus[:4000], "method": "ai" if ai is not None else "rules"}
