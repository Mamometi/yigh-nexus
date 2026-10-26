# Architecture: Constellation + Global Health Radar

```
 data sources                      ingestion                     storage            API / UI
 ───────────────                   ─────────────────────         ───────────        ─────────────────────
 YIGH faculty directory ──► scripts/scrape_faculty.py ──► data/faculty.json ─┐
                                                                             ├─► backend/scripts/init_db.py ─► data/yigh.db ─► FastAPI ─► React (Vite + TS)
 Funder websites ───────► scripts/opportunities.py  ──► data/opportunities.json ┘   (+ keyword priority tagging)        (SQLite)    /faculty  /matches  /radar
                          (Claude + web search)
```

- **Constellation** finds faculty and student collaborators across schools, using shared research interests, regions and strategic priorities.
- **Global Health Radar** lists funders and open calls, and matches each call to relevant faculty.

The two modules share the same lists of **research interests**, **regions** and **strategic priorities**. Faculty, funders and opportunities are all tagged from the same lists, so they can be matched on the same terms.

## Schema (`backend/app/models.py`)

```
schools ─┬─< departments
         └─< faculty >── departments (primary)
                │
                ├─< faculty_appointments >── departments
                ├─< faculty_interests    >── research_interests ──┐
                ├─< faculty_regions      >── regions ─────────────┤ shared vocabularies
                └─< faculty_priorities   >── strategic_priorities ┘
                                                   ▲  ▲  ▲
funders ─┬─< funder_interests / funder_regions ────┘  │  │
         └─< opportunities ─< opportunity_interests ──┘  │
                          ├─< opportunity_regions        │
                          └─< opportunity_priorities ────┘

collaboration_matches   faculty_a ── faculty_b   (one row per pair, a < b)
opportunity_matches     faculty   ── opportunity
```

| Table | Purpose |
|---|---|
| `faculty` | Name, title, email, bio, school, primary department, `source_url` (unique profile link) |
| `faculty_appointments` | Every primary and secondary appointment (department, title, type) |
| `research_interests` | Shared list of research topics |
| `faculty_source_texts` | **Source text, kept exactly as scraped** (title, bio, research-interest list, appointments) with source URL and retrieval date. Classifiers only read it. |
| `faculty_interests` | Links faculty to interests; `category` records which list on the profile the interest came from |
| `regions` | Countries and regions (`kind` = country / region / global) |
| `faculty_regions` | **Generated** geographic interests. Only places that the profile ties to research activity |
| `strategic_priorities` | The four YIGH priorities |
| `faculty_priorities` | **Generated** strategic priorities (a person can have several) |
| `standard_keywords` / `faculty_keywords` | **Generated** standardized research keywords from a fixed list |
| `funders` | Funder profiles; `source` = `curated` or `discovered` |
| `opportunities` | Specific calls: deadline, deadline type, amount, eligibility, whether US institutions can apply, status |
| `opportunity_*` | Links opportunities to interests, regions and priorities |
| `collaboration_matches` | Suggested faculty pairs: score, what they share, cross-school flag, rationale, method |
| `opportunity_matches` | Suggested faculty–opportunity fits with score and rationale |

## Classification (`backend/app/classification/rules.py`, `backend/scripts/classify_faculty.py`)

Source text and generated tags are kept apart. `init_db` stores only scraped data. `classify_faculty` reads `faculty_source_texts` and writes tags to `faculty_priorities`, `faculty_keywords` and `faculty_regions`. Every tag row records:

| Column | Meaning |
|---|---|
| `method` | `rules` (current), `llm` (later), or `manual`. Re-runs replace only `rules` rows; `manual` rows are never touched |
| `rule_version` | e.g. `rules-v1`; change it whenever a rule changes |
| `explanation` | Plain-English reason, e.g. "Matched 1 core term (pandemic) and 2 supporting terms…" |
| `evidence` | JSON list of `{field, term, snippet}`: the exact sentence from the profile |
| `confidence` / `confidence_label` | A rule-strength score with a high / medium / low label. **Not a calibrated probability**; the UI should show the label, not a percentage |

**Rules**
- **Priorities:** each priority has *core* terms and *supporting* terms. A priority is assigned when at least one core term is found, or two different supporting terms. Matches in the research-interest list count more than matches in the title, which count more than matches in the bio. A term found inside a longer matched term isn't counted twice.
- **Keywords:** about 40 standard keywords, each with a list of synonyms. A keyword the faculty member listed themselves gets high confidence; one mentioned once in the bio gets medium.
- **Geography:** a place is tagged only if it appears in the research-interest list, or in a sentence that also mentions research activity (studies, projects, collaborations, sites…). Sentences about education or background (birthplace, degrees, residency) are skipped. A single sentence gives medium confidence; two or more give high.

