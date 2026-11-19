"""GRAPPH hub: step-by-step pathways, the Facilities & Resources builder, and letter-of-support requests.

Pathway content lives in config/grapph/ and is summarized from public Yale office pages (each topic lists its sources).
Letter requests are saved in data/hub.db for YIGH staff; nothing is emailed.
"""
from __future__ import annotations

import json
import os
import time
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from backend import llm
from backend.auth.api import current_user

REPO = Path(__file__).resolve().parents[2]
CONFIG = REPO / "config" / "grapph"
DB_PATH = Path(os.environ.get("HUB_DB", REPO / "data" / "hub.db"))

router = APIRouter(prefix="/api/hub", tags=["GRAPPH hub"])


def _load(name: str):
    return json.loads((CONFIG / name).read_text())


def _topic_card(t: dict) -> dict:
    return {k: t.get(k) for k in ("section", "slug", "title", "summary")}


# ------------------------------------------------------------------ pathways
@router.get("/sections")
def sections():
    """The six lifecycle stages with their topic lists."""
    topics = _load("topics.json")
    return [{**s, "topics": [_topic_card(t) for t in topics if t["section"] == s["slug"]]} for s in _load("sections.json")]


@router.get("/topics/{section}/{slug}")
def topic(section: str, slug: str):
    topics = _load("topics.json")
    # match on slug alone so links from before the six-stage reorganization (e.g. /hub/comply/...) still work
    t = next((t for t in topics if t["slug"] == slug), None)
    if not t:
        raise HTTPException(404, "That page doesn't exist.")
    section = t["section"]
    by_slug = {x["slug"]: x for x in topics}
    related = [_topic_card(by_slug[r]) for r in t.get("related", []) if r in by_slug and r != slug]
    sec = next(s for s in _load("sections.json") if s["slug"] == section)
    return {**t, "related": related, "section_info": sec,
            "siblings": [_topic_card(x) for x in topics if x["section"] == section]}


@router.get("/search")
def search(q: str = ""):
    """Keyword search across pathway pages, tools and templates (used by the hub search box and Nexi)."""
    words = [w for w in q.lower().split() if len(w) > 2]
    if not words:
        return []
    out = []
    for t in _load("topics.json"):
        hay = json.dumps(t).lower()
        score = sum(hay.count(w) for w in words) + 5 * sum(w in t["title"].lower() for w in words)
        if score:
            out.append((score, {**_topic_card(t), "kind": "pathway", "path": f"/hub/{t['section']}/{t['slug']}"}))
    tools = [("Facilities & Resources builder", "/launchpad/facilities", "facilities resources grant section boilerplate equipment computing"),
             ("Letters of support", "/launchpad/letters", "letter support commitment template request"),
             ("Templates and checklists", "/launchpad/letters#templates", "template checklist")]
    for title, path, kw in tools:
        score = sum((title + " " + kw).lower().count(w) for w in words)
        if score:
            out.append((score + 3, {"title": title, "summary": "Tool", "kind": "tool", "path": path}))
    return [o for _, o in sorted(out, key=lambda x: -x[0])[:12]]


@router.get("/offices")
def offices():
    """Yale offices named in the guides, each with the guides it owns (for Expertise & Support)."""
    out: dict[str, dict] = {}
    for t in _load("topics.json"):
        o = t.get("office") or {}
        if not o.get("name"):
            continue
        e = out.setdefault(o["name"], {**o, "topics": []})
        e["topics"].append(_topic_card(t))
    return sorted(out.values(), key=lambda o: o["name"])


# ------------------------------------------------------------------ Facilities & Resources builder
@router.get("/facilities")
def facilities():
    return _load("facilities.json")


class FacilitiesIn(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=40)
    project: str = Field(default="", max_length=300)
    site_text: str = Field(default="", max_length=3000)   # the user's own description of partner-site facilities
    polish: bool = False


