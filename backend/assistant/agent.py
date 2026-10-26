"""YIGH Nexus assistant: a chat agent that can look up anything on the website.

Its tools call the site's own API (in-process), so it sees exactly what a visitor sees: funding opportunities,
funder timing, the faculty directory and profiles, collaborator suggestions, suggested teams and partners,
partner institutions, and YIGH's strategic plan and news. Drafting a Launchpad concept is only offered to
signed-in users, like on the site.

With an Anthropic API key it runs as a PydanticAI agent (Claude chooses which tools to call). Without one it
falls back to a simple keyword router over the same tools, so it still answers common questions.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import date

from pydantic_ai import Agent, RunContext

from backend.nexus.agent import DEFAULT_MODEL
from backend.nexus.service import ai_available

SITE_PAGES = {"home": "/", "opportunities": "/radar", "directory": "/directory", "sign_in": "/signin"}

INSTRUCTIONS = f"""You are Nexi, the cheerful front-desk assistant on the Yale Institute for Global Health website. Today is {date.today():%B %-d, %Y}.
Help people find funding opportunities, Yale faculty, possible collaborators and teams, partner institutions, and information about YIGH.

Personality: warm, upbeat and helpful, like a friendly desk assistant who loves pointing people to the right place.
Open with a short, friendly line ("Happy to help!", "Ooh, good question!"), keep the energy light, and end with a helpful nudge
or offer ("Want me to look for collaborators too?"). At most one exclamation mark per sentence and no more than one emoji per reply.
Stay chirpy even when you can't find something, but be honest about it.

How to answer:
- Always look things up with your tools before answering; never answer from memory about opportunities, faculty, funders or dates.
- Never invent amounts, deadlines, eligibility, people, or partnerships. If a tool doesn't show it, say you couldn't find it.
- Never say a faculty member or organization is interested, available, eligible or has agreed to anything. Suggestions are suggestions.
- Keep answers short and friendly, in plain language. Avoid jargon such as "documented", "rule-based" or "evidence facets".
- Link to pages on the site with markdown links using paths like /radar/12, /faculty/34, /directory?priority=climate-health, /radar?funder=gates.
- Remind people to confirm details on the funder's own page before applying.
- If someone wants a concept draft (Launchpad) and isn't signed in, tell them to sign in at /signin.

How to search well (be resourceful; never give up after one empty search):
- Break a question into parts: topic, place, YIGH priority, school. Use the right filter for each part instead of
  stuffing the whole sentence into `query`. Call directory_options to see valid place names, research areas and priorities.
- Priorities map to slugs: climate-health, digital-health-ai, health-diplomacy-security, health-sovereignty.
- If a combined search is empty, relax it step by step (e.g. place only, then priority only, then a nearby region such as
  "East Africa" or "Africa") and say which parts matched: "Nobody is tagged with both, but these 5 work in Kenya and
  these 4 work on climate and health in East Africa."
- Run several searches in parallel when useful, and combine and rank the results yourself.
- For "who could I collaborate with", suggest 3-6 specific people with one line each on why, and offer next steps
  (their profile, suggested collaborators, partner institutions in that country, related funding).
