"""Database models shared by Constellation and Global Health Radar.

Shared vocabularies (research interests, regions, strategic priorities) are
separate tables so faculty, funders and opportunities can be matched on the
same terms.
"""
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (Boolean, CheckConstraint, Column, Date, DateTime, Float, ForeignKey,
                        Integer, String, Table, Text, UniqueConstraint, func)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


# ---------------------------------------------------------------- organization

class School(Base):
    __tablename__ = "schools"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)

    departments: Mapped[list["Department"]] = relationship(back_populates="school")
    faculty: Mapped[list["Faculty"]] = relationship(back_populates="school")


class Department(Base):
    __tablename__ = "departments"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    school_id: Mapped[Optional[int]] = mapped_column(ForeignKey("schools.id"))

    school: Mapped[Optional[School]] = relationship(back_populates="departments")


# ---------------------------------------------------------------- shared vocabularies

class ResearchInterest(Base):
    __tablename__ = "research_interests"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)


class Region(Base):
    """A country or a multi-country region (e.g. 'Sub-Saharan Africa')."""
    __tablename__ = "regions"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    kind: Mapped[str] = mapped_column(String(20), default="country")  # country | region | global


class StrategicPriority(Base):
    __tablename__ = "strategic_priorities"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text)


class StandardKeyword(Base):
    """Controlled vocabulary used for generated keyword tags (distinct from free-text profile interests)."""
    __tablename__ = "standard_keywords"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)


class ClassificationMixin:
    """Provenance for every generated classification.

    confidence is a heuristic 0-1 rule score (how much textual support was found),
    NOT a calibrated probability. confidence_label (high/medium/low) is what the UI should show.
    """
    confidence: Mapped[float] = mapped_column(Float)
    confidence_label: Mapped[str] = mapped_column(String(10))   # high | medium | low
    method: Mapped[str] = mapped_column(String(20))             # rules | llm | manual
    rule_version: Mapped[Optional[str]] = mapped_column(String(30))
    explanation: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str] = mapped_column(Text)                 # JSON: [{field, term, snippet}]
    classified_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ---------------------------------------------------------------- faculty (Constellation)

class Faculty(Base):
    __tablename__ = "faculty"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    title: Mapped[Optional[str]] = mapped_column(Text)
    email: Mapped[Optional[str]] = mapped_column(String(200))
    bio: Mapped[Optional[str]] = mapped_column(Text)
    school_id: Mapped[Optional[int]] = mapped_column(ForeignKey("schools.id"), index=True)
    department_id: Mapped[Optional[int]] = mapped_column(ForeignKey("departments.id"), index=True)
    source_url: Mapped[str] = mapped_column(String(500), unique=True)
    # Where the person came from: "yigh" (YIGH affiliated-faculty directory) or "ysph" (YSPH faculty
    # directory, included because their profile documents global health work; see inclusion_reasons).
    source: Mapped[str] = mapped_column(String(20), default="yigh", index=True)
    inclusion_reasons: Mapped[Optional[str]] = mapped_column(Text)  # JSON list, for source="ysph"
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    school: Mapped[Optional[School]] = relationship(back_populates="faculty")
    department: Mapped[Optional[Department]] = relationship()
    appointments: Mapped[list["FacultyAppointment"]] = relationship(back_populates="faculty", cascade="all, delete-orphan")
    interests: Mapped[list["FacultyInterest"]] = relationship(back_populates="faculty", cascade="all, delete-orphan")
    regions: Mapped[list["FacultyRegion"]] = relationship(back_populates="faculty", cascade="all, delete-orphan")
    priorities: Mapped[list["FacultyPriority"]] = relationship(back_populates="faculty", cascade="all, delete-orphan")
    keywords: Mapped[list["FacultyKeyword"]] = relationship(back_populates="faculty", cascade="all, delete-orphan")
    source_texts: Mapped[list["FacultySourceText"]] = relationship(back_populates="faculty", cascade="all, delete-orphan")
    activities: Mapped[list["FacultyActivity"]] = relationship(back_populates="faculty", cascade="all, delete-orphan")
    organizations: Mapped[list["Organization"]] = relationship(secondary="faculty_organizations")
    coauthors: Mapped[list["FacultyCoauthor"]] = relationship(back_populates="faculty", cascade="all, delete-orphan",
                                                              foreign_keys="FacultyCoauthor.faculty_id")