CATEGORY_TITLES = {"institutes": "Institutional Environment", "computing": "Computing", "data": "Data and Library Resources",
                   "labs": "Laboratories and Core Facilities", "support": "Research Support"}


def assemble(items: list[dict], project: str, site_text: str) -> str:
    """Plain assembly: no AI. Every sentence comes from the resource descriptions or the user's own text."""
    parts = ["FACILITIES AND OTHER RESOURCES"]
    if project.strip():
        parts.append(f"The following Yale University resources are available to support \"{project.strip()}\".")
    for cat, title in CATEGORY_TITLES.items():
        group = [i for i in items if i["category"] == cat]
        if group:
            parts.append(title.upper())
            parts += [f"{i['name']}. {i['text']}" for i in group]
    if site_text.strip():
        parts += ["PARTNER SITE(S)", site_text.strip()]
    return "\n\n".join(parts)


POLISH_RULES = """You edit a grant 'Facilities and Other Resources' section. Rewrite the draft so it reads as one coherent, formal section
with smooth transitions and the same headings. STRICT RULES: do not add any facility, number, equipment, service, capability or claim that
is not in the draft; do not remove facts; do not promise access or commitments; keep third person; plain text only, no markdown."""


@router.post("/facilities/draft")
def facilities_draft(body: FacilitiesIn):
    by_id = {f["id"]: f for f in _load("facilities.json")}
    items = [by_id[i] for i in body.ids if i in by_id]
    if not items:
        raise HTTPException(422, "Pick at least one resource.")
    text = assemble(items, body.project, body.site_text)
    sources = [{"name": i["name"], "url": i["url"]} for i in items]
    if not (body.polish and llm.ai_available() and llm.within_budget()):
        return {"text": text, "mode": "assembled", "sources": sources}
    from pydantic_ai import Agent
    t0 = time.perf_counter()
    try:
        r = Agent(llm.model(), instructions=POLISH_RULES, defer_model_check=True).run_sync(text, usage_limits=llm.limits("one_pager"))
        llm.record("facilities", r.usage, latency_s=time.perf_counter() - t0)
        return {"text": r.output.strip(), "mode": "ai", "sources": sources}
    except Exception as e:  # fall back to the plain version rather than failing
        llm.record("facilities", None, latency_s=time.perf_counter() - t0, status="error", error=str(e))
        return {"text": text, "mode": "assembled", "sources": sources, "note": "The AI editor wasn't available, so this is the plain version."}


# ------------------------------------------------------------------ letters of support, templates, checklists
@router.get("/templates")
def templates():
    return _load("templates.json")


class Base(DeclarativeBase):
    pass


class LetterRequest(Base):
    __tablename__ = "letter_requests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer)
    user_email: Mapped[str] = mapped_column(String(254))
    user_name: Mapped[str] = mapped_column(String(200))
    signer: Mapped[str] = mapped_column(String(200))
    project_title: Mapped[str] = mapped_column(String(300))
    funder: Mapped[str] = mapped_column(String(300))
    deadline: Mapped[str] = mapped_column(String(10))
    summary: Mapped[str] = mapped_column(Text)
    confirm: Mapped[str] = mapped_column(Text)
    opportunity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="submitted")
    created_at: Mapped[datetime] = mapped_column(DateTime)


_Session = None


def hub_db():
    global _Session
    if _Session is None or str(_Session.kw["bind"].url.database) != str(DB_PATH):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        _Session = sessionmaker(bind=engine, expire_on_commit=False)
    return _Session()


class LetterIn(BaseModel):
    signer: str = Field(min_length=2, max_length=200)
    project_title: str = Field(min_length=3, max_length=300)
    funder: str = Field(min_length=2, max_length=300)
    deadline: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    summary: str = Field(min_length=20, max_length=3000)
    confirm: str = Field(default="", max_length=2000)
    opportunity_id: int | None = None


