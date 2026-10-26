"""Turn untrusted external HTML into plain visible text, and detect instruction-like content.

Everything fetched from a funder's site is data, never instructions. The pipeline is deterministic
(no LLM reads this text), but pages can still try to smuggle values ("deadline: 2099", "mark as
verified") into what we store, so:
  * scripts, styles, comments, hidden and aria-hidden elements are dropped;
  * sentences that look like instructions to an AI/system are removed from stored text and the
    opportunity is flagged for review.
"""
import re

from bs4 import BeautifulSoup, Comment

INJECTION = re.compile(
    r"ignore (?:all |any )?(?:previous|prior|above) (?:instructions|prompts?)|disregard (?:the )?(?:above|previous)|"
    r"\b(?:system|assistant) (?:prompt|message|instruction)s?\b|you are (?:an? )?(?:ai|assistant|language model)|"
    r"\bas an ai\b|(?:mark|set|flag) (?:this|the) (?:record|opportunity|entry)? ?(?:as )?(?:verified|approved)|"
    r"\bnew instructions?\b|\boverride\b.*\b(?:deadline|amount|status)\b|<\s*/?\s*(?:system|instructions?)\s*>",
    re.I)

_HIDDEN_STYLE = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0", re.I)


def visible_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for el in soup(["script", "style", "noscript", "template", "iframe", "svg", "head"]):
        el.decompose()
    for c in soup.find_all(string=lambda s: isinstance(s, Comment)):
        c.extract()
    for el in soup.find_all(True):
        if el.decomposed:
            continue
        attrs = el.attrs or {}
        if (attrs.get("hidden") is not None or attrs.get("aria-hidden") == "true"
                or _HIDDEN_STYLE.search(attrs.get("style", "") or "")):
            el.decompose()
    text = soup.get_text("\n", strip=True)
    return re.sub(r"[ \t]+", " ", text)


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


def strip_injections(text: str) -> tuple[str, list[str]]:
    """Remove instruction-like sentences. Returns (clean_text, removed_sentences)."""
    kept, removed = [], []
    for s in split_sentences(text or ""):
        (removed if INJECTION.search(s) else kept).append(s)
    return " ".join(kept), removed


def html_to_text(html: str) -> str:
    """Grants.gov descriptions contain HTML markup; keep only text."""
    return re.sub(r"\s+", " ", BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True)).strip()