class FacultySourceText(Base):
    """Verbatim text captured from the faculty profile. Never edited by classifiers."""
    __tablename__ = "faculty_source_texts"
    id: Mapped[int] = mapped_column(primary_key=True)
    faculty_id: Mapped[int] = mapped_column(ForeignKey("faculty.id", ondelete="CASCADE"), index=True)
    field: Mapped[str] = mapped_column(String(40))  # title | bio | research_interests | appointments
    text: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(String(500))
    retrieved_on: Mapped[Optional[date]] = mapped_column(Date)

    __table_args__ = (UniqueConstraint("faculty_id", "field"),)

    faculty: Mapped["Faculty"] = relationship(back_populates="source_texts")


class FacultyActivity(Base):
    """Source: an activity entered on the profile (e.g. an international research project)."""
    __tablename__ = "faculty_activities"
    id: Mapped[int] = mapped_column(primary_key=True)
    faculty_id: Mapped[int] = mapped_column(ForeignKey("faculty.id", ondelete="CASCADE"), index=True)
    title: Mapped[Optional[str]] = mapped_column(Text)
    activity_type: Mapped[Optional[str]] = mapped_column(String(60))
    start_date: Mapped[Optional[date]] = mapped_column(Date)
    end_date: Mapped[Optional[date]] = mapped_column(Date)
    locations: Mapped[Optional[str]] = mapped_column(Text)  # JSON list, verbatim, e.g. ["Kikuyu, Central, Kenya"]
    synopsis: Mapped[Optional[str]] = mapped_column(Text)

    faculty: Mapped["Faculty"] = relationship(back_populates="activities")


class Organization(Base):
    """Source: Yale centers, networks, programs and labs listed under 'Other Departments & Organizations'."""
    __tablename__ = "organizations"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    url: Mapped[Optional[str]] = mapped_column(String(500))


faculty_organizations = Table("faculty_organizations", Base.metadata,
    Column("faculty_id", ForeignKey("faculty.id", ondelete="CASCADE"), primary_key=True),
    Column("organization_id", ForeignKey("organizations.id"), primary_key=True))


class FacultyCoauthor(Base):
    """Source (verified): 'Yale Co-Authors' on the profile, i.e. frequent collaborators on published research.
    coauthor_faculty_id is set when the co-author is also in this directory."""
    __tablename__ = "faculty_coauthors"
    id: Mapped[int] = mapped_column(primary_key=True)
    faculty_id: Mapped[int] = mapped_column(ForeignKey("faculty.id", ondelete="CASCADE"), index=True)
    coauthor_name: Mapped[str] = mapped_column(String(200))
    coauthor_url: Mapped[Optional[str]] = mapped_column(String(500))
    coauthor_faculty_id: Mapped[Optional[int]] = mapped_column(ForeignKey("faculty.id", ondelete="SET NULL"), index=True)

    faculty: Mapped["Faculty"] = relationship(back_populates="coauthors", foreign_keys=[faculty_id])
    coauthor: Mapped[Optional["Faculty"]] = relationship(foreign_keys=[coauthor_faculty_id])