To check the results, use `data/classifications_review.json`, which lists every tag with its evidence for each person.

## Design decisions
- **SQLite + SQLAlchemy 2.0.** A single database file with no server to run. Moving to Postgres later only needs a new `DATABASE_URL`. Foreign keys are switched on for every connection.
- **Every generated tag records where it came from:** the method, rule version, explanation and evidence, so admins can override it with `method='manual'`.
- **Matches are stored, not calculated on every request.** A batch job (to be written) fills `collaboration_matches` and `opportunity_matches`. Each pair is stored once, which the `a < b` constraint enforces.
- **Re-runnable loading.** `init_db` updates rows by `source_url` (faculty) or `slug` (funders) instead of inserting duplicates. `--reset` rebuilds everything.

## Commands
```bash
.venv/bin/python -m backend.scripts.init_db --reset     # load source data
.venv/bin/python -m backend.scripts.classify_faculty    # generate classifications
```

## Collaboration matching (`backend/app/matching/`)

`GET /api/faculty/{id}/collaborators` returns a ranked list of possible collaborators. The score for each pair is calculated when you call the endpoint (`engine.py`):

**score = Σ weightᵢ × criterionᵢ**, where each criterion is between 0 and 1 and the weights are normalized to sum to 1.

| Criterion | Default weight | How it's scored |
|---|---|---|
| `shared_interests` | 0.25 | Standard keywords and profile-listed interests both people have. Each counts more the rarer it is among Yale faculty, so "Global Health" counts little and "Vector Biology" counts a lot. Overlap stops adding to the score after a couple of strong shared themes, so near-identical profiles don't push out complementary ones |
| `complementary_expertise` | 0.30 | (a) One person brings a **method** the other's profile doesn't mention (AI/ML, biostatistics, health economics, implementation science, genomics, ethics/law…), **but only if** they already share a specific topic, region or priority. (b) **Related topics** from a hand-written list with a stated reason, e.g. Climate Change ↔ Vector-Borne Disease |
| `geography` | 0.15 | The same country or region; or, at half strength, places in the same wider region (Kenya ↔ Uganda through East Africa) |
| `strategic_priorities` | 0.20 | YIGH priorities both people share, scaled by the lower of their two confidence levels |
| `cross_school` | 0.10 | 1 for different schools, 0.5 for the same school but different departments, 0 for the same department |

**Safeguards**
- A pair is recommended only if something substantive connects them. Being in different schools isn't enough on its own.
- Every reason quotes evidence from the stored profile text or the person's listed interests.
- Every response includes a disclaimer. The database holds no co-authorship or prior-collaboration data, so the engine never says two people have or haven't worked together.

**Configuration**
- Weights are in `config/matching_weights.json`; restart the API after editing.
- A single request can override them with `?w_complementary_expertise=0.5` and similar parameters.
- The list of method keywords, the related-topic pairs, the country-to-region map and the thresholds are in `backend/app/matching/config.py`.
- The default minimum score is 0.30.

**API**
```bash
.venv/bin/uvicorn backend.app.main:app --reload
```
- `GET /api/faculty?q=bell`: search faculty by name
- `GET /api/faculty/{id}/collaborators?limit=10&min_score=0.3&cross_school_only=true`
- `GET /api/matching/weights`: the current normalized weights

## Frontend (`frontend/`, React + Vite + TypeScript)

| Page | What it does |
|---|---|
| `/` Directory | Search across names, titles, bios and research interests, with filters for priority, school, research area and geography. Filters are stored in the URL, so a view can be shared. Shows faculty cards |
| `/faculty/:id` Profile | Splits **source** content (bio, listed interests, appointments) from **generated** tags; select a tag to see the explanation and quoted evidence. The *Find collaborators* button (or `?collaborators=1`) shows the ranked list, a star-map graph and an "other schools only" toggle |

Each match card shows a 0–100 compatibility score with a plain label (Strong / Good / Possible fit), a "why this pairing" sentence, overlapping interests, complementary expertise, shared priorities and places, and an expandable score breakdown with quoted profile text. Every view has loading, empty and error states (the error state has a retry button).