def _letter(r: LetterRequest) -> dict:
    return {k: getattr(r, k) for k in ("id", "signer", "project_title", "funder", "deadline", "summary", "confirm",
                                         "opportunity_id", "status")} | {"created_at": r.created_at.isoformat()}


@router.post("/letters")
def request_letter(body: LetterIn, user: dict = Depends(current_user)):
    try:
        due = date.fromisoformat(body.deadline)
    except ValueError:
        raise HTTPException(422, "Enter a real date.")
    if due < date.today():
        raise HTTPException(422, "That deadline has already passed.")
    with hub_db() as db:
        r = LetterRequest(user_id=user["id"], user_email=user["email"], user_name=user["name"],
                          **body.model_dump(), created_at=datetime.now(timezone.utc).replace(tzinfo=None))
        db.add(r)
        db.commit()
        out = _letter(r)
    days = (due - date.today()).days
    out["warning"] = (f"The deadline is in {days} day{'s' if days != 1 else ''}. Letters usually need two to three weeks, "
                      "so reach out to the signer directly as well.") if days < 14 else None
    return out


@router.get("/letters")
def my_letters(user: dict = Depends(current_user)):
    with hub_db() as db:
        rows = db.scalars(select(LetterRequest).filter_by(user_id=user["id"]).order_by(LetterRequest.created_at.desc())).all()
        return [_letter(r) for r in rows]


# ------------------------------------------------------------------ feedback
class Feedback(Base):
    __tablename__ = "feedback"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    page: Mapped[str] = mapped_column(String(300))
    page_title: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(40))
    message: Mapped[str] = mapped_column(Text)
    email: Mapped[str] = mapped_column(String(254))
    created_at: Mapped[datetime] = mapped_column(DateTime)


FEEDBACK_KINDS = {"incorrect", "missing", "confusing", "suggestion", "other"}


class FeedbackIn(BaseModel):
    page: str = Field(max_length=300)
    page_title: str = Field(default="", max_length=300)
    kind: str
    message: str = Field(default="", max_length=3000)
    email: str = Field(default="", max_length=254)


@router.post("/feedback")
def feedback(body: FeedbackIn):
    """Saved in data/hub.db for YIGH staff to review. No account needed; email is optional."""
    if body.kind not in FEEDBACK_KINDS:
        raise HTTPException(422, "Pick what kind of feedback this is.")
    if body.kind != "suggestion" and len(body.message.strip()) < 3 and body.kind == "other":
        raise HTTPException(422, "Tell us a little more.")
    if body.email and "@" not in body.email:
        raise HTTPException(422, "That email doesn't look right.")
    with hub_db() as db:
        db.add(Feedback(**body.model_dump(), created_at=datetime.now(timezone.utc).replace(tzinfo=None)))
        db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ Launchpad plan: stage + project → matches and Yale steps
# Which pathway stages matter at each project stage, in order.
STAGES = {
    "idea": {"label": "Exploring an idea", "sections": ["partner", "fund"]},
    "applying": {"label": "Applying for a grant", "sections": ["fund", "submit", "partner"]},
    "awarded": {"label": "Just won a grant", "sections": ["setup", "operate"]},
    "implementing": {"label": "Running the project", "sections": ["operate", "setup"]},
    "sharing": {"label": "Sharing results and wrapping up", "sections": ["share"]},
}
# Words in a project description that make another guide relevant, whatever the stage.
TRIGGERS = [
    (("sample", "specimen", "blood", "biospecimen", "equipment", "ship", "supplies"), "international-shipping"),
    (("travel", "field", "site visit", "trip"), "international-travel"),
    (("participant", "survey", "interview", "trial", "patients", "human subject", "cohort", "enrol", "enroll"), "irb-international-research"),
    (("data", "records", "dataset", "database"), "data-protection"),
    (("hire", "staff", "pay", "stipend", "community health worker", "consultant"), "hiring-and-paying-people-internationally"),
    (("subaward", "partner institution", "local partner", "ministry"), "subcontracts-and-subawards"),
    (("visitor", "visiting scholar", "host"), "hosting-international-visitors"),
    (("agreement", "mou", "memorandum"), "memoranda-of-understanding"),
]