- Use the conversation history: follow-ups like "I mean faculty who work in that domain" refer to the earlier topic.
"""


@dataclass
class Deps:
    cookie: str | None = None
    signed_in: bool = False
    links: list[dict] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)


def _client():
    from fastapi.testclient import TestClient
    from backend.app.main import app
    return TestClient(app)


def call_api(deps: Deps, path: str, params: dict | None = None, method: str = "GET"):
    """Call the site's own API. Runs on a fresh thread (no inherited agent-run context), so endpoints that start
    their own agent run, such as team matching, work when Nexi calls them as a tool."""
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(_call_api, deps, path, params, method).result()


def _call_api(deps: Deps, path: str, params: dict | None = None, method: str = "GET"):
    deps.tools_used.append(path.split("?")[0])
    c = _client()
    if deps.cookie:
        c.cookies.set("yigh_session", deps.cookie)
    r = c.request(method, path, params={k: v for k, v in (params or {}).items() if v not in (None, "")})
    if r.status_code >= 400:
        try:
            return {"error": r.json().get("detail", r.text)}
        except ValueError:
            return {"error": r.text}
    return r.json()


def _trim_opp(o: dict) -> dict:
    return {k: o.get(k) for k in ("id", "title", "funder", "status", "deadline", "deadline_text", "days_left", "award_text", "official_url")} | \
           {"priorities": [p["name"] for p in o.get("priorities", [])], "page": f"/radar/{o.get('id')}"}


def _trim_fac(f: dict) -> dict:
    return {"id": f["id"], "name": f["name"], "title": f.get("title"), "school": f.get("school"), "department": f.get("department"),
            "priorities": [p["name"] for p in f.get("priorities", [])], "research_areas": f.get("keywords", [])[:6],
            "places": f.get("regions", [])[:6], "page": f"/faculty/{f['id']}"}


# ------------------------------------------------------------------ tools (shared by the AI agent and the fallback)
def t_search_opportunities(deps: Deps, query: str = "", priority: str = "", funder: str = "", status: str = "open",
                           geo: str = "", closing_within_days: int = 0) -> dict:
    deadline_before = (date.fromordinal(date.today().toordinal() + closing_within_days).isoformat() if closing_within_days else None)
    d = call_api(deps, "/api/radar/opportunities", {"q": query, "priority": priority, "funder": funder,
                                                    "status": None if status == "all" else status, "geo": geo,
                                                    "deadline_before": deadline_before, "limit": 50})
    if "error" in d:
        return d
    return {"count": d["count"], "opportunities": [_trim_opp(o) for o in d["opportunities"][:10]]}


def t_get_opportunity(deps: Deps, opportunity_id: int) -> dict:
    d = call_api(deps, f"/api/radar/opportunities/{opportunity_id}")
    if "error" in d:
        return d
    keep = ("id", "title", "funder", "status", "deadline", "deadline_text", "award_text", "eligibility", "geographic_restrictions",
            "official_url", "application_url", "posted_date")
    return {k: d.get(k) for k in keep} | {"description": (d.get("description") or "")[:1500],
                                          "priorities": [p["name"] for p in d.get("priorities", [])], "page": f"/radar/{opportunity_id}"}


def t_list_funders(deps: Deps) -> list:
    return call_api(deps, "/api/radar/funders")


def t_funder_timing(deps: Deps, funder_slug: str) -> dict:
    return call_api(deps, f"/api/radar/funders/{funder_slug}/timing")


def t_search_faculty(deps: Deps, query: str = "", priority: str = "", school: str = "", region: str = "") -> dict:
    d = call_api(deps, "/api/faculty", {"q": query, "priority": priority, "school": school, "region": region})
    if isinstance(d, dict) and "error" in d:
        return d
    return {"count": len(d), "faculty": [_trim_fac(f) for f in d[:12]]}


def t_directory_options(deps: Deps) -> dict:
    d = call_api(deps, "/api/filters")
    pick = lambda xs, n: [f"{x['label']} ({x['count']})" for x in xs[:n]]
    return {"places": pick(d.get("regions", []), 120), "research_areas": pick(d.get("keywords", []), 80),
            "schools": pick(d.get("schools", []), 20), "priorities": [f"{x['value']}: {x['label']} ({x['count']})" for x in d.get("priorities", [])]}


def t_get_faculty(deps: Deps, faculty_id: int) -> dict:
    d = call_api(deps, f"/api/faculty/{faculty_id}")
    if "error" in d:
        return d
    return _trim_fac(d) | {"bio": (d.get("bio") or "")[:1500], "profile_url": d.get("profile_url"), "email": d.get("email")}


def t_find_collaborators(deps: Deps, faculty_id: int) -> dict:
    d = call_api(deps, f"/api/faculty/{faculty_id}/collaborators", {"limit": 6})
    if "error" in d:
        return d
    return {"for": d.get("faculty", {}).get("name"), "suggestions": [
        {"name": m["faculty"]["name"], "page": f"/faculty/{m['faculty']['id']}", "why": [r["text"] for r in m.get("reasons", [])][:3]}
        for m in d.get("matches", [])]}


def t_team_for_opportunity(deps: Deps, opportunity_id: int) -> dict:
    d = call_api(deps, f"/api/radar/opportunities/{opportunity_id}/workspace")
    if "error" in d:
        return d
    return {"opportunity": d["opportunity"]["title"], "page": f"/radar/{opportunity_id}",
            "suggested_faculty": [{"name": f["name"], "page": f"/faculty/{f['faculty_id']}", "why": f["explanation"]["text"]}
                                  for f in d["recommended_faculty"][:5]],
            "teams": [{"name": t["name"], "members": [f"{m['name']} ({m['proposed_role']['text']})" for m in t["members"]]}
                      for t in d["teams"][:3]],
            "partners": [{"name": p["name"], "country": p["country"],
                          "connected_to_yale": p["relationship"]["status"] == "documented"}
                         for t in d["external_partners"]["teams"][:1] for p in t["partners"][:5]],
            "things_to_check": d["eligibility_and_collaboration_gaps"][:6]}


def t_search_partners(deps: Deps, country: str = "", query: str = "") -> dict:
    d = call_api(deps, "/api/partners", {"country": country, "q": query})
    if "error" in d:
        return d
    return {"count": len(d.get("partners", [])), "partners": [{k: p.get(k) for k in ("name", "country", "type", "website")}
                                                             for p in d.get("partners", [])[:12]]}


def t_about_yigh(deps: Deps) -> dict:
    d = call_api(deps, "/api/home")
    p = d.get("profile", {})
    return {"mission": p.get("mission"), "vision": p.get("vision"), "history": p.get("history"),
            "values": [v["name"] for v in p.get("values", [])],
            "priorities": [{"name": x["name"], "summary": x["summary"], "faculty_page": f"/directory?priority={x['slug']}",
                            "funding_page": f"/radar?priority={x['slug']}"} for x in p.get("priorities", [])],
            "pillars": [x["name"] + ": " + x["text"] for x in p.get("pillars", [])],
            "contact": p.get("contact"), "newsletter": p.get("newsletter_url"),
            "latest_news": [{"title": n["title"], "url": n["url"], "date": n.get("date")} for n in d.get("news", [])]}


def t_draft_concept(deps: Deps, opportunity_id: int, team_name: str = "") -> dict:
    if not deps.signed_in:
        return {"error": "Not signed in. Drafting a concept needs a Yale sign-in at /signin."}
    d = call_api(deps, f"/api/nexus/opportunities/{opportunity_id}/concept", {"team": team_name}, method="POST")
    return d if "error" in d else {"label": d["label"], "concept": d["concept"], "page": f"/radar/{opportunity_id}#launchpad"}


TOOLS = [t_directory_options, t_search_opportunities, t_get_opportunity, t_list_funders, t_funder_timing, t_search_faculty, t_get_faculty,
         t_find_collaborators, t_team_for_opportunity, t_search_partners, t_about_yigh, t_draft_concept]

PRIORITY_SLUGS = {"climate": "climate-health", "digital": "digital-health-ai", " ai ": "digital-health-ai",
                  "diplomacy": "health-diplomacy-security", "security": "health-diplomacy-security",
                  "sovereignty": "health-sovereignty"}


def build_agent(model=None) -> Agent:
    from backend import llm
    agent = Agent(model or llm.model(), deps_type=Deps, instructions=INSTRUCTIONS,
                  defer_model_check=True)

    @agent.tool
    def search_opportunities(ctx: RunContext[Deps], query: str = "", priority: str = "", funder: str = "", status: str = "open",
                             geo: str = "", closing_within_days: int = 0) -> dict:
        """Search funding opportunities. priority: climate-health | digital-health-ai | health-diplomacy-security | health-sovereignty.
        funder: a funder slug from list_funders. status: open | forecasted | closed | all. geo: foreign_eligible | lmic_lead | us_only."""
        return t_search_opportunities(ctx.deps, query, priority, funder, status, geo, closing_within_days)

    @agent.tool
    def get_opportunity(ctx: RunContext[Deps], opportunity_id: int) -> dict:
        """Full details of one opportunity: description, eligibility, deadline, award and links."""
        return t_get_opportunity(ctx.deps, opportunity_id)

    @agent.tool
    def list_funders(ctx: RunContext[Deps]) -> list:
        """All funders the site tracks, with slugs and how many opportunities each has."""
        return t_list_funders(ctx.deps)

    @agent.tool
    def funder_timing(ctx: RunContext[Deps], funder_slug: str) -> dict:
        """When a funder last opened a call, its most recent close, what's open now and anything forecasted."""
        return t_funder_timing(ctx.deps, funder_slug)

    @agent.tool
    def search_faculty(ctx: RunContext[Deps], query: str = "", priority: str = "", school: str = "", region: str = "") -> dict:
        """Search the Yale faculty directory by name, topic or place, YIGH priority slug, school or region."""
        return t_search_faculty(ctx.deps, query, priority, school, region)

    @agent.tool
    def directory_options(ctx: RunContext[Deps]) -> dict:
        """Valid filter values for the faculty directory: places (regions and countries), research areas, schools and priorities, with counts."""
        return t_directory_options(ctx.deps)

    @agent.tool
    def get_faculty(ctx: RunContext[Deps], faculty_id: int) -> dict:
        """One faculty member's profile: title, school, research areas, places and bio."""
        return t_get_faculty(ctx.deps, faculty_id)

    @agent.tool
    def find_collaborators(ctx: RunContext[Deps], faculty_id: int) -> dict:
        """Suggested Yale collaborators for a faculty member, with reasons."""
        return t_find_collaborators(ctx.deps, faculty_id)

    @agent.tool
    def team_for_opportunity(ctx: RunContext[Deps], opportunity_id: int) -> dict:
        """Suggested Yale faculty, team options and partner institutions for an opportunity, plus things to check."""
        return t_team_for_opportunity(ctx.deps, opportunity_id)

    @agent.tool
    def search_partners(ctx: RunContext[Deps], country: str = "", query: str = "") -> dict:
        """Partner institutions YIGH or Yale faculty work with, by country or name."""
        return t_search_partners(ctx.deps, country, query)

    @agent.tool
    def about_yigh(ctx: RunContext[Deps]) -> dict:
        """YIGH's mission, vision, values, four strategic priorities, pillars, contact details and latest news."""
        return t_about_yigh(ctx.deps)

    @agent.tool
    def draft_concept(ctx: RunContext[Deps], opportunity_id: int, team_name: str = "") -> dict:
        """Launchpad: a one-page concept outline for a suggested team. Only works for signed-in users."""
        return t_draft_concept(ctx.deps, opportunity_id, team_name)

    return agent