class FacultyAppointment(Base):
    __tablename__ = "faculty_appointments"
    id: Mapped[int] = mapped_column(primary_key=True)
    faculty_id: Mapped[int] = mapped_column(ForeignKey("faculty.id", ondelete="CASCADE"), index=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"))
    title: Mapped[Optional[str]] = mapped_column(String(200))
    appointment_type: Mapped[Optional[str]] = mapped_column(String(30))  # Primary | Secondary | ...

    faculty: Mapped[Faculty] = relationship(back_populates="appointments")
    department: Mapped[Department] = relationship()


class FacultyInterest(Base):
    __tablename__ = "faculty_interests"
    faculty_id: Mapped[int] = mapped_column(ForeignKey("faculty.id", ondelete="CASCADE"), primary_key=True)
    interest_id: Mapped[int] = mapped_column(ForeignKey("research_interests.id"), primary_key=True)
    category: Mapped[Optional[str]] = mapped_column(String(100))  # e.g. "Public Health Interests"

    faculty: Mapped[Faculty] = relationship(back_populates="interests")
    interest: Mapped[ResearchInterest] = relationship()


class FacultyRegion(ClassificationMixin, Base):
    """Generated: geographic interest explicitly supported by profile text."""
    __tablename__ = "faculty_regions"
    faculty_id: Mapped[int] = mapped_column(ForeignKey("faculty.id", ondelete="CASCADE"), primary_key=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), primary_key=True)

    faculty: Mapped[Faculty] = relationship(back_populates="regions")
    region: Mapped[Region] = relationship()


class FacultyPriority(ClassificationMixin, Base):
    """Generated: YIGH strategic priority. A faculty member may have several."""
    __tablename__ = "faculty_priorities"
    faculty_id: Mapped[int] = mapped_column(ForeignKey("faculty.id", ondelete="CASCADE"), primary_key=True)
    priority_id: Mapped[int] = mapped_column(ForeignKey("strategic_priorities.id"), primary_key=True)

    faculty: Mapped[Faculty] = relationship(back_populates="priorities")
    priority: Mapped[StrategicPriority] = relationship()


class FacultyKeyword(ClassificationMixin, Base):
    """Generated: standardized research keyword."""
    __tablename__ = "faculty_keywords"
    faculty_id: Mapped[int] = mapped_column(ForeignKey("faculty.id", ondelete="CASCADE"), primary_key=True)
    keyword_id: Mapped[int] = mapped_column(ForeignKey("standard_keywords.id"), primary_key=True)

    faculty: Mapped[Faculty] = relationship(back_populates="keywords")
    keyword: Mapped[StandardKeyword] = relationship()


# ---------------------------------------------------------------- funders & opportunities (Radar)

funder_interests = Table("funder_interests", Base.metadata,
    Column("funder_id", ForeignKey("funders.id", ondelete="CASCADE"), primary_key=True),
    Column("interest_id", ForeignKey("research_interests.id"), primary_key=True))
funder_regions = Table("funder_regions", Base.metadata,
    Column("funder_id", ForeignKey("funders.id", ondelete="CASCADE"), primary_key=True),
    Column("region_id", ForeignKey("regions.id"), primary_key=True))
opportunity_interests = Table("opportunity_interests", Base.metadata,
    Column("opportunity_id", ForeignKey("opportunities.id", ondelete="CASCADE"), primary_key=True),
    Column("interest_id", ForeignKey("research_interests.id"), primary_key=True))
opportunity_regions = Table("opportunity_regions", Base.metadata,
    Column("opportunity_id", ForeignKey("opportunities.id", ondelete="CASCADE"), primary_key=True),
    Column("region_id", ForeignKey("regions.id"), primary_key=True))
opportunity_priorities = Table("opportunity_priorities", Base.metadata,
    Column("opportunity_id", ForeignKey("opportunities.id", ondelete="CASCADE"), primary_key=True),
    Column("priority_id", ForeignKey("strategic_priorities.id"), primary_key=True))


class Funder(Base):
    __tablename__ = "funders"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    funder_type: Mapped[Optional[str]] = mapped_column(String(100))
    headquarters: Mapped[Optional[str]] = mapped_column(String(120))
    website: Mapped[Optional[str]] = mapped_column(String(500))
    funding_url: Mapped[Optional[str]] = mapped_column(String(500))
    accepts_unsolicited: Mapped[Optional[str]] = mapped_column(String(200))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(20), default="curated")  # curated | discovered

    interests: Mapped[list[ResearchInterest]] = relationship(secondary=funder_interests)
    regions: Mapped[list[Region]] = relationship(secondary=funder_regions)
    opportunities: Mapped[list["Opportunity"]] = relationship(back_populates="funder", cascade="all, delete-orphan")