**Run locally** (two terminals, from the project root):
```bash
.venv/bin/python -m uvicorn backend.app.main:app --port 8000
```
```bash
cd frontend && npm run dev
```
Then open http://localhost:5173. Vite forwards `/api` to the API at `API_URL` (default `http://127.0.0.1:8000`).

## Collaboration network (`/network`)

**Backend:** `GET /api/network?school=&keyword=&priority=&size=25&edges_per_node=3` (`backend/app/matching/network.py`). It reuses `engine.score_pair` unchanged, and only decides what to display:
1. Filter faculty, skipping profiles with too few documented tags to match on.
2. Score every pair in a candidate pool of up to 90 people.
3. Keep the `size` people (5–40) whose top three suggested links are strongest.
4. Keep each person's `edges_per_node` strongest links.

An unfiltered request takes about 0.5 s. Every edge carries the same summary, highlights, breakdown and evidence as a collaborator match.

**Frontend:** Cytoscape.js (`NetworkGraph.tsx`, `pages/Network.tsx`), loaded only when the page is visited.
- Node colour = the person's highest-confidence YIGH priority (grey = none identified). Node size grows with the number of connections. Edge thickness = match score.
- Scroll to zoom, drag to pan, or use the +/−/fit buttons. Nodes can be dragged.
- Clicking a person highlights their 3 strongest suggested links and fades everything else. The side panel lists all their links in this view.
- Clicking a line opens the explanation: score, overlapping interests, complementary expertise, and the breakdown with quoted evidence.
- Filters: Yale school, research area, YIGH priority, and number of people shown (15–30). They are stored in the URL.
- **List view** (`?view=list`) is an accessible alternative: the same people and links as nested lists, with expandable explanations. The canvas is hidden from screen readers, and a note points them to the list view.
- The graph labels links as algorithm-generated suggestions, not verified collaborations, in its intro text, a banner and every explanation.

## Profile activities, Yale co-authors and organizations

`scripts/scrape_faculty.py` also captures three more profile sections:

| Profile section | Stored in (source data, unedited) | How Constellation uses it |
|---|---|---|
| **Activities** (title, type, dates, locations, synopsis) | `faculty_activities` | The listed locations become geographic tags with high confidence (0.95, *"listed as a location of a research/international activity"*). Titles and synopses feed the priority and keyword rules |
| **Yale Co-Authors** ("frequent collaborators of … published research") | `faculty_coauthors`, linked to directory records by profile URL | Treated as **verified existing collaboration.** Matches and network edges carry `already_coauthors`, shown as a "✓ Already co-authors" badge and dashed lines. *New connections only* (`new_connections_only=true`) hides those pairs. It doesn't change the score |
| **Other Departments & Organizations** | `organizations`, `faculty_organizations` | Text for the priority rules (e.g. "Climate Change and Health"). Organizations both people list count as a shared interest, weighted by how rare they are, so near-universal ones like YIGH count for almost nothing |

The classifier is now `rules-v2`. After re-scraping, run:
```bash
.venv/bin/python scripts/scrape_faculty.py
.venv/bin/python -m backend.scripts.init_db --reset
.venv/bin/python -m backend.scripts.classify_faculty
```

## YIGH Nexus frontend (React + Vite + TypeScript)
The app has three sections, all reading from the FastAPI backend (no hard-coded people, opportunities, scores or amounts):

| Route | Page |
|---|---|
| `/` | **Dashboard**: faculty, open and verified opportunities, partner institutions, items flagged for review, YIGH priority breakdown, this week's discovery run, recent matches |
| `/radar` | **Opportunity Radar**: the weekly brief (highlights, closing soon, open by priority, review queue) and searchable opportunities filtered by priority, funder, deadline window, geographic eligibility and status. Each card shows status, deadline, award (only if stated), verification, the official source and **Find a team** |
| `/radar/:id` | Opportunity workspace: 1 details · 2 recommended faculty · 3 proposed teams · 4 external partners · 5 eligibility and collaboration gaps · **Launchpad** (choose a team → one-page concept: an AI draft if a model is configured, otherwise an outline from documented facts) · 6 sources. Generated content carries a visible label |
| `/constellation` | Merged directory and network: search and filters, a results list, and a **React Flow** graph of researchers, disciplines and themes. Solid edges are documented (appointments, profile-quoting tags, green for Yale co-authors); dashed edges are algorithm-proposed. The side panel shows bio, documented partner institutions and edge evidence |
| `/faculty/:id` | Full profile with collaborator suggestions |
