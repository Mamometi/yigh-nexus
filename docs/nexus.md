# YIGH Nexus: faculty matchmaking for funding opportunities

For each relevant opportunity found by Global Health Radar, Nexus recommends Yale faculty and interdisciplinary teams, explaining why each person could contribute. Recommendations rest on documented profile evidence, and everything generated (roles, contributions, complementarity, scores) is labelled as a hypothesis.

## Pipeline
```
Radar opportunity (verified) ──► profile with the same transparent rules (topics, methods, places, YIGH priorities)
        │
        ├─► Stage A  backend/nexus/shortlist.py   deterministic shortlist (15) from documented overlap + BM25 text relevance
        │            every point of score is tied to an evidence id
        ├─► Eligibility  shortlist.eligibility_concerns   concerns quoted from the funder's own eligibility text
        │
        └─► Stage B  backend/nexus/agent.py   PydanticAI agent (NativeOutput → MatchResult)
                     tools: get_faculty_dossier, find_in_shortlist (shortlist only)
                     output_validator: unknown faculty / evidence ids → ModelRetry
                     post-checks: unsupported claims removed; eligibility notes kept only if quoted verbatim
                     no model/key → rule_based_result (same structure, labelled "Rule-based suggestion (no AI)")
        ▼
Recommendation document (service.py)  →  data/nexus.db (cache + model-call log)  →  /api/nexus
```

## Step 1: Retrieval tools (`retrieval.py`, `GET /api/nexus/faculty/search`)
You can search by research expertise, methodology, school or department, YIGH priority, geography (wider regions count: Kenya ↔ East Africa ↔ Sub-Saharan Africa), and projects. Every hit returns evidence items: an id, the quote, whether it's quoted profile text or a rule-based tag that quotes it, and the profile's **source URL**.

*Limitation:* publication lists were not collected from profiles. "Projects" covers research activities listed on profiles (titles, dates, places, summaries) and bio text.

## Step 3: What a recommendation contains
- **Top 5 faculty:** match score, Stage A score, explanation (hypothesis), documented evidence with source URLs.
- **Up to 3 teams:** a proposed role and contribution for each member (hypothesis), documented evidence, requirements covered, missing expertise, schools, and **verified existing co-authors** (taken only from the Yale Co-Authors lists).
- **Strategic alignment:** the opportunity's documented rule-based priorities with explanations, plus an assessment (hypothesis).
- **Missing capabilities, eligibility concerns** (each with the funder's quote), **overall match score and explanation**.
- **Sources:** the official opportunity URL and every profile URL used.
- **Validation:** unsupported claims removed, eligibility notes dropped, any model error.
- **Notes:** a statement that nothing in the recommendation says anyone is interested, available or eligible.

## Step 4: Keeping recommendations updated
The cache key is a hash of:
- the opportunity's content hash,
- fingerprints of the shortlisted faculty profiles,
- the generator (model id, or "rules"),
- the prompt version.

| Trigger | How |
|---|---|
| New opportunity, or a material requirement change | `Matcher.refresh_after_radar_run()`, run by the weekly workflow after discovery. A changed content hash means a new key |
| Faculty profile updated | `POST /api/nexus/refresh?trigger=faculty_updated` reloads profiles. Only opportunities whose shortlisted profiles changed get a new key |
| Administrator request | `POST /api/nexus/opportunities/{id}/refresh` (`force=true`) |

Unchanged inputs are served from the cache, with no model call and no cost.

## Step 5: Evaluation and logging
`python -m backend.nexus.evaluate pool` and then `score` (results in `data/nexus_eval/report.json`; summary in `docs/nexus-evaluation.md`). Every model call is logged in `data/nexus.db` with model, latency, request count, input, output and cache tokens, estimated cost (Claude Opus 5.5 at $4 / $20 per million tokens) and errors: `GET /api/nexus/model-calls`.

## Configuration
- `NEXUS_MODEL` (default `anthropic:claude-opus-5-5`)
- `ANTHROPIC_API_KEY`: without it, the rule-based path is used and the output says so.
- `NEXUS_DB_PATH`
