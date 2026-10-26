"""Turn the tagger's technical explanations into plain sentences for people reading the site."""
from __future__ import annotations

import re

_GROUP = re.compile(r"\d+ (core|supporting) term\(s\) \(([^)]*)\)")


def _and(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1] if items else ""


def plain_explanation(text: str | None) -> str | None:
    """'Matched 2 core term(s) (a, b) and 1 supporting term(s) (c) in the profile bio. Assigned because…'
    becomes 'Their profile mentions a, b and c.' Text that isn't in that format is returned unchanged."""
    if not text or not text.startswith("Matched "):
        return text
    main, related = [], []
    for kind, terms in _GROUP.findall(text):
        (main if kind == "core" else related).extend(t.strip() for t in terms.split(",") if t.strip())
    where = "The funding call" if re.search(r"in the profile (opportunity|title|description)", text) else "Their profile"
    words = main + related
    if "research-interest list" in text:
        return f"{_and(words)} {'is' if len(words) == 1 else 'are'} on their list of research interests, but the profile doesn't describe this work further."
    out = f"{where} mentions {_and(words)}." if words else text
    if not main:
        out += " These words are only loosely related, so treat this as a possible fit."
    return out
