"""Chat endpoint for the site assistant."""
from __future__ import annotations

from fastapi import APIRouter, Cookie
from pydantic import BaseModel, Field

from backend.auth.api import current_user

from .agent import chat

router = APIRouter(prefix="/api/assistant", tags=["Assistant"])


class Msg(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(max_length=4000)


class ChatIn(BaseModel):
    messages: list[Msg] = Field(min_length=1, max_length=40)


@router.post("/chat")
def assistant_chat(body: ChatIn, yigh_session: str | None = Cookie(default=None)):
    try:
        current_user(yigh_session)
        signed_in = True
    except Exception:  # noqa: BLE001
        signed_in = False
    return chat([m.model_dump() for m in body.messages], yigh_session, signed_in)
