"""Measure real agent runs for the report (token counts, latency) and save one traced chat run.

    .venv/bin/python -m scripts.measure_runs
Every run is appended to data/usage_log.jsonl by backend/llm.py; this script also writes docs/report/trace_chat.json.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from backend import llm
from backend.assistant import agent as A

OUT = Path(__file__).resolve().parents[1] / "docs" / "report"
CHAT = [
    "Hi who can I collaborate with that works on climate and health in Kenya?",
    "Any open funding for digital health or AI?",
    "When does the Gates Foundation open again?",
    "Who works on malaria?",
    "Build a team for the Emerging Infections Network call",
    "What are YIGH's strategic priorities?",
]


def main():
    assert llm.ai_available(), "Set PORTKEY_API_KEY (or have the course .env one folder up)"
    print("model:", llm.model_name())
    # 1) traced chat run (first question) with every message, tool call and tool result
    deps = A.Deps()
    t0 = time.perf_counter()
    r = A.build_agent().run_sync(CHAT[0], deps=deps, usage_limits=llm.limits("assistant"))
    row = llm.record("assistant", r.usage, latency_s=time.perf_counter() - t0)
    steps = []
    for m in r.all_messages():
        for p in m.parts:
            kind = type(p).__name__
            if kind == "SystemPromptPart":
                continue
            content = getattr(p, "content", None)
            if kind == "ToolCallPart":
                steps.append({"step": "tool_call", "tool": p.tool_name, "args": p.args_as_dict()})
            elif kind == "ToolReturnPart":
                steps.append({"step": "tool_result", "tool": p.tool_name, "result": json.dumps(content, default=str)[:700]})
            elif kind == "UserPromptPart":
                steps.append({"step": "user", "text": content})
            elif kind == "TextPart":
                steps.append({"step": "answer", "text": content})
            elif kind == "ThinkingPart":
                steps.append({"step": "reasoning", "text": (content or "")[:300]})
    (OUT / "trace_chat.json").write_text(json.dumps({"question": CHAT[0], "usage": row, "steps": steps}, indent=1, default=str))
    print("traced:", row)
    # 2) the other chat questions
    for q in CHAT[1:]:
        res = A.chat([{"role": "user", "content": q}], None, False)
        print(q[:40], "->", res["mode"], res.get("usage"))
    # 3) team matching (forced fresh AI runs) on three opportunities
    from backend.nexus.api import get_matcher
    m = get_matcher()
    for oid in (15, 14, 5):
        t = time.perf_counter()
        doc = m.recommend(oid, mode="ai", force=True)
        print("team", oid, doc["generated_by"], round(time.perf_counter() - t, 1), "s")
    # 4) one-pagers with user goals
    from backend.partners.api import workspace
    from backend.nexus.concept import build_concept
    for oid, goals in ((15, ["Track travel-associated infections in returning travelers", "Train clinicians to spot imported arboviruses"]),
                       (14, ["Study adolescent HIV care in two clinics", "Train peer counselors"])):
        d = build_concept(m, workspace(oid, mode="auto"), None, goals=goals)
        print("one-pager", oid, d["generated_by"], d["cache"])


if __name__ == "__main__":
    main()
