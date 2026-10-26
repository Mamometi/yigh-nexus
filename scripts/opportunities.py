"""Global Health Radar agent.

For each major global health grantmaker, asks Claude (with web search + web fetch)
to find currently open or upcoming funding calls, validates the result against a
schema, and writes everything to data/opportunities.json.

Usage:
    python scripts/opportunities.py                  # all funders
    python scripts/opportunities.py wellcome gates   # only these funder ids
"""
from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from typing import List, Literal, Optional

import anthropic
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_opportunities import FUNDERS  # curated funder profiles

OUT = Path(__file__).resolve().parent.parent / "data" / "opportunities.json"
MODEL = "claude-opus-5-5"
MAX_WORKERS = 4
MAX_CONTINUATIONS = 5

client = anthropic.Anthropic()


class Opportunity(BaseModel):
    title: str
    description: str
    url: str
    deadline: Optional[str]  # YYYY-MM-DD, or null if not stated / rolling
    deadline_type: Literal["fixed", "rolling", "recurring", "unknown"]
    amount: Optional[str]
    eligibility: Optional[str]
    us_institutions_eligible: Optional[bool]
    focus_areas: List[str]
    geographic_focus: List[str]
    status: Literal["open", "upcoming"]


class FunderSearchResult(BaseModel):
    opportunities: List[Opportunity]
    notes: str  # e.g. "invitation-only; nothing open"


SYSTEM = """You are a grants research assistant for the Yale Institute for Global Health.
Find funding opportunities that are currently open or announced as upcoming from the funder you are given.
- Prefer the funder's official pages; use web search to locate them and web fetch to read them.
- Only report calls you saw evidence for on a page. Never invent deadlines or amounts; use null when not stated.
- Exclude calls whose deadline has already passed.
- Write descriptions in your own words, 1-2 sentences.
- If the funder only funds by invitation and nothing is open, return an empty list and say so in notes."""


def search_funder(funder: dict) -> dict:
    today = date.today().isoformat()
    prompt = (
        f"Today is {today}. Funder: {funder['name']} ({funder['website']}).\n"
        f"Known funding page: {funder['funding_opportunities_url']}\n"
        f"Focus areas: {', '.join(funder['focus_areas'])}.\n"
        "Find its open or upcoming grant calls, fellowships, prizes or RFPs relevant to global health researchers "
        "(up to 6, most relevant first)."
    )
    messages = [{"role": "user", "content": prompt}]
    tools = [
        {"type": "web_search_20260209", "name": "web_search", "max_uses": 8},
        {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 6},
    ]

    for _ in range(MAX_CONTINUATIONS + 1):
        response = client.messages.parse(
            model=MODEL,
            max_tokens=16000,
            system=SYSTEM,
            thinking={"type": "adaptive"},
            output_config={"effort": "medium"},
            tools=tools,
            messages=messages,
            output_format=FunderSearchResult,
        )
        if response.stop_reason == "pause_turn":
            # Long server-tool turn: append and let Claude resume.
            messages.append({"role": "assistant", "content": response.content})
            continue
        break

    if response.stop_reason == "refusal":
        return {"opportunities": [], "notes": "Model declined this request.", "error": "refusal"}
    if response.parsed_output is None:
        return {"opportunities": [], "notes": "", "error": f"no structured output (stop_reason={response.stop_reason})"}
    return response.parsed_output.model_dump()


def run_one(funder: dict) -> dict:
    try:
        result = search_funder(funder)
    except anthropic.RateLimitError:
        time.sleep(30)
        result = search_funder(funder)
    except anthropic.APIStatusError as e:
        result = {"opportunities": [], "notes": "", "error": f"API error {e.status_code}: {e.message}"}
    except anthropic.APIConnectionError as e:
        result = {"opportunities": [], "notes": "", "error": f"connection error: {e}"}

    today = date.today().isoformat()
    for i, opp in enumerate(result["opportunities"], 1):
        opp["id"] = f"{funder['id']}-{i}"
        opp["funder_id"] = funder["id"]
        opp["funder_name"] = funder["name"]
        opp["source_checked_on"] = today
    print(f"  {funder['id']}: {len(result['opportunities'])} found" + (f" ({result['error']})" if result.get("error") else ""))
    return {**funder, "search_notes": result["notes"], "search_error": result.get("error"),
            "opportunities": result["opportunities"]}


def main(selected: List[str]) -> None:
    funders = [f for f in FUNDERS if not selected or f["id"] in selected]
    print(f"Searching {len(funders)} funders with {MODEL}...")
    with ThreadPoolExecutor(MAX_WORKERS) as pool:
        results = list(pool.map(run_one, funders))

    # Drop anything whose fixed deadline has passed (defensive; the prompt already asks for this).
    today = date.today().isoformat()
    for r in results:
        r["opportunities"] = [o for o in r["opportunities"] if not o["deadline"] or o["deadline"] >= today]

    # When running a subset, keep previous results for the other funders.
    if selected and OUT.exists():
        previous = {f["id"]: f for f in json.loads(OUT.read_text()).get("funders", [])}
        previous.update({r["id"]: r for r in results})
        results = [previous[f["id"]] for f in FUNDERS if f["id"] in previous]

    all_opps = [o for r in results for o in r.get("opportunities", [])]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "generated_on": today,
        "model": MODEL,
        "funder_count": len(results),
        "opportunity_count": len(all_opps),
        "funders": results,
        "opportunities": all_opps,
    }, indent=2, ensure_ascii=False))
    print(f"Wrote {len(all_opps)} opportunities from {len(results)} funders to {OUT}")


if __name__ == "__main__":
    main(sys.argv[1:])
