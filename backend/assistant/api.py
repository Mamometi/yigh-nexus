"""Chat endpoint for the site assistant."""
from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import APIRouter, Cookie, HTTPException, Request
from pydantic import BaseModel, Field

from backend.auth.api import current_user

from .agent import chat

router = APIRouter(prefix="/api/assistant", tags=["Assistant"])


class Msg(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(max_length=4000)


class ChatIn(BaseModel):
    messages: list[Msg] = Field(min_length=1, max_length=40)


RATE = (20, 600)  # at most 20 messages per visitor per 10 minutes
_recent: dict[str, deque] = defaultdict(deque)


def _rate_limited(key: str) -> bool:
    now, q = time.time(), _recent[key]
    while q and now - q[0] > RATE[1]:
        q.popleft()
    if len(q) >= RATE[0]:
        return True
    q.append(now)
    return False


@router.post("/chat")
def assistant_chat(body: ChatIn, request: Request, yigh_session: str | None = Cookie(default=None)):
    if _rate_limited(yigh_session or (request.client.host if request.client else "unknown")):
        raise HTTPException(429, "Whoa, that's a lot of questions! Please wait a few minutes and try again.")
    try:
        current_user(yigh_session)
        signed_in = True
    except Exception:  # noqa: BLE001
        signed_in = False
    return chat([m.model_dump() for m in body.messages], yigh_session, signed_in)
