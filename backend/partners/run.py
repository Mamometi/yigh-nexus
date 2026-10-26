"""Build or refresh the partner database (monthly; also safe to run anytime — registry lookups are cached).

    python -m backend.partners.run refresh
"""
import json
import sys
from datetime import timedelta

from sqlalchemy import select

from backend.app.database import SessionLocal
from backend.radar.http import Fetcher

from .collect import faculty_activities, faculty_name_index, ghes_sites
from .models import Org, RefreshRun, make_session
from .ror import Ror
from .store import now

UA = "YIGH-Radar/1.0 (Yale Institute for Global Health; research use)"


def refresh(db=None, fetcher=None, fdb=None):
    db, fdb = db or make_session(), fdb or SessionLocal()
    fetcher = fetcher or Fetcher(UA)
    ror = Ror(db, fetcher)
    run = RefreshRun(started_at=now())
    db.add(run)
    summary = {"ghes": ghes_sites(db, fetcher, ror, faculty_name_index(fdb)), "faculty_activities": faculty_activities(db, fdb, ror)}
    stale = [o.name for o in db.scalars(select(Org)) if o.last_verified_at and now() - o.last_verified_at > timedelta(days=180)]
    summary.update({"organizations": db.query(Org).count(), "stale_records": stale})
    run.finished_at, run.summary = now(), json.dumps(summary, default=str)
    db.commit()
    return summary


if __name__ == "__main__":
    print(json.dumps(refresh(), indent=2, default=str)) if sys.argv[1:] == ["refresh"] else print(__doc__)