# ------------------------------------------------------------------ fallback when no AI key is configured
def _opp_lines(opps: list[dict]) -> str:
    out = []
    for o in opps[:6]:
        when = f"deadline {o['deadline']}" if o.get("deadline") else (o.get("deadline_text") or "no deadline listed")
        out.append(f"- [{o['title']}]({o['page']}) — {o.get('funder') or 'funder not listed'}, {when}")
    return "\n".join(out)


def _match_funder(deps: Deps, text: str) -> dict | None:
    t = text.lower()
    best = None
    funders = t_list_funders(deps)
    for f in funders if isinstance(funders, list) else []:
        label = f["label"].lower()
        short = re.sub(r"\b(the|foundation|fund|institute|of|for|and|&)\b", " ", label).split()
        initials = "".join(w[0] for w in re.findall(r"[a-z]+", re.sub(r"\(.*?\)|-.*$", "", label)) if w not in ("of", "and", "for", "the"))
        if label in t or f["value"].replace("-", " ") in t or (short and all(w in t for w in short[:2])) or \
                (len(initials) >= 3 and re.search(rf"\b{initials}\b", t)):
            if not best or len(f["label"]) > len(best["label"]):
                best = f
    return best


def _find_person(deps: Deps, name: str) -> list[dict]:
    hits = t_search_faculty(deps, name).get("faculty", [])
    words = name.split()
    if not hits and len(words) >= 2:
        hits = [f for f in t_search_faculty(deps, words[-1]).get("faculty", []) if words[0].lower() in f["name"].lower()]
    return hits


