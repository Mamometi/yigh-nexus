"""The site assistant: answers come only from the site's own data, and the Launchpad stays behind sign-in."""
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart

from backend.assistant import agent as A


def test_basic_mode_answers_from_site_data(monkeypatch):
    calls = []

    def fake(deps, path, params=None, method="GET"):
        deps.tools_used.append(path)
        calls.append(path)
        if path == "/api/radar/funders":
            return [{"value": "gates", "label": "Gates Foundation", "count": 1}]
        if path == "/api/radar/funders/gates/timing":
            return {"funder": {"name": "Gates Foundation"}, "headline": "Nothing is open now.", "last_opened": None,
                    "first_recorded": None, "last_closed": None, "forecasted": [], "open_now": []}
        if path == "/api/faculty":
            return [{"id": 7, "name": "Ada Lovelace, PhD", "school": "Public Health", "keywords": ["Malaria"], "priorities": [], "regions": []}]
        return {"count": 0, "opportunities": []}
    monkeypatch.setattr(A, "call_api", fake)
    monkeypatch.setattr(A, "ai_available", lambda: False)

    r = A.chat([{"role": "user", "content": "When does the Gates Foundation open again?"}], None, False)
    assert r["mode"] == "basic" and "Gates Foundation" in r["reply"] and "/api/radar/funders/gates/timing" in calls
    r = A.chat([{"role": "user", "content": "who works on malaria?"}], None, False)
    assert "[Ada Lovelace, PhD](/faculty/7)" in r["reply"]


def test_concept_tool_requires_sign_in(monkeypatch):
    monkeypatch.setattr(A, "call_api", lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not call the API")))
    out = A.t_draft_concept(A.Deps(signed_in=False), 1)
    assert "sign" in out["error"].lower()


def test_ai_mode_uses_tools(monkeypatch):
    monkeypatch.setattr(A, "call_api", lambda deps, path, params=None, method="GET":
                        (deps.tools_used.append(path), {"count": 1, "opportunities": [
                            {"id": 3, "title": "Heat and Health", "funder": "Wellcome", "status": "open", "priorities": []}]})[1])

    def model(messages, info: AgentInfo):
        if len(messages) == 1:
            return ModelResponse(parts=[ToolCallPart("search_opportunities", {"query": "heat"})])
        return ModelResponse(parts=[TextPart("See [Heat and Health](/radar/3).")])
    r = A.chat([{"role": "user", "content": "heat grants?"}], None, False, model=FunctionModel(model))
    assert r["mode"] == "ai" and "/radar/3" in r["reply"] and "/api/radar/opportunities" in r["tools_used"]
