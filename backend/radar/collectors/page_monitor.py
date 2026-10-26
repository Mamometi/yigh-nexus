"""Pages without an API or a machine-readable listing: detect changes only. A change creates a
review item for a person to read; no opportunity fields are extracted or guessed."""
from __future__ import annotations

import hashlib

from ..sanitize import strip_injections, visible_text


def snapshot(fetcher, cfg):
    page = fetcher.get(cfg["endpoint"], min_interval=cfg.get("min_interval_seconds", 5.0))
    text, _removed = strip_injections(visible_text(page.text))
    return {"url": cfg["endpoint"], "hash": hashlib.sha256(text.encode()).hexdigest(),
            "excerpt": text[:800], "retrieved_at": page.retrieved_at}