def fallback_reply(deps: Deps, message: str) -> str:
    t = f" {message.lower()} "
    prio = next((v for k, v in PRIORITY_SLUGS.items() if k in t), "")
    funder = _match_funder(deps, message)

    if funder and re.search(r"\b(when|open|opening|last|next|again|round|cycle)\b", t):
        d = t_funder_timing(deps, funder["value"])
        parts = [f"Let me check the calendar for you! 📅 **{d['funder']['name']}**: {d['headline']}"]
        if d.get("last_opened"):
            parts.append(f"Last opened: [{d['last_opened']['title']}](/radar/{d['last_opened']['id']}), posted {d['last_opened']['posted_date']}.")
        elif d.get("first_recorded"):
            parts.append(f"Most recent call on record: [{d['first_recorded']['title']}](/radar/{d['first_recorded']['id']}) (this funder doesn't publish posting dates).")
        if d.get("last_closed"):
            parts.append(f"Most recent close: {d['last_closed']['title']} on {d['last_closed']['deadline']}.")
        if d.get("forecasted"):
            parts.append("Forecasted next:\n" + _opp_lines([_trim_opp(o) | {"page": f"/radar/{o['id']}"} for o in d["forecasted"]]))
        parts.append(f"You can see everything from them [right here](/radar?funder={funder['value']}). Want me to find Yale faculty for one of these?")
        return "\n\n".join(parts)

    m = re.search(r"collaborat\w* (?:with|for) ([a-z .'-]+)", t)
    if m:
        hits = _find_person(deps, m.group(1).strip())
        if not hits:
            return f"Hmm, I couldn't find anyone called “{m.group(1).strip()}” in the directory. Could you check the spelling for me?"
        d = t_find_collaborators(deps, hits[0]["id"])
        lines = [f"- [{s['name']}]({s['page']}): {s['why'][0] if s['why'] else ''}" for s in d.get("suggestions", [])]
        return (f"Great idea! Here are some people who could team up with **{hits[0]['name']}**:\n\n" + "\n".join(lines or ["I didn't find a good match this time."]) +
                "\n\nThese are just suggestions, and nobody has been contacted yet.")

    if re.search(r"\b(team|who could apply|who should apply|build a team)\b", t):
        found = t_search_opportunities(deps, _keywords(t), prio, funder["value"] if funder else "", "all")
        if found.get("opportunities"):
            o = found["opportunities"][0]
            d = t_team_for_opportunity(deps, o["id"])
            ppl = "\n".join(f"- [{f['name']}]({f['page']})" for f in d["suggested_faculty"])
            return (f"Ooh, let's build a team! For **[{o['title']}]({o['page']})**, these Yale faculty look like a great fit:\n\n{ppl}\n\n"
                    f"You'll find team ideas and partner organizations on the [opportunity page]({o['page']}#team), or head to the "
                    f"[Team Launchpad](/launchpad?opp={o['id']}) to draft a one-pager. Just suggestions for now; nobody has been contacted.")

    if re.search(r"\b(who|faculty|professor|researcher|expert|works? on|working on|scientist)\b", t):
        q = _keywords(t)
        d = t_search_faculty(deps, q, prio)
        if not d.get("faculty"):
            return f"Hmm, nobody popped up for “{q}”. The [Faculty Directory](/directory) might help you browse!"
        lines = [f"- [{f['name']}]({f['page']}) — {f.get('school') or ''}{', ' + ', '.join(f['research_areas'][:3]) if f['research_areas'] else ''}" for f in d["faculty"][:8]]
        more = f"\n\n[See all {d['count']} in the directory](/directory?q={q.replace(' ', '+')})" if d["count"] > 8 else ""
        return f"Happy to help! Faculty matching “{q or 'your search'}”:\n\n" + "\n".join(lines) + more + "\n\nWant me to suggest collaborators for any of them?"

    if re.search(r"\b(partner|institution|organi[sz]ation)s?\b", t):
        country = next((w.strip().title() for w in re.findall(r"in ([a-z ]+)", t)), "")
        d = t_search_partners(deps, country.strip())
        lines = [f"- {p['name']} ({p['country']})" for p in d.get("partners", [])]
        return ("Here are partner institutions" + (f" in {country}" if country else "") + " 🌍\n\n" + "\n".join(lines)) if lines else \
            "Hmm, I couldn't find partner institutions for that. Try another country?"

    if re.search(r"\b(grant|fund|funding|opportunit|call|rfa|award|deadline|closing)\w*", t) or prio or funder:
        within = 30 if re.search(r"closing soon|this month|next month|30 days", t) else 0
        d = t_search_opportunities(deps, _keywords(t), prio, funder["value"] if funder else "", "open", closing_within_days=within)
        if not d.get("opportunities"):
            d = t_search_opportunities(deps, "", prio, funder["value"] if funder else "", "open", closing_within_days=within)
        if not d.get("opportunities"):
            return "No open calls matched that just now. You can browse everything on the [Opportunities page](/radar)!"
        return (f"Good news! I found {d['count']} open opportunit{'y' if d['count'] == 1 else 'ies'}:\n\n" + _opp_lines(d["opportunities"]) +
                "\n\nDo double-check the details on the funder's own page before applying. Want me to find a team for one of these?")

    if re.search(r"\b(yigh|mission|vision|priorit|pillar|value|about|news|contact|strategic)\w*", t):
        d = t_about_yigh(deps)
        if "news" in t:
            return "Here's the latest from YIGH 📰\n\n" + "\n".join(f"- [{n['title']}]({n['url']})" for n in d["latest_news"])
        pr = "\n".join(f"- **{p['name']}**: {p['summary']} ([faculty]({p['faculty_page']}), [funding]({p['funding_page']}))" for p in d["priorities"])
        return f"Happy to tell you about us! **Our mission:** {(d['mission'] or {}).get('text') if isinstance(d['mission'], dict) else d['mission']}\n\n**YIGH's four strategic priorities:**\n\n{pr}"

    return ("Hi there, I'm Nexi, your YIGH desk assistant! 👋 I can find funding opportunities, Yale faculty, collaborators, "
            "teams for a call, partner institutions, or tell you about YIGH. Try “open grants on climate and health”, "
            "“who works on malaria?”, or “when does the Gates Foundation open again?”")


