# External partner discovery (YIGH Nexus)

For each proposed Yale team, Nexus suggests up to five external organizations that could strengthen the collaboration, especially where local expertise or a locally based applicant matters.

## Sources (documented only)
| Source | What it gives | Relationship |
|---|---|---|
| **YIGH GHES research training-site pages** (15 countries) | Institution, country, research areas, site description; Yale faculty listed as US mentors (matched by name to the faculty database). Personal contact details are not stored | **Documented** (YIGH page URL) |
| **Yale faculty profile research activities** | An institution named in the activity text, confirmed by ROR's affiliation matcher in the activity's own country | **Documented**, at faculty level (profile URL) |
| **ROR registry search** (only when a team needs a partner in a country with none on record; `?discover=true`) | Official name, type, country, website | **Proposed**; expertise and capacity "need verification" |

**Rule:** a relationship with Yale is recorded only through `store.add_yale_link`, and it refuses to do so without a public `yale_partnership` or `project` evidence URL. Shared interests never create a relationship.

## Matching (`backend/partners/match.py`)
The partner score combines four weighted factors:

| Factor | Weight | How it's scored |
|---|---|---|
| Geography | 0.40 | A target country scores fully, a low- or middle-income country when the call targets "LMICs" scores 0.75, and the same wider region scores 0.5 |
| Documented expertise overlapping the opportunity | 0.25 | |
| Documented Yale link | 0.20 | Higher when it's with someone on the team |
| Locally based in a low- or middle-income country | 0.15 | Favours locally led, reciprocal partnerships |

Institution types are mixed in the top five. Each suggestion lists:
- why the organization is relevant;
- capabilities, each with an evidence quote and URL;
- how it complements the team;
- whether it helps meet a locally-based-applicant requirement;
- whether the relationship is documented or proposed, with evidence;
- what needs verification;
- when it was last verified, and a stale flag after 180 days.

Every suggestion also says that no organization has been contacted or has agreed to anything.

## Storage and refresh
`data/partners.db` holds `organizations`, `evidence`, `yale_links`, `lookup_cache` (ROR responses, kept 30 days) and `refresh_runs`.
- **Deduplication** by ROR ID, then by normalized name or alias within the same country.
- **Monthly refresh** by `.github/workflows/partners-monthly.yml` (`python -m backend.partners.run refresh`). Cached registry lookups avoid repeat requests.

## API
| Endpoint | Returns |
|---|---|
| `GET /api/partners?country=&type=&q=&documented=` | Search partner records |
| `GET /api/partners/{id}` | One record with evidence |
| `GET /api/faculty/{id}/partners` | Organizations documented as linked to a faculty member (shown in Constellation) |
| `GET /api/radar/opportunities/{id}/workspace` | The integrated view: opportunity details, recommended faculty, teams, partners per team, eligibility and collaboration gaps, alignment, all source links |

## Tests (`tests/partners`)
Fabricated partnerships (rejected without evidence; shared interests only gives "proposed"), never implying agreement, outdated records, mismatched geography, the local-partner gap, unsupported recommendations (no evidence means no recommendation), team-member ranking, deduplication, and registry caching.
