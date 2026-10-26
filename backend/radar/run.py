"""Command-line entry point (used by the scheduled workflows).

    python -m backend.radar.run --mode weekly
    python -m backend.radar.run --mode deadlines
    python -m backend.radar.run --mode weekly --fixtures tests/radar/fixtures/week1 --db /tmp/radar.db --today 2026-10-26
"""
import argparse
import json
import logging
import os
import sys
from datetime import date
from pathlib import Path

from sqlalchemy.orm import sessionmaker

from .db import make_engine
from .http import Fetcher, FixtureFetcher
from .pipeline import ROOT, load_registry, run_deadlines, run_weekly, summary_markdown


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["weekly", "deadlines"], default="weekly")
    ap.add_argument("--db", help="SQLite path (default data/radar.db or $RADAR_DB_PATH)")
    ap.add_argument("--fixtures", help="serve saved responses from this directory instead of the network")
    ap.add_argument("--registry", help="source registry JSON (default config/radar_sources.json)")
    ap.add_argument("--today", help="YYYY-MM-DD (testing)")
    ap.add_argument("--sources", help="comma-separated source ids to run")
    ap.add_argument("--max-details", type=int, default=150)
    ap.add_argument("--summary-dir", default=str(ROOT / "data" / "radar"))
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    engine = make_engine(a.db)
    db = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    today = date.fromisoformat(a.today) if a.today else None
    registry = load_registry(a.registry) if a.registry else load_registry()
    if a.mode == "weekly":
        fetcher = FixtureFetcher(a.fixtures) if a.fixtures else Fetcher(registry["user_agent"])
        summary = run_weekly(db, fetcher, registry, today=today, only=a.sources.split(",") if a.sources else None,
                             max_details=a.max_details)
    else:
        summary = run_deadlines(db, today=today)

    out = Path(a.summary_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"last_{a.mode}_run.json").write_text(json.dumps(summary, indent=2, default=str))
    md = summary_markdown(summary)
    (out / f"last_{a.mode}_run.md").write_text(md)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as fh:
            fh.write(md + "\n")
    print(md)
    return 0 if summary.get("status", "success") != "failed" else 1


if __name__ == "__main__":
    sys.exit(main())
