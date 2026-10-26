"""External partner database (data/partners.db).

An organization's relationship with Yale is "documented" only when a YaleLink row exists, and every
YaleLink must point to an Evidence row with a public URL (enforced in store.add_yale_link). Shared
interests never create a YaleLink.
"""
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "partners.db"


class PartnerBase(DeclarativeBase):
    pass


class Org(PartnerBase):
    __tablename__ = "organizations"
    id: Mapped[int] = mapped_column(primary_key=True)
    ror_id: Mapped[Optional[str]] = mapped_column(String(60), unique=True)
    name: Mapped[str] = mapped_column(String(300))
    norm_name: Mapped[str] = mapped_column(String(300), index=True)
    aliases: Mapped[Optional[str]] = mapped_column(Text)            # JSON list
    country: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    country_code: Mapped[Optional[str]] = mapped_column(String(4))
    org_type: Mapped[str] = mapped_column(String(40))              # university | research_institute | ministry_public_health | multilateral | ngo | healthcare | technology | other
    ror_types: Mapped[Optional[str]] = mapped_column(Text)
    website: Mapped[Optional[str]] = mapped_column(String(500))
    description: Mapped[Optional[str]] = mapped_column(Text)        # verbatim excerpt from an official/Yale page
    expertise: Mapped[Optional[str]] = mapped_column(Text)          # JSON {tag: evidence_id} from documented text
    origin: Mapped[str] = mapped_column(String(30))                 # ghes_site | faculty_activity | ror_search
    last_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime)

    evidence: Mapped[list["Evidence"]] = relationship(back_populates="org", cascade="all, delete-orphan")
    yale_links: Mapped[list["YaleLink"]] = relationship(back_populates="org", cascade="all, delete-orphan")


class Evidence(PartnerBase):
    __tablename__ = "evidence"
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(30))       # yale_partnership | registry | description | project
    url: Mapped[str] = mapped_column(String(800))
    quote: Mapped[Optional[str]] = mapped_column(Text)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime)

    __table_args__ = (UniqueConstraint("org_id", "kind", "url"),)
    org: Mapped[Org] = relationship(back_populates="evidence")


class YaleLink(PartnerBase):
    """A publicly documented connection between the organization and Yale/YIGH."""
    __tablename__ = "yale_links"
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    link_type: Mapped[str] = mapped_column(String(40))  # ghes_training_site | faculty_activity
    faculty_id: Mapped[Optional[int]] = mapped_column(Integer)      # faculty.id in yigh.db, when a named Yale person is documented
    faculty_name: Mapped[Optional[str]] = mapped_column(String(200))
    detail: Mapped[Optional[str]] = mapped_column(Text)
    evidence_id: Mapped[int] = mapped_column(ForeignKey("evidence.id"))

    __table_args__ = (UniqueConstraint("org_id", "link_type", "faculty_name", "evidence_id"),)
    org: Mapped[Org] = relationship(back_populates="yale_links")
    evidence: Mapped[Evidence] = relationship()


class LookupCache(PartnerBase):
    """Cached registry queries so repeat runs don't repeat web requests (30-day TTL)."""
    __tablename__ = "lookup_cache"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(500), unique=True)
    response: Mapped[str] = mapped_column(Text)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime)


class RefreshRun(PartnerBase):
    __tablename__ = "refresh_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    summary: Mapped[Optional[str]] = mapped_column(Text)


_makers: dict = {}


def make_session(path=None):
    """A NEW session each call (sessions must never be shared between threads); engines are cached per path."""
    path = Path(path or os.environ.get("PARTNERS_DB_PATH") or DEFAULT_PATH)
    if str(path) not in _makers:
        path.parent.mkdir(parents=True, exist_ok=True)
        eng = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})

        @event.listens_for(eng, "connect")
        def _fk(c, _):
            c.execute("PRAGMA foreign_keys = ON")
        PartnerBase.metadata.create_all(eng)
        _makers[str(path)] = sessionmaker(bind=eng, autoflush=False, expire_on_commit=False)
    return _makers[str(path)]()
