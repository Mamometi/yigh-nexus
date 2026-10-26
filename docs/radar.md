# Global Health Radar — funding discovery system

Every Monday, the Radar finds global health funding opportunities from official sources. It checks the details against those sources and records what's new or changed in `data/radar.db`. A daily job closes opportunities whose deadline has passed and reports which ones close soon.

**Ground rule:** every deadline, amount, eligibility statement and status is copied from an official source. Missing or uncertain values are left empty, and the opportunity is flagged for review. Nothing is guessed.

## 1. Source registry — `config/radar_sources.json`

| Source | Access method | How it's collected |
|---|---|---|
| **Grants.gov** | Official REST API (`search2`, `fetchOpportunity`; no key needed) | Searched with the YIGH priority query sets. Each result is read from the official detail record. Covers all US federal funders: NIH including Fogarty, CDC, the State Department's global health bureau, and others |
| **NIH Guide** | Official RSS feed | New RFAs, PARs and PAs are looked up on Grants.gov by number, so they get structured, verified details. Notices are skipped |
| **IDRC** | Server-rendered listing (no API or feed) | Each call page is read from IDRC's site. Values are taken only from labelled text, and the snippet is kept as evidence |
| Wellcome, Gates Grand Challenges, Grand Challenges Canada, Fogarty, EDCTP3, Rockefeller | Change monitor | The pages are built by JavaScript or have no structured listing. When the content changes, it's queued for a person to review. No fields are extracted |
| Gates Foundation, Coefficient Giving, NIHR, Unitaid, CEPI | Manual | No open listing, a 403 response to automated requests (not worked around), or a URL that needs confirming |

**Polite access:**
- Every source is checked against its robots.txt, and any `Crawl-delay` is honoured (Wellcome asks for 10 s).
- Requests are spaced per site: 1 request/second for APIs, 5–10 s for web pages.
- Requests use a clear user agent and time out after 30 s.
- 429 and 5xx responses are retried with increasing waits.

## 2. Pipeline — `backend/radar/`

| Step | Where | What it does |
|---|---|---|
| Collect | `collectors/*.py` | Each source returns *candidates* with: title, funder, description, deadline (and the verbatim deadline text), award floor, ceiling and text, eligibility, geographic restrictions, application URL, official URL, retrieval time |
| Deduplicate | `pipeline.merge_candidates`, `find_existing` | Exact matches share a **stable uid**: `opp:<opportunity number>` (e.g. the same NIH NOFO from the RSS feed and Grants.gov), or `url:<hash>`. Near-duplicates are the same funder, a title similarity of at least 0.92 and the same or unknown deadline (e.g. a call re-announced at a new URL) |
| Upsert | `pipeline.upsert` | A new uid creates a record and a `created` change. Otherwise each material field is compared, and only real differences become `updated` change rows. Each run adds a sighting (source URL and timestamp) and a verification record |
| Verify | collectors | **Grants.gov:** the official detail record *is* the source, and the search listing's close date is cross-checked against it (a disagreement is marked `mismatch`). **Web pages:** each value must appear next to a label on the official page, and the snippet is stored (`partially_verified`) |
| Status | `apply_status`, recheck | Changes only on evidence: the source says closed, the deadline has passed, or Grants.gov returns 404 for the record. A source being down never closes anything. A web listing that drops a call flags it for review instead of closing it |
| Review flags | collectors and `upsert` | Missing deadline, amount or eligibility; forecast-only dates; RSS-only items; mismatches; instruction-like content found in the page |
| Classify | `pipeline.classify` | The same transparent YIGH priority rules as Constellation (rules-v3), with an explanation and evidence |

**Untrusted content:** pages are treated as data. Scripts, styles, comments and hidden elements are removed, and sentences that look like instructions to an AI or system ("ignore previous instructions", "mark as verified") are deleted before anything is extracted. The record is then flagged as suspicious and for review. No AI model reads page text, so injected text can't steer the pipeline.

**Sentinel values:** Grants.gov uses `2147483647` (the maximum integer) as a placeholder, and `0` or a blank field when an amount isn't stated. These are treated as "not stated".

## 3. Database — `data/radar.db`
`organizations`, `sources`, `discovery_runs` (with a JSON summary), `source_fetches` (per-source outcome), `opportunities`, `sightings` (where and when each was seen), `changes` (field-level history), `verifications` (history of checks against the official source), `opportunity_priorities` (classification with evidence), `page_snapshots` (monitored pages). The Radar has its own database file, so rebuilding faculty data never erases discovery history.

## 4. Scheduling — `.github/workflows/`
- **`radar-weekly.yml`:** runs Mondays at 11:00 UTC and can be started manually (optionally for specific sources). It runs the tests, then discovery, then commits `data/radar.db` and the summary, which also appears on the workflow page.
- **`radar-deadlines.yml`:** runs daily at 12:00 UTC with **no external requests**. It closes past-deadline records and reports what closes within 7, 14 and 30 days.
- Both use the same concurrency group, so they never write the database at the same time.
- A run is `partial` if some sources fail and `failed` only if all do.

Run locally:
```bash
.venv/bin/python -m backend.radar.run --mode weekly
.venv/bin/python -m backend.radar.run --mode deadlines
```

## 5. Feed API (`/api/radar`)

| Endpoint | Returns |
|---|---|
| `GET /opportunities?status=&priority=&q=&funder=&needs_review=` | All opportunities, soonest deadline first |
| `GET /opportunities/new?since=` | First seen in the latest weekly run (or since a date) |
| `GET /opportunities/updated?since=` | Changed in the latest weekly run, with old → new values |
| `GET /opportunities/closing-soon?days=30&priority=` | Open or forecasted, with a deadline within N days |
| `GET /opportunities/priority/{slug}` | Filtered by YIGH priority |
| `GET /opportunities/{id}` | Full details, verification history, sources, change log, priority evidence |
| `GET /review` | Flagged opportunities and changed monitored pages |
| `GET /runs/latest`, `GET /sources` | Run summaries and registry status |

## 6. Tests — `tests/radar/`
`.venv/bin/python -m pytest tests/radar` runs the pipeline against saved fixtures and mocked sources. Each scenario has its own test:
- first-time discovery
- the same opportunity from two sources
- re-announcement at a new URL
- running twice (no duplicates, no false changes)
- a deadline change
- a listing that disagrees with the official record
- a deadline passing
- a page that says closed
- an opportunity withdrawn from Grants.gov
- the closing-soon report
- an unavailable source
- missing eligibility
- malicious instructions in hidden elements, comments, scripts and visible text
- monitored-page changes
- every API endpoint