class Opportunity(Base):
    __tablename__ = "opportunities"
    id: Mapped[int] = mapped_column(primary_key=True)
    funder_id: Mapped[int] = mapped_column(ForeignKey("funders.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[Optional[str]] = mapped_column(Text)
    url: Mapped[str] = mapped_column(String(500))
    deadline: Mapped[Optional[date]] = mapped_column(Date, index=True)
    deadline_type: Mapped[str] = mapped_column(String(20), default="unknown")  # fixed | rolling | recurring | unknown
    amount: Mapped[Optional[str]] = mapped_column(String(200))
    eligibility: Mapped[Optional[str]] = mapped_column(Text)
    us_institutions_eligible: Mapped[Optional[bool]] = mapped_column(Boolean)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | upcoming | closed
    source_checked_on: Mapped[Optional[date]] = mapped_column(Date)

    __table_args__ = (UniqueConstraint("funder_id", "url", "title"),)

    funder: Mapped[Funder] = relationship(back_populates="opportunities")
    interests: Mapped[list[ResearchInterest]] = relationship(secondary=opportunity_interests)
    regions: Mapped[list[Region]] = relationship(secondary=opportunity_regions)
    priorities: Mapped[list[StrategicPriority]] = relationship(secondary=opportunity_priorities)


# ---------------------------------------------------------------- matches

class CollaborationMatch(Base):
    """Faculty <-> faculty suggestion. Stored once per pair (faculty_a_id < faculty_b_id)."""
    __tablename__ = "collaboration_matches"
    id: Mapped[int] = mapped_column(primary_key=True)
    faculty_a_id: Mapped[int] = mapped_column(ForeignKey("faculty.id", ondelete="CASCADE"), index=True)
    faculty_b_id: Mapped[int] = mapped_column(ForeignKey("faculty.id", ondelete="CASCADE"), index=True)
    score: Mapped[float] = mapped_column(Float)
    shared_interests: Mapped[Optional[str]] = mapped_column(Text)   # JSON list
    shared_regions: Mapped[Optional[str]] = mapped_column(Text)     # JSON list
    shared_priorities: Mapped[Optional[str]] = mapped_column(Text)  # JSON list
    cross_school: Mapped[bool] = mapped_column(Boolean, default=False)
    rationale: Mapped[Optional[str]] = mapped_column(Text)
    method: Mapped[str] = mapped_column(String(20), default="rules")  # rules | embedding | llm
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (UniqueConstraint("faculty_a_id", "faculty_b_id"),
                      CheckConstraint("faculty_a_id < faculty_b_id", name="ordered_pair"))

    faculty_a: Mapped[Faculty] = relationship(foreign_keys=[faculty_a_id])
    faculty_b: Mapped[Faculty] = relationship(foreign_keys=[faculty_b_id])


class OpportunityMatch(Base):
    """Faculty <-> funding opportunity suggestion (links Constellation and Radar)."""
    __tablename__ = "opportunity_matches"
    id: Mapped[int] = mapped_column(primary_key=True)
    faculty_id: Mapped[int] = mapped_column(ForeignKey("faculty.id", ondelete="CASCADE"), index=True)
    opportunity_id: Mapped[int] = mapped_column(ForeignKey("opportunities.id", ondelete="CASCADE"), index=True)
    score: Mapped[float] = mapped_column(Float)
    rationale: Mapped[Optional[str]] = mapped_column(Text)
    method: Mapped[str] = mapped_column(String(20), default="rules")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (UniqueConstraint("faculty_id", "opportunity_id"),)

    faculty: Mapped[Faculty] = relationship()
    opportunity: Mapped[Opportunity] = relationship()
