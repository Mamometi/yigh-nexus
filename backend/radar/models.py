"""Global Health Radar schema.

Stable identifiers:
  * FundingSource.slug  — registry id (e.g. "grants-gov")
  * Organization.slug   — funder id (e.g. "nih", "agency-dos-ghsd")
  * Opportunity.uid     — "opp:<normalized opportunity number>" when the funder publishes a number
                          (so the same NIH NOFO from the RSS feed and from Grants.gov is one record),
                          otherwise "url:<sha1 of normalized official URL>".
Every value shown to users is copied from an official source; nothing is inferred. Fields that are
missing or could not be verified are left empty and the opportunity is flagged for review.
"""
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import RadarBase


class Organization(RadarBase):
    """A funding organization (foundation, agency, multilateral)."""
    __tablename__ = "organizations"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    org_type: Mapped[Optional[str]] = mapped_column(String(100))
    website: Mapped[Optional[str]] = mapped_column(String(500))
    origin: Mapped[str] = mapped_column(String(20), default="curated")  # curated | discovered


class FundingSource(RadarBase):
    """A registry entry: where and how opportunities are collected."""
    __tablename__ = "sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    organization_id: Mapped[Optional[int]] = mapped_column(ForeignKey("organizations.id"))
    official_url: Mapped[str] = mapped_column(String(500))
    access_method: Mapped[str] = mapped_column(String(20))  # api | rss | html_listing | page_monitor | manual
    collector: Mapped[Optional[str]] = mapped_column(String(40))
    endpoint: Mapped[Optional[str]] = mapped_column(String(500))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    last_status: Mapped[Optional[str]] = mapped_column(String(20))  # ok | failed | blocked | skipped
    last_success_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    organization: Mapped[Optional[Organization]] = relationship()


class DiscoveryRun(RadarBase):
    __tablename__ = "discovery_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    mode: Mapped[str] = mapped_column(String(20))  # weekly | deadlines
    started_at: Mapped[datetime] = mapped_column(DateTime)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default="running")  # success | partial | failed
    summary: Mapped[Optional[str]] = mapped_column(Text)  # JSON


class SourceFetch(RadarBase):
    """Per-run, per-source outcome (lets one source fail without failing the run)."""
    __tablename__ = "source_fetches"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("discovery_runs.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    status: Mapped[str] = mapped_column(String(20))  # ok | failed | blocked | skipped
    items_found: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    source: Mapped[FundingSource] = relationship()


class Opportunity(RadarBase):
    __tablename__ = "opportunities"
    id: Mapped[int] = mapped_column(primary_key=True)
    uid: Mapped[str] = mapped_column(String(200), unique=True)
    opportunity_number: Mapped[Optional[str]] = mapped_column(String(80), index=True)
    title: Mapped[str] = mapped_column(Text)
    organization_id: Mapped[Optional[int]] = mapped_column(ForeignKey("organizations.id"))
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))  # first source that found it
    description: Mapped[Optional[str]] = mapped_column(Text)
    deadline: Mapped[Optional[date]] = mapped_column(Date, index=True)
    deadline_text: Mapped[Optional[str]] = mapped_column(Text)     # verbatim, e.g. "Feb 14, 2027" or "Rolling"
    award_floor: Mapped[Optional[float]] = mapped_column(Float)
    award_ceiling: Mapped[Optional[float]] = mapped_column(Float)
    award_text: Mapped[Optional[str]] = mapped_column(Text)        # verbatim from source
    currency: Mapped[Optional[str]] = mapped_column(String(10))
    eligibility: Mapped[Optional[str]] = mapped_column(Text)
    geographic_restrictions: Mapped[Optional[str]] = mapped_column(Text)
    application_url: Mapped[Optional[str]] = mapped_column(String(800))
    official_url: Mapped[str] = mapped_column(String(800))
    posted_date: Mapped[Optional[date]] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="open")  # forecasted | open | closed | unknown
    status_reason: Mapped[Optional[str]] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime)
    first_seen_run_id: Mapped[Optional[int]] = mapped_column(ForeignKey("discovery_runs.id"))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime)
    last_changed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_changed_run_id: Mapped[Optional[int]] = mapped_column(ForeignKey("discovery_runs.id"))
    verification_status: Mapped[str] = mapped_column(String(20), default="unverified")  # verified | partially_verified | unverified | mismatch
    last_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    review_reasons: Mapped[Optional[str]] = mapped_column(Text)  # JSON list
    suspicious_content: Mapped[bool] = mapped_column(Boolean, default=False)

    organization: Mapped[Optional[Organization]] = relationship()
    source: Mapped[FundingSource] = relationship()
    sightings: Mapped[list["Sighting"]] = relationship(back_populates="opportunity", cascade="all, delete-orphan")
    changes: Mapped[list["Change"]] = relationship(back_populates="opportunity", cascade="all, delete-orphan",
                                                   order_by="Change.detected_at")
    verifications: Mapped[list["Verification"]] = relationship(back_populates="opportunity", cascade="all, delete-orphan",
                                                               order_by="Verification.checked_at")
    priorities: Mapped[list["OpportunityPriority"]] = relationship(back_populates="opportunity", cascade="all, delete-orphan")


