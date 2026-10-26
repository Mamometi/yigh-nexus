# Classification audit (rules-v3)

**Goal:** make sure faculty are not mis-tagged with research areas, YIGH priorities or places.

## How the audit was done
1. **First review.** Five reviewers read the verbatim profile text of all 251 YIGH faculty. They judged each of the 1,763 generated tags (priorities, research areas, places) against that text, flagging tags as wrong or clearly missing.
2. **Rule fixes.** The rules were changed to address recurring error patterns, never by editing individual people.
3. **Second review.** An independent reviewer judged (a) every tag the new rules removed that the first reviewers had not flagged, so that correct tags weren't being lost, and (b) every flagged tag that was still present.
4. **Re-scoring.** The rules were refined again and scored against both reviews.

## Results

| | Before (v2) | After (v3) |
|---|---|---|
| Tags reviewers judged wrong (212) still assigned | 212 | **43** |
| Correct tags that an earlier v3 draft removed (96) now restored | — | **66** |
| Faculty with ≥1 YIGH priority | 104 | 74 |

About 10 of the 43 remaining "wrong" tags are deliberate: research areas the faculty member listed themselves in their profile's research interests (e.g. "Cancer"). We keep the person's own claim even when the bio doesn't mention it; the tag's explanation says where it came from. Three more are archaeology field sites (real research locations, not health research).

## What the rules now do differently
| Problem found | Rule change |
|---|---|
| **Membership in a center** (e.g. "Climate Change and Health") alone produced priorities. This was the single largest error | Organization lists are no longer evidence for priorities or research areas. They are still used to find shared ground in matching |
| **Institution, funder, journal and committee names** ("Yale Cancer Center", "National Institute of Mental Health", "Yale New Haven Health System") | These names are masked before matching. Labs and clinics a person runs are not masked |
| **The person's own training** (degrees, residency, fellowship, postdoc, undergraduate work), career history, sabbaticals, teaching, editorial and board roles, consulting, films | Sentences like these are skipped. Training programs the person runs *for others* (D43, training local health workers) still count |
| **Citations and publication titles** in bios | Skipped (year in parentheses, volume(issue):pages, "Journal of…", title-case lines) |
| **"Pandemic" used as a time marker** ("since the pandemic") | Ignored, unless the sentence is about COVID research (evaluations, modeling, response, equity) |
| **Word-sense errors**: "trauma" (surgical), "kidney/nerve injury", "aging face", "pulmonary hypertension", "vocational training", "policy" (generic), "water" (incidental) | Narrower patterns |
| **Topics only named as examples** ("matters ranging from…", "e.g. breast cancer") | Not enough on their own, unless the sentence describes the person's own research |
| **Activities**: committees, journal service, peer review, and lecture locations | Only Research, Patient Care and Volunteer activities count as evidence |
| **High-income countries** from activity addresses or long partner lists | Not tagged as a geographic focus unless a research sentence of their own supports them |
| **A priority from one self-selected interest checkbox** with no description | Not assigned |
| **Joint appointments in titles** ("…and Pediatrics") | Titles are not used for research-area tags |
| **"Dr." splitting sentences**, so filters missed context | Fixed with abbreviation-aware sentence splitting |

## Known limits
- Rules still miss tags that are described only indirectly; recall matters less than precision here.
- Some calls are judgment calls (e.g. whether stroke counts as cardiovascular disease; we follow the AHA and count it).
- Audit working files are in the session scratchpad; the review file `data/classifications_review.json` lists every tag with its evidence for spot checks.
