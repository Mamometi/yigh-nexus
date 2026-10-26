# YIGH Nexus

**A funding and collaboration hub for the Yale Institute for Global Health (YIGH).**

YIGH Nexus helps Yale researchers go from a funding call to a team and a plan:

- **Opportunity Radar**: global health funding opportunities collected every week from official sources
  (Grants.gov, the NIH Guide, IDRC, MacArthur/Lever for Change and about 20 funder pages), checked against the funder's own record,
  and tagged with YIGH's four strategic priorities. Pick a funder to see when it last opened a call and whether a next round is announced.
- **Faculty Directory**: 281 YIGH-affiliated and Yale School of Public Health faculty with their priorities, research areas,
  places they work, biographies and photos, taken from their public Yale profiles.
- **Team Launchpad**: paste a link to any funding call (or pick one from the Radar), see which Yale faculty and partner
  organizations to reach out to, then turn a few bullet points into a one-page concept.
- **Nexi, the chat assistant**: a desk assistant on every page that can search everything on the site.

Built for the AI Foundations for Managers final project (MGT 409, Fall 2026).

---

## Run it locally (about 5 minutes)

You need **Python 3.11 or newer**. Node.js is **not** needed: the built website is included in `frontend/dist`.

```bash
git clone https://github.com/Mamometi/yigh-nexus.git
cd yigh-nexus
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn backend.app.main:app --port 8000
```

Open **http://localhost:8000**. That's it: one server runs both the website and the API.

### AI key (optional, but needed for the AI agents)

The app reads a `.env` file from the repo folder first, then from **one folder above it**. If you already keep the course
`.env` (with `PORTKEY_API_KEY`) one level up, nothing else is needed. Otherwise:

```bash
cp .env.example .env               # then paste your PORTKEY_API_KEY into .env
```

| Key | What it does |
|---|---|
| `PORTKEY_API_KEY` | Course key. All agents use **gpt-6-luna** through Yale's Portkey gateway. |
| `OPENAI_API_KEY` | Optional alternative, used only if `PORTKEY_API_KEY` is empty. |

**Without any key the app still works.** Each agent falls back to a basic, non-AI mode:
faculty and partner matching uses keyword overlap, the one-pager becomes a structured outline, and Nexi answers
common questions with keyword search.

### Signing in

The Team Launchpad's "paste a link" and "draft a one-pager" steps need a sign-in. Click **Sign in → Create an account**
and use any `@yale.edu` address (accounts are stored only on your computer, in `data/auth.db`).

### Data: real vs. test

The real data is included, so nothing has to be downloaded or scraped to run the app:

| File | Contents |
|---|---|
| `data/yigh.db` | 281 faculty profiles with their tags |
| `data/radar.db` | funding opportunities, sources and change history |
| `data/partners.db` | partner organizations and their documented Yale connections |
| `data/nexus.db` | cached team suggestions and one-pagers |
| `data/faculty_photos.json` | headshot links from public Yale profiles |

The test suite uses its own small fixture data (in `tests/`) and never touches these files or calls a real AI model.

---

## Development mode (optional)

Hot-reloading frontend, needs Node.js 20+:

```bash
python -m uvicorn backend.app.main:app --port 8000 --reload   # terminal 1
cd frontend && npm install && npm run dev                     # terminal 2 → http://localhost:5173
```

After changing the frontend, `npm run build` updates `frontend/dist`, which the backend serves.

### Tests

```bash
python -m pytest -q                                   # 61 backend tests (no network, no AI calls)
cd frontend && BASE_URL=http://localhost:8000 npx playwright test   # 26 click-through tests (app must be running)
```

### Refreshing the data

```bash
python -m backend.radar.run --mode weekly      # collect new funding opportunities
python -m backend.radar.run --mode deadlines   # close passed deadlines, flag ones closing soon
python -m backend.app.scrape_photos            # re-collect faculty photos
```

The same jobs run on a schedule on GitHub (`.github/workflows/`): opportunities every Monday, deadlines daily,
partners monthly.

---

## How it works

```
frontend/   React + Vite + TypeScript website (built copy in frontend/dist)
backend/
  app/        FastAPI app, faculty directory, rule-based classification, collaborator matching
  radar/      Opportunity Radar: collectors, verification, change detection, weekly pipeline
  nexus/      team-matching agent (shortlist + AI ranking) and the one-pager agent
  partners/   partner-organization matching (documented Yale links vs. new suggestions)
  launchpad/  Team Launchpad: link import and one-pager API
  assistant/  Nexi, the chat agent (tools = the site's own API)
  auth/       sign-in (PBKDF2-hashed passwords, HttpOnly session cookie)
  llm.py      picks the AI model (Portkey/gpt-6-luna by default) and loads .env
config/       funder watchlist, YIGH home-page content, matching weights
docs/         design notes, classification audit, agent evaluation
tests/        backend tests; frontend/e2e/ has the Playwright click-through
prompts.md    every prompt used to build the project
```

### The agents

| Agent | What it does | Without a key |
|---|---|---|
| Opportunity Radar | Finds, verifies and tracks funding calls weekly | (no AI needed) |
| Team matching (Nexus) | Shortlists faculty by documented profile overlap, then the AI ranks them, proposes teams and explains why | Keyword-overlap ranking |
| Partner matching | Suggests partner organizations, separating existing Yale connections from new suggestions | (no AI needed) |
| One-pager | Drafts a one-page concept from the call's requirements, the user's goals and the suggested team | Structured outline |
| Nexi (chat) | Answers questions by calling the site's API (search opportunities, funder timing, faculty, collaborators, teams, partners, YIGH info) | Keyword search |

### Safety rules built in

- Never invents amounts, deadlines, eligibility or opportunity status; empty fields stay empty.
- Never says a person is interested, available or eligible, or that an organization has agreed to anything.
  AI text is checked and unsupported claims are removed.
- Respects `robots.txt` and access restrictions when collecting data; funder pages that block automated access are listed for manual checks.
- Text from web pages is cleaned of instruction-like content before any AI sees it.
- Pages pasted into the Launchpad are kept apart from the shared Opportunities list and marked as not checked with the funder.

More detail is in [`docs/`](docs/).
