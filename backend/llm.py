"""One place that decides which AI model the agents use.

Keys are read from a `.env` file in the repo folder first, then from the folder above it (where the course
staff keep theirs). Real environment variables always win over both.

  PORTKEY_API_KEY  -> Yale's Portkey gateway (OpenAI-compatible), model gpt-6-luna   [course default]
  OPENAI_API_KEY   -> OpenAI directly, model gpt-6-luna (override with LLM_MODEL)
  ANTHROPIC_API_KEY-> Claude (anthropic:claude-opus-5-5)
  none             -> every agent falls back to its basic, non-AI mode (the app still works)

LLM_MODEL overrides the model name for whichever provider is used.
"""
from __future__ import annotations

import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PORTKEY_BASE_URL = os.environ.get("PORTKEY_BASE_URL", "https://api.portkey.ai/v1")
COURSE_MODEL = "gpt-6-luna"
# Yale's Portkey routes by model catalog id: "@<provider>/<model>"
PORTKEY_MODEL = os.environ.get("PORTKEY_MODEL", "@azure-openai-global/gpt-6-luna-global")
_loaded = False


def load_env() -> None:
    global _loaded
    if _loaded:
        return
    os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
    try:
        from dotenv import load_dotenv
    except ImportError:  # python-dotenv not installed: rely on real environment variables
        _loaded = True
        return
    for path in (REPO / ".env", REPO.parent / ".env"):  # repo folder first, then one level up
        if path.exists():
            load_dotenv(path, override=False)
    _loaded = True


def provider() -> str | None:
    load_env()
    if os.environ.get("NEXUS_MODEL", "").startswith("test"):
        return "test"
    if os.environ.get("PORTKEY_API_KEY"):
        return "portkey"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return "anthropic"
    return None


def ai_available() -> bool:
    return provider() is not None


def model_name() -> str:
    """A readable id for logs and cache keys, e.g. 'portkey:gpt-6-luna'."""
    p = provider()
    if p == "test":
        return os.environ["NEXUS_MODEL"]
    if p == "anthropic":
        return os.environ.get("LLM_MODEL") and f"anthropic:{os.environ['LLM_MODEL']}" or "anthropic:claude-opus-5-5"
    return f"{p or 'none'}:{os.environ.get('LLM_MODEL', COURSE_MODEL)}"


def model():
    """The model object/string to hand to a PydanticAI Agent."""
    p = provider()
    if p in ("portkey", "openai"):
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
        if p == "portkey":
            from openai import AsyncOpenAI
            key = os.environ["PORTKEY_API_KEY"]
            client = AsyncOpenAI(base_url=PORTKEY_BASE_URL, api_key=key, default_headers={"x-portkey-api-key": key})
            # Responses API: gpt-6-luna only allows tool calls (which every agent here uses) through /v1/responses
            from pydantic_ai.models.openai import OpenAIResponsesModel
            return OpenAIResponsesModel(os.environ.get("LLM_MODEL", PORTKEY_MODEL), provider=OpenAIProvider(openai_client=client))
        return OpenAIChatModel(os.environ.get("LLM_MODEL", COURSE_MODEL), provider=OpenAIProvider(api_key=os.environ["OPENAI_API_KEY"]))
    return model_name() if p else "test"
