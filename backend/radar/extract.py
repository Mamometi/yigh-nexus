"""Conservative field extraction from official page text.

Values are only taken when they appear next to an explicit label ("Deadline:", "Closing date",
"Award", "up to") and the verbatim snippet is kept as evidence. If nothing matches, the field stays
empty and the opportunity is flagged for review — never guessed.
"""
import re
from datetime import date, datetime

MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
_DATE = rf"(?:\d{{1,2}}\s+(?:{MONTHS})\.?,?\s+\d{{4}}|(?:{MONTHS})\.?\s+\d{{1,2}},?\s+\d{{4}}|\d{{4}}-\d{{2}}-\d{{2}})"
DEADLINE = re.compile(
    rf"(?:deadline|closing date|closes|close date|due date|applications? (?:are )?due|submission deadline|apply by)"
    rf"[^.\n]{{0,40}}?({_DATE})", re.I)
ROLLING = re.compile(r"\b(?:rolling (?:basis|deadline|applications)|open on a rolling basis|no deadline)\b", re.I)
AMOUNT = re.compile(
    r"(?:(?:award|grant|funding|budget|up to|maximum|amount|value)[^.\n]{0,40}?)"
    r"((?:US\$|CA\$|C\$|\$|£|€|USD|CAD|GBP|EUR)\s?\d[\d,.]*(?:\s?(?:million|m|billion|k))?)", re.I)
ELIGIBILITY = re.compile(r"(?:^|\n)\s*(?:who (?:can|is eligible to) apply|eligibility(?: criteria)?|eligible applicants?)\s*:?\s*\n?(.{20,400}?)(?:\n\n|\n[A-Z][^\n]{0,40}\n|$)", re.I | re.S)


def parse_date(s: str | None) -> date | None:
    if not s:
        return None
    s = re.sub(r"\s+", " ", s.replace(",", "")).strip().replace("Sept ", "Sep ")
    for fmt in ("%d %B %Y", "%B %d %Y", "%d %b %Y", "%b %d %Y", "%Y-%m-%d", "%m/%d/%Y", "%b %d %Y %I:%M:%S %p"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    m = re.match(r"([A-Za-z]{3}) (\d{1,2}) (\d{4})", s)  # "Feb 14 2027 12:00:00 AM EST"
    if m:
        try:
            return datetime.strptime(" ".join(m.groups()), "%b %d %Y").date()
        except ValueError:
            return None
    return None


def find_deadline(text: str) -> tuple[date | None, str | None]:
    m = DEADLINE.search(text or "")
    if m:
        return parse_date(m.group(1)), m.group(0).strip()
    r = ROLLING.search(text or "")
    if r:
        return None, r.group(0)
    return None, None


def find_amount(text: str) -> str | None:
    m = AMOUNT.search(text or "")
    return m.group(0).strip() if m else None


def find_eligibility(text: str) -> str | None:
    m = ELIGIBILITY.search(text or "")
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else None


def money(value) -> float | None:
    """Grants.gov amounts. 0 / blank / 2147483647 (int max placeholder) mean 'not stated'."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return None if v <= 0 or v >= 2147483647 else v