# words too common to explain a match
GENERIC = {"health", "research", "study", "studies", "project", "global", "institute", "medical", "medicine", "public", "university",
           "center", "program", "work", "working", "new", "using", "based", "data", "care", "community", "people", "rural", "urban",
           "one", "two", "three", "four", "five", "six", "several", "many", "local", "also"}


class PlanIn(BaseModel):
    stage: str
    text: str = Field(default="", max_length=4000)
    opportunity_id: int | None = None


def _words(text: str) -> set[str]:
    from backend.nexus.retrieval import tokens
    return set(tokens(text))


def _match_faculty(text: str, k: int = 8) -> list[dict]:
    from backend.nexus import api as nexus_api
    from backend.nexus.retrieval import tokens
    q = tokens(text)
    low = text.lower()
    with nexus_api.MATCHER_LOCK:
        ix = nexus_api.get_matcher().ix
        scored = []
        for fid, d in ix.d.items():
            s = ix.bm25(q, fid)
            hits = sorted({t for t in list(d.expertise) + list(d.places) + list(d.methods) if t.lower() in low})
            s += 2.5 * len(hits)
            if s > 0:
                scored.append((s, d, hits))
        scored.sort(key=lambda x: -x[0])
        return [{"id": d.id, "name": d.name, "title": d.title, "school": d.school,
                 "why": hits[:4] or sorted((set(q) & set(tokens(d.text))) - GENERIC)[:4]} for _, d, hits in scored[:k]]


def _match_partners(text: str, k: int = 8) -> list[dict]:
    from backend.partners.api import partner_db
    from backend.partners.models import Org
    words, low = _words(text), text.lower()
    out = []
    for o in partner_db().scalars(select(Org)).all():
        tags = set(json.loads(o.expertise or "{}"))
        hay = _words(f"{o.name} {o.description or ''} {' '.join(tags)}")
        country = bool(o.country and o.country.lower() in low)
        named = o.name.lower() in low                       # the text names this organization outright
        score = len(words & hay) + 4 * country + 2 * len({t for t in tags if t.lower() in low}) + 12 * named
        if score >= 2:
            out.append((score + 0.5 * bool(o.yale_links), {
                "id": o.id, "name": o.name, "country": o.country, "type": o.org_type, "website": o.website,
                "works_with_yale": bool(o.yale_links),
                "why": (["named in your text"] if named else []) + ([o.country] if country else []) + sorted(t for t in tags if t.lower() in low)[:3]}))
    out.sort(key=lambda x: -x[0])
    return [o for _, o in out[:k]]


def _match_resources(text: str, k: int = 6) -> list[dict]:
    words = _words(text)
    scored = []
    for f in _load("facilities.json"):
        s = len(words & _words(f["name"] + " " + f["text"]))
        scored.append((s, f))
    scored.sort(key=lambda x: -x[0])
    picked = [f for s, f in scored if s > 0][:k]
    if not picked:   # nothing specific: offer the general institutional resources
        picked = [f for f in _load("facilities.json") if f["category"] == "institutes"][:3]
    return [{"id": f["id"], "name": f["name"], "url": f["url"], "category": f["category"], "text": f["text"]} for f in picked]


