"""Sign-in for members-only features (the Launchpad).

Local accounts restricted to @yale.edu addresses, stored in data/auth.db. Passwords are hashed with
PBKDF2-SHA256 (600k iterations, per-user salt). A successful sign-in sets an HttpOnly, SameSite=Lax
session cookie holding a random token; only its SHA-256 hash is stored. Sessions last 14 days.
In production this would be replaced by Yale CAS / NetID single sign-on.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import DateTime, ForeignKey, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

DB_PATH = Path(os.environ.get("AUTH_DB", Path(__file__).resolve().parents[2] / "data" / "auth.db"))
COOKIE = "yigh_session"
SESSION_DAYS = 14
ITERATIONS = 600_000
EMAIL = re.compile(r"^[A-Za-z0-9._%+-]+@yale\.edu$", re.I)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime)


class AuthSession(Base):
    __tablename__ = "sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime)


_engine = None
_Session = None


def auth_db() -> Session:
    global _engine, _Session
    if _engine is None or str(_engine.url.database) != str(DB_PATH):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
        Base.metadata.create_all(_engine)
        _Session = sessionmaker(bind=_engine, expire_on_commit=False)
    return _Session()


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def hash_password(pw: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, it, salt, dk = stored.split("$")
        return hmac.compare_digest(hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), int(it)).hex(), dk)
    except ValueError:
        return False


def _token_hash(t: str) -> str:
    return hashlib.sha256(t.encode()).hexdigest()


def _public(u: User) -> dict:
    return {"id": u.id, "email": u.email, "name": u.name}


def current_user(yigh_session: str | None = Cookie(default=None)) -> dict:
    if not yigh_session:
        raise HTTPException(401, "Sign in to use the Launchpad.")
    with auth_db() as db:
        s = db.scalar(select(AuthSession).filter_by(token_hash=_token_hash(yigh_session)))
        if not s or s.expires_at < _now():
            raise HTTPException(401, "Your session has expired. Sign in again.")
        return _public(db.get(User, s.user_id))


router = APIRouter(prefix="/api/auth", tags=["Sign-in"])


class Register(BaseModel):
    email: str
    name: str
    password: str


class Login(BaseModel):
    email: str
    password: str


def _start_session(db: Session, user: User, response: Response) -> None:
    token = secrets.token_urlsafe(32)
    db.add(AuthSession(token_hash=_token_hash(token), user_id=user.id, expires_at=_now() + timedelta(days=SESSION_DAYS)))
    db.commit()
    response.set_cookie(COOKIE, token, max_age=SESSION_DAYS * 86400, httponly=True, samesite="lax",
                        secure=os.environ.get("COOKIE_SECURE") == "1", path="/")


@router.post("/register")
def register(body: Register, response: Response):
    email = body.email.strip().lower()
    if not EMAIL.match(email):
        raise HTTPException(422, "Use your @yale.edu email address.")
    if len(body.password) < 10:
        raise HTTPException(422, "Password must be at least 10 characters.")
    if not body.name.strip():
        raise HTTPException(422, "Enter your name.")
    with auth_db() as db:
        if db.scalar(select(User).filter_by(email=email)):
            raise HTTPException(409, "An account with this email already exists. Sign in instead.")
        u = User(email=email, name=body.name.strip()[:200], password_hash=hash_password(body.password), created_at=_now())
        db.add(u)
        db.commit()
        _start_session(db, u, response)
        return _public(u)


@router.post("/login")
def login(body: Login, response: Response):
    with auth_db() as db:
        u = db.scalar(select(User).filter_by(email=body.email.strip().lower()))
        if not u or not verify_password(body.password, u.password_hash):
            raise HTTPException(401, "Email or password is incorrect.")
        _start_session(db, u, response)
        return _public(u)


@router.post("/logout")
def logout(response: Response, yigh_session: str | None = Cookie(default=None)):
    if yigh_session:
        with auth_db() as db:
            s = db.scalar(select(AuthSession).filter_by(token_hash=_token_hash(yigh_session)))
            if s:
                db.delete(s)
                db.commit()
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(yigh_session: str | None = Cookie(default=None)):
    """The signed-in user, or null when signed out (200 either way, so the app can check quietly)."""
    try:
        return current_user(yigh_session)
    except HTTPException:
        return None
