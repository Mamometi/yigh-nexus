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

from fastapi import APIRouter, Depends, HTTPException
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
    """The five lifecycle sections with their topic lists."""
    topics = _load("topics.json")
    return [{**s, "topics": [_topic_card(t) for t in topics if t["section"] == s["slug"]]} for s in _load("sections.json")]


@router.get("/topics/{section}/{slug}")
def topic(section: str, slug: str):
    topics = _load("topics.json")
    t = next((t for t in topics if t["section"] == section and t["slug"] == slug), None)
    if not t:
        raise HTTPException(404, "That page doesn't exist.")
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
    tools = [("Facilities & Resources builder", "/hub/tools/facilities", "facilities resources grant section boilerplate equipment computing"),
             ("Letters of support", "/hub/tools/letters", "letter support commitment template request"),
             ("Templates and checklists", "/hub/tools/letters#templates", "template checklist")]
    for title, path, kw in tools:
        score = sum((title + " " + kw).lower().count(w) for w in words)
        if score:
            out.append((score + 3, {"title": title, "summary": "Tool", "kind": "tool", "path": path}))
    return [o for _, o in sorted(out, key=lambda x: -x[0])[:12]]


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