def _steps(stage: str, text: str) -> list[dict]:
    topics = _load("topics.json")
    by_slug = {t["slug"]: t for t in topics}
    secs = {s["slug"]: s["title"] for s in _load("sections.json")}
    out, seen = [], set()

    def add(t: dict, why: str):
        if t["slug"] in seen:
            if why.startswith("Your project"):   # already listed for the stage: say why it matters for this project
                next(x for x in out if x["slug"] == t["slug"])["why"] = why
            return
        seen.add(t["slug"])
        out.append({**_topic_card(t), "section_title": secs.get(t["section"]), "why": why,
                    "office": (t.get("office") or {}).get("name"), "path": f"/hub/{t['section']}/{t['slug']}"})

    for sec in STAGES[stage]["sections"]:
        for t in topics:
            if t["section"] == sec:
                add(t, f"Part of {secs.get(sec)}")
    low = text.lower()
    for words, slug in TRIGGERS:
        hit = next((w for w in words if w in low), None)
        if hit and slug in by_slug:
            add(by_slug[slug], f"Your project mentions “{hit}”")
    # put the guides your project text points to first, then the rest of the stage
    out.sort(key=lambda s: 0 if s["why"].startswith("Your project") else 1)
    return out


@router.post("/plan")
def plan(body: PlanIn):
    """Suggestions only: matches come from public profiles and pages, nobody has been contacted."""
    if body.stage not in STAGES:
        raise HTTPException(422, "Pick the stage of your project.")
    text = body.text.strip()
    opp = None
    if body.opportunity_id:
        from backend.radar.api import opportunity_detail
        from backend.radar.db import get_session
        db = get_session()
        try:
            o = opportunity_detail(body.opportunity_id, db)
        except HTTPException:
            raise HTTPException(404, "That funding opportunity wasn't found.")
        finally:
            db.close()
        opp = {"id": o["id"], "title": o["title"], "funder": o.get("funder")}
        text = " ".join(filter(None, [text, o.get("title"), o.get("synopsis") or o.get("description") or ""]))
    if len(text) < 20:
        raise HTTPException(422, "Describe your project in a few sentences (at least 20 characters), or pick a funding call.")
    return {"stage": body.stage, "stage_label": STAGES[body.stage]["label"], "opportunity": opp,
            "faculty": _match_faculty(text), "partners": _match_partners(text),
            "resources": _match_resources(text), "steps": _steps(body.stage, text)}


# ------------------------------------------------------------------ award letters: read the text, keep nothing
MAX_UPLOAD = 8 * 1024 * 1024


def letter_text(name: str, data: bytes) -> str:
    """Plain text from a PDF, Word (.docx) or text file. Raises ValueError for anything else."""
    import io
    low = name.lower()
    if low.endswith(".pdf") or data[:5] == b"%PDF-":
        from pypdf import PdfReader
        return "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(data)).pages[:20])
    if low.endswith(".docx"):
        from docx import Document
        return "\n".join(p.text for p in Document(io.BytesIO(data)).paragraphs)
    if low.endswith((".txt", ".md")):
        return data.decode("utf-8", errors="replace")
    raise ValueError("Upload a PDF, a Word file (.docx) or a text file.")


@router.post("/award-letter")
async def award_letter(request: Request, filename: str = ""):
    """Reads an award letter sent as the raw request body and returns its text for the project description.
    The file is read in memory only: it is not saved, logged or sent anywhere."""
    data = await request.body()
    if not data:
        raise HTTPException(422, "The file was empty.")
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "That file is over 8 MB. Try a smaller PDF, or paste the key parts into “Describe my project”.")
    try:
        text = letter_text(filename, data)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception:
        raise HTTPException(422, "We couldn’t read that file. If it’s a scanned image, paste the key parts into “Describe my project” instead.")
    text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if len(text) < 40:
        raise HTTPException(422, "We couldn’t find text in that file. If it’s a scanned image, paste the key parts into “Describe my project” instead.")
    from backend.partners.api import partner_db
    from backend.partners.models import Org
    from .letter import analyze
    names = [o.name for o in partner_db().scalars(select(Org)).all()]
    info = analyze(text, _load("topics.json"), names)
    return {"text": info["match_text"], "letter_chars": len(text), "truncated": False,
            "facts": info["facts"], "needs": info["needs"], "method": info["method"]}
