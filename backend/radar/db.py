"""Separate SQLite database for Global Health Radar (persistent discovery history).

Kept apart from the faculty database so rebuilding faculty data never wipes discovery history,
and so the scheduled job only has to persist one small file. RADAR_DB_PATH overrides the location
(tests use a temporary file).
"""
import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "radar.db"


class RadarBase(DeclarativeBase):
    pass


def make_engine(path: str | os.PathLike | None = None):
    path = Path(path or os.environ.get("RADAR_DB_PATH") or DEFAULT_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys = ON")

    from . import models  # noqa: F401  (register tables)
    RadarBase.metadata.create_all(engine)
    return engine


_engine = None
_Session = None


def get_session():
    global _engine, _Session
    if _Session is None:
        _engine = make_engine()
        _Session = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    return _Session()


def get_radar_db():
    """FastAPI dependency."""
    db = get_session()
    try:
        yield db
    finally:
        db.close()