class Sighting(RadarBase):
    """Each time a source listed the opportunity: where and when it was retrieved."""
    __tablename__ = "sightings"
    id: Mapped[int] = mapped_column(primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(ForeignKey("opportunities.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("discovery_runs.id", ondelete="CASCADE"))
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    source_url: Mapped[str] = mapped_column(String(800))
    external_ref: Mapped[Optional[str]] = mapped_column(String(200))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime)

    __table_args__ = (UniqueConstraint("opportunity_id", "run_id", "source_id"),)
    opportunity: Mapped[Opportunity] = relationship(back_populates="sightings")
    source: Mapped[FundingSource] = relationship()


class Change(RadarBase):
    """Field-level change log: created, updated fields, status changes."""
    __tablename__ = "changes"
    id: Mapped[int] = mapped_column(primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(ForeignKey("opportunities.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[Optional[int]] = mapped_column(ForeignKey("discovery_runs.id"))
    change_type: Mapped[str] = mapped_column(String(20))  # created | updated | status
    field: Mapped[Optional[str]] = mapped_column(String(40))
    old_value: Mapped[Optional[str]] = mapped_column(Text)
    new_value: Mapped[Optional[str]] = mapped_column(Text)
    detected_at: Mapped[datetime] = mapped_column(DateTime)

    opportunity: Mapped[Opportunity] = relationship(back_populates="changes")


class Verification(RadarBase):
    """A check of the record against the official source."""
    __tablename__ = "verifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(ForeignKey("opportunities.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[Optional[int]] = mapped_column(ForeignKey("discovery_runs.id"))
    checked_at: Mapped[datetime] = mapped_column(DateTime)
    url: Mapped[str] = mapped_column(String(800))
    method: Mapped[str] = mapped_column(String(30))  # official_api | official_page
    status: Mapped[str] = mapped_column(String(20))  # verified | partially_verified | unverified | mismatch | unavailable
    details: Mapped[Optional[str]] = mapped_column(Text)  # JSON: {field: {"verified": bool, "evidence": "..."}}

    opportunity: Mapped[Opportunity] = relationship(back_populates="verifications")


class OpportunityPriority(RadarBase):
    """YIGH strategic-priority classification (rule-based, with evidence)."""
    __tablename__ = "opportunity_priorities"
    opportunity_id: Mapped[int] = mapped_column(ForeignKey("opportunities.id", ondelete="CASCADE"), primary_key=True)
    priority: Mapped[str] = mapped_column(String(40), primary_key=True)  # slug, e.g. "climate-health"
    confidence: Mapped[float] = mapped_column(Float)
    confidence_label: Mapped[str] = mapped_column(String(10))
    rule_version: Mapped[str] = mapped_column(String(30))
    explanation: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str] = mapped_column(Text)  # JSON

    opportunity: Mapped[Opportunity] = relationship(back_populates="priorities")


class PageSnapshot(RadarBase):
    """page_monitor sources: last-seen content hash, so changes can be queued for review."""
    __tablename__ = "page_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    url: Mapped[str] = mapped_column(String(800))
    content_hash: Mapped[str] = mapped_column(String(64))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime)
    changed: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    excerpt: Mapped[Optional[str]] = mapped_column(Text)
