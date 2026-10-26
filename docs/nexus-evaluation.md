# YIGH Nexus evaluation (2026-10-26)

**Setup:**
- 10 real, verified opportunities from the live Radar database, ranging from immunization capacity building and polio modelling to antimicrobial resistance, plus three deliberately poor fits for global health (US Embassy Libya, NIOSH mining robotics, state occupational surveillance).
- Each method's top 5 were pooled and shuffled, and **89 opportunity–faculty pairs** were judged **blind** for relevance on a 0–2 scale.
- Reproduce with `python -m backend.nexus.evaluate pool && python -m backend.nexus.evaluate score`.

## Retrieval relevance

| Method | Precision@5 | nDCG@5 | Mean relevance (0–2) |
|---|---|---|---|
| Keyword baseline (title words in profile text) | 0.467 | 0.387 | 0.69 |
| **Stage A** (documented-overlap shortlist) | **0.640** | **0.483** | **0.96** |
| Rule-based Stage B top 5 | 0.640 | 0.483 | 0.96 |
| AI Stage B (PydanticAI) | not run (no API key on this machine) | | |

On the three poor-fit opportunities, every candidate from every method was judged irrelevant (0), as it should be. The baseline returned results for only 9 of the 10 opportunities.

## Teams (rule-based Stage B, 30 teams)
| Measure | Result |
|---|---|
| Documented requirement facets covered | 98.9% |
| Departments per team | 1.97 |
| Schools per team | 1.47 |
| Overlap of members between alternative teams | 13% |
| Team members judged relevant | 58.5% |

## Grounding and claims
- 100% of recommended team members have at least one evidence item with a source URL.
- **0** unsupported claims (interest, availability, eligibility or collaboration) in generated text. Tests show that such claims are removed when a model produces them.

## Eligibility accuracy
12 labelled cases (LMIC-only lead, limited submission, career stage, citizenship, small-business-only, no higher-ed applicant type, "see NOFO", eligible cases): **precision 1.0, recall 1.0**.

## Cost logging
No model calls were made (no API key), so the cost was $0. With a key, every call is logged with latency, request count, input, output and cache tokens and estimated cost at Claude Opus 5.5 prices ($4 / $20 per MTok): `GET /api/nexus/model-calls`.

## Limitations
- **One judge, coarse reading.** The judge read about 400 characters of each opportunity and gave generic reasons, so these numbers indicate direction and aren't precise.
- **Stage A and rule-based top 5 are the same list.** The rule-based Stage B keeps Stage A's ranking, so it can't add retrieval quality on its own; only the AI arm can re-rank.
- **The AI arm needs `ANTHROPIC_API_KEY`.** The harness runs it automatically once the key is set.