STOP = set("a an the i im i'm me my we our you your is are was be to of in on for with and or any some show find list what which who whom "
           "please can could would there about that this those these do does get give need want looking look open grants grant funding "
           "fund opportunities opportunity calls call faculty professor professors researchers researcher experts expert works work working "
           "on at yale yigh soon closing new current currently how many when does team build apply should could".split())


def _keywords(t: str) -> str:
    return " ".join(w for w in re.findall(r"[a-z][a-z-]+", t) if w not in STOP and w not in ("climate", "health", "digital", "ai", "sovereignty", "diplomacy", "security"))[:80]


BLOCKED_REPLY = ("Sorry, I can't help with that one! I can't share system settings, keys or account details, and I can't say "
                 "that anyone has agreed to collaborate. I'm happy to help you find funding, Yale faculty, collaborators or "
                 "partner institutions, though. What are you working on?")


def chat(messages: list[dict], cookie: str | None, signed_in: bool, model=None) -> dict:
    deps = Deps(cookie=cookie, signed_in=signed_in)
    last = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    if model is not None or ai_available():
        from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart
        history = []
        for m in messages[:-1][-12:]:
            history.append(ModelRequest(parts=[UserPromptPart(content=m["content"])]) if m["role"] == "user"
                           else ModelResponse(parts=[TextPart(content=m["content"])]))
        try:
            from backend import llm
            import time as _t
            t0 = _t.perf_counter()
            r = build_agent(model).run_sync(last, deps=deps, message_history=history, usage_limits=llm.limits("assistant"))
            row = llm.record("assistant", r.usage, latency_s=_t.perf_counter() - t0)
            return {"reply": r.output, "mode": "ai", "tools_used": deps.tools_used, "usage": row}
        except Exception as e:  # noqa: BLE001 — fall back rather than fail the chat
            from backend import llm
            llm.record("assistant", None, latency_s=0, status="error", error=f"{type(e).__name__}: {e}")
            if re.search(r"filtered|content[_ ]?filter|jailbreak|content management policy", str(e), re.I):
                return {"reply": BLOCKED_REPLY, "mode": "blocked", "tools_used": deps.tools_used,
                        "note": "The model provider's safety filter blocked this request."}
            reply = fallback_reply(deps, last)
            return {"reply": reply, "mode": "basic", "tools_used": deps.tools_used, "note": f"AI unavailable ({type(e).__name__}); used basic search."}
    return {"reply": fallback_reply(deps, last), "mode": "basic", "tools_used": deps.tools_used}
