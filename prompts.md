# Prompts Log

## Prompt 1 — 2026-10-25

I'm currently a student fellow for the Yale Institute for Global Health. YIGH is trying to do multiple things - strengthen linkages between faculty and their work, create opportunities for students, support leadership by training leaders but also supporting leaders in global health and creating partnerships with the opportunity for bidirectional exchange. For this I want to build an app that has two things 1.  constellation - a  collaboration matchmaking that helps faculty and students discover collaborators across schools based on research interests, geographic focus. and 2) global health radar which helps the institute and faculty discover relevant grants and funding opportunities from big grant makers (foundations).  We'll use React + Vite + TypeScript for the frontend, Python + FastAPI for the backend, and a lightweight database. I'll give you prompts, please keep them on a prompts

## Prompt 2 — 2026-10-25

Visit this directory and extract every listed affiliated faculty.  For each person, collect Name, title, school and department, geographic focus, bio, focus area, email (if publicly listed),put  the data you find in faculty.json

## Prompt 3 — 2026-10-25

now, extract all major global health grantmakers like rockefeller, coefficient giving, mastercard foundation, macarthur foundation, wellcome trust, etc. Put it in opportunities.json

## Prompt 4 — 2026-10-25

Yes, research current open calls for these funders and add them to opportunities.json

## Prompt 5 — 2026-10-25

actually, build an agent opportunities.py that searches for grant opportunities from major global health grantmakers like rockefeller, coefficient giving, mastercard foundation, macarthur foundation, wellcome trust, etc. The agent should put the outputs in opportunities.json

## Prompt 6 — 2026-10-25

are you limiting it to those funders only or other major ones too?

## Prompt 7 — 2026-10-25

ok now let's work on the constellation. Help me design the architecture for it. The application needs to store faculty profiles, research expertise, geographic interests, strategic priority classifications, funding opportunities, and potential collaboration matches.
The four YIGH strategic priorities are:

* Climate & Health
* Digital Health & AI
* Health Diplomacy & Security
* Health Sovereignty

Please design a SQLite database schema that supports both Constellation and Global Health Radar.
Each faculty profile should include a name, Yale school or department, research interests, geographic focus when documented, strategic priorities, and source URL. Create the database models and initialization scripts. Include clear relationships between faculty, research interests, opportunities, and matches.

## Prompt 8 — 2026-10-25

Using the verified faculty profiles in our database, classify each faculty member according to the four YIGH strategic priorities:

1. Climate & Health
2. Digital Health & AI
3. Health Diplomacy & Security
4. Health Sovereignty

Faculty can belong to multiple categories.
Also extract standardized research keywords and geographic interests when they are explicitly supported by their profiles.
Start with a transparent, rule-based approach using keyword matching and research descriptions. Keep the original source text separate from generated classifications.
For every classification, store an explanation and the supporting evidence. Include a confidence score, but do not present it as a statistically calibrated probability.

## Prompt 9 — 2026-10-25

Let's build Constellation's faculty collaboration matching engine.
The goal is to recommend meaningful research collaborations between Yale faculty members who may not already know each other.
I don't want the system to simply match people who work on identical topics. It should also identify complementary expertise that could lead to interesting interdisciplinary collaborations.
Build a matching algorithm that considers:

* Overlapping research interests
* Complementary expertise
* Shared or related geographic interests
* Alignment with YIGH's four strategic priorities
* Opportunities for cross-school collaboration

Create a transparent scoring system using weighted criteria. Make the weights configurable.
For every recommended match, generate an explanation based on documented evidence, such as shared research themes or complementary methodological expertise.
Do not invent research interests or claim that faculty have previously collaborated unless verified.
Implement a FastAPI endpoint that returns ranked collaborators for a selected faculty member.

## Prompt 10 — 2026-10-25

(Shared a dark "knowledge graph" UI screenshot as visual reference.)

Now create the Constellation frontend using React and TypeScript.
Build a faculty discovery interface with:

* A searchable faculty directory
* Filters for Yale school, research area, strategic priority, and geography
* Faculty profile cards
* A detailed faculty profile view
* A "Find Collaborators" action
* A ranked list of recommended collaborators

Each recommendation should display a compatibility score, overlapping interests, complementary expertise, and a short explanation of why the collaboration might be valuable.
Make the interface intuitive for faculty and YIGH staff who may not have technical backgrounds.
Connect the frontend to the existing FastAPI endpoints and use actual database records, not hardcoded faculty examples.
Include loading, empty, and error states.
Test the main interactions before proceeding.

## Prompt 11 — 2026-10-25

(Shared the same knowledge-graph screenshot as visual reference.)

I want to add a distinctive visual feature to Constellation: an interactive faculty collaboration network.
Represent faculty members as nodes in a network, with connections indicating potential research compatibility.
Requirements:

* Each node represents a faculty member.
* Node colors represent their primary YIGH strategic priority.
* Connections represent algorithm-generated potential matches, not verified existing collaborations.
* Connection thickness reflects the matching score.
* Users can zoom, pan, and select faculty.
* Selecting a faculty member highlights their strongest potential collaborators.
* Clicking a connection displays the explanation behind the match.
* Filters allow users to explore different research areas and Yale schools.

Use a suitable React-compatible network visualization library, such as React Flow or Cytoscape.js.
Keep the network readable and performant with 20–30 faculty members.
Make sure the visualization uses data from the backend.
Include an accessible list-based alternative to the network.
Do not change the existing matching algorithm unless necessary.

## Prompt 12 — 2026-10-25

ok run the app for me

## Prompt 13 — 2026-10-25

use the branding of this site for the formatting: https://medicine.yale.edu/yigh/faculty-support-initiative/affiliated-faculty/

## Prompt 14 — 2026-10-25

what else would be relevant to take from this site for the constellation? additionally, could you're https://medicine.yale.edu/yigh/

## Prompt 15 — 2026-10-25

Yes, extend the scraper to capture profile activities, Yale co-authors and organization memberships, and use them in Constellation

## Prompt 16 — 2026-10-25

instead of a view profile tab that would take you to a new page, add a "click to expand" option to view their bios

## Prompt 17 — 2026-10-25

use playwright to click through the pages and ensure its correct logically.  please double check to make sure that no faculty have been miscategorized to a different research area, priorities, etc

## Prompt 18 — 2026-10-25

browse faculty directories from YSPH as well and include any faculty members that have global health projects. Audit faculty tags for these ones too and : https://ysph.yale.edu/school-of-public-health-faculty/

## Prompt 19 — 2026-10-25

Okay now for the second component - Build an autonomous funding opportunity discovery system for the site..
Objective: Every week, the system should discover new global health research funding opportunities, verify their details, and update a persistent opportunities database and user-facing feed.
Use YIGH's four strategic priorities as the discovery framework: 1. Climate & Health 2. Digital Health & AI 3. Health Diplomacy & Security 4. Health Sovereignty
Step 1: Build a source registry (NIH, Grants.gov, Wellcome, Gates Foundation, Grand Challenges, philanthropic/multilateral; official URL, API/RSS/webpage, collection method; prefer APIs/feeds; respect robots.txt, access restrictions, rate limits).
Step 2: Python discovery pipeline (search sources; extract title, funder, description, deadline, award amount, eligibility, geographic restrictions, application URL; detect new/updated; duplicates; verify against official sources; flag incomplete/uncertain for review; record retrieval timestamps and source URLs). Never invent funding amounts, deadlines, eligibility, or status.
Step 3: SQLite database (opportunities, organizations, source URLs and verification history, discovery timestamps, status, changes since previous scan, strategic-priority classifications; stable identifiers and upserts).
Step 4: Schedule (GitHub Actions every Monday + manual trigger; idempotent; tolerate source failures; run summary; daily lightweight deadline check).
Step 5: FastAPI endpoints (all, new, updated, closing soon, by priority, details + verification status).
Step 6: Tests with fixtures/mocks (first discovery, duplicates, deadline changes, closed, unavailable sources, missing eligibility, malicious instructions in pages).
Do not build the frontend yet. First demonstrate that running the pipeline twice does not create duplicates and that a changed funding deadline is correctly detected.

## Prompt 20 — 2026-10-25

Build a faculty intelligence and matchmaking agent for YIGH Nexus that automatically evaluates new and updated funding opportunities against the Yale faculty database.
Objective: For every relevant funding opportunity, recommend a potential interdisciplinary team of Yale researchers and explain why each researcher could contribute.
Use the faculty profiles collected from the official YIGH affiliated faculty directory: https://medicine.yale.edu/yigh/faculty-support-initiative/affiliated-faculty/
Step 1: faculty retrieval tools (research expertise, methodology, school/department, strategic-priority alignment, geographic research experience, publications and projects). Only documented information; preserve source URLs.
Step 2: two-stage matching. Stage A deterministic/semantic shortlist. Stage B PydanticAI agent evaluates shortlist and builds complementary interdisciplinary teams (subject expertise, methods, diversity, geography, documented eligibility).
Step 3: per opportunity: top five faculty; up to three teams; role per researcher; evidence; YIGH strategic alignment; missing expertise/capabilities; eligibility concerns; match score + explanation; source URLs. Distinguish documented expertise from AI-generated hypotheses. Never claim interest, availability, eligibility or collaboration without evidence.
Step 4: rerun when new opportunity / material requirement change / faculty profile update / admin refresh. Cache unchanged results.
Step 5: evaluation vs keyword baseline (retrieval relevance, team complementarity, eligibility accuracy, source grounding, unsupported claims). Log model calls, latency, tokens, cost.
Build the matching API and tests. Demonstrate one complete workflow from a real, verified funding opportunity to a proposed interdisciplinary Yale research team.

## Prompt 21 — 2026-10-26

Build an external partner discovery agent for YIGH Nexus. For each funding opportunity and proposed Yale faculty team, identify credible external organizations that could strengthen the collaboration (local expertise, implementation capacity, geographic eligibility).
Step 1 categories: universities/research institutions; ministries of health/public health agencies; regional & multilateral organizations; NGOs/implementation partners; healthcare & technology organizations; existing Yale/YIGH institutional partners (publicly documented).
Step 2: research via official websites, verified project pages, publications, documented collaborations. Extract name, country/presence, type, expertise, relevant projects, documented Yale partnerships, website, evidence URLs, last verification date. Do not infer partnerships from shared interests.
Step 3: up to five partners per team; explain relevance, capabilities, complementarity, geographic/partnership requirements, documented vs proposed relationship, what needs verification. Prioritize locally led and reciprocal partnerships. Never imply agreement to collaborate.
Step 4: SQLite partner DB, dedupe, monthly refresh, avoid unnecessary repeated searches.
Step 5: integrate with opportunity feed (details, faculty, teams, partners, eligibility/collaboration gaps, evidence links). Tests for fabricated partnerships, outdated info, mismatched geography, unsupported recommendations. Working workflow integrated with Radar and Constellation APIs.

## Prompt 22 — 2026-10-26

Update the frontend to a polished, responsive React + Vite + TypeScript frontend for YIGH (academic research intelligence aesthetic, Yale identity: deep navy, white, subtle blue, clean type, generous spacing). Pages: 1) Dashboard (YIGH overview, strategic priorities, verified opportunities, faculty records, recent matches). 2) Opportunity Radar (search; filters priority/funder/deadline/geographic eligibility/status; weekly brief fed by the weekly agent search linking grants, faculty, partners; eligibility, deadlines, source evidence, "Find a Team"; a launchpad proposing interdisciplinary teams per proposal and generating a one-page research concept aligned with grant requirements). 3) Constellation (merge directory + connections; for students/faculty/staff to search faculty and see interconnections with React Flow; nodes = researchers, disciplines, research themes; distinguish documented vs AI-proposed connections). Connect to FastAPI; no hardcoded fictional data. Build incrementally, checking each page works.

## Prompt 23 — 2026-10-26

How about coefficient giving, rockefeller, macarthur big bets, gates foundation etc

## Prompt 24 — 2026-10-26

What other grantmakers are on the agents watchlist?

## Prompt 25 — 2026-10-26

can you add them to the agents watchlist?

## Prompt 26 — 2026-10-26

ford foundation and others?

## Prompt 27 — 2026-10-26

now update the back+frontend

## Prompt 28 — 2026-10-26

remove the constellation part. make it a faculty directory page w priorities and their bio

## Prompt 29 — 2026-10-26

make them boxes. bring the filters up, horizontally

## Prompt 30 — 2026-10-26

we lost their geographic focus too

## Prompt 31 — 2026-10-26

request failed

## Prompt 32 — 2026-10-26

(screenshot of Dashboard "This week's discovery" and "Recent matches") these two tabs are confusing. label them correctly. remove "rule-based" and replace with potential external partners. Move the recent matches to the "opportunities tab", in place of the weekly brief

## Prompt 33 — 2026-10-26

(attached draft_YIGH Strategic Plan_2025-2026_Review&Recommendations.docx) for the dashboard, rename it home page and build it like this with info about yigh and strategic priorities: https://www.speakupafrica.org/

## Prompt 34 — 2026-10-26

(attached draft_YIGH Strategic Plan_2025-2030.pdf)

## Prompt 35 — 2026-10-26

for the opportunities tab, use this as a model for the structure, but keep the different components: https://www.opensocietyfoundations.org/grants/past

## Prompt 36 — 2026-10-26

replace "Connecting Yale for Global Health" with "Hub for Global Health at Yale"

## Prompt 37 — 2026-10-26

in the oppotunities tab, only have one dashboard, not two, that has all the components listed

## Prompt 38 — 2026-10-26

(screenshot of the Opportunities filter block) make this dropdown

## Prompt 39 — 2026-10-26

make it pretty like you did the home page

## Prompt 40 — 2026-10-26

remove the "where YIGH works with partners" segment

## Prompt 41 — 2026-10-26

pretty up the faculty directory page as well

## Prompt 42 — 2026-10-26

replace "explore funding opportunities" on the home page with "explore opportunities hub"

## Prompt 43 — 2026-10-26

(screenshot of the two hero buttons) delete this and also the "invalid date" at top of the news articles

## Prompt 44 — 2026-10-26

(screenshot of the "Latest from YIGH" news cards) move to the bottom of homepage

## Prompt 45 — 2026-10-26

replace with "Where Yale  brings distinctive expertise"

## Prompt 46 — 2026-10-26

require a login for the launchpad section. add a sign in option on the dashboard

## Prompt 47 — 2026-10-26

(screenshot of the Institutional Pillars section, plus a reference image of a four-pillar temple graphic) also can you make this more visual, like roman pillars etc

## Prompt 48 — 2026-10-26

(image of a blue four-column temple: "Yale Institute for Global Health" roof; 1 Partners, 2 Leaders, 3 Innovators, 4 Scholars with icons) integrate this instead, make it animated

## Prompt 49 — 2026-10-26

for the login, hash the passwords for protection

## Prompt 50 — 2026-10-26

delete the "our approach" part.  use that formatting (color/bkgd) for the tools on this site section

## Prompt 51 — 2026-10-26

animate the whole home page

## Prompt 52 — 2026-10-26

hide the funder watchlist page. Instead, if a person selects a funder on the filter, give them feedback on the last time the opportunity opened or when its opening again

## Prompt 53 — 2026-10-26

make the words on the build a team page more normal, human words. dont use words like "documented evidence" or "documented approach"

## Prompt 54 — 2026-10-26

also wipe the website off of any words like that, replace with normal words. Another example  is "rules-based no AI"

## Prompt 55 — 2026-10-26

also build an agent that users can chat with in the chat bot to find what they need. Give it access to everything on the website

## Prompt 56 — 2026-10-26

make the pillars on the home page more vector like instead of cylindrical

## Prompt 57 — 2026-10-26

(screenshot of the Tools on this site section) replace "the plan calls for more..." with "explore the tools on our site to help you connect with resources at the institute and externally"

## Prompt 58 — 2026-10-26

remove the numbers, replace the subtext with something that sounds a bit more human

## Prompt 59 — 2026-10-26

add another tab to the dashboard called "team launchpad" aligned with the rest of the websites formatting. The frontend it should have a slot to add a link to an opportunity or select from the list of opportunities that already exist in the opportunities hub. In the backend, link it with the agent that finds the find most fitting faculty to reach out to and external partners to work with. also create an agent that could help create a one pager based on the opportunity and a few bullet points of what the user wants to accomplish.

## Prompt 60 — 2026-10-26

remove this from team launchpad AN OUTLINE TO FILL IN: IT LISTS WHAT THE CALL ASKS FOR AND WHO COULD DO WHAT (NO AI WAS USED)

## Prompt 61 — 2026-10-26

okay now use playwright to click through one by one and correct any logical issues

## Prompt 62 — 2026-10-26

remove the blend on homepage right underneath the blue title block and make sure to apply the same across all pages. for the chatbot, give it a chirpy personality of a helpful desk assistant. Also take design inspirations from this page for the faculty directory: https://www.speakupafrica.org/our-team/

## Prompt 63 — 2026-10-26

(screenshot of the filter panel overlapping the hero) noooo keep the hero wave, just make sure none of the website contents overlap with it

## Prompt 64 — 2026-10-26

(screenshot of the vision quote in the Faculty Directory hero) delete the quotes

## Prompt 65 — 2026-10-26

find the faculty pictures from their yale pages and add it. If you cant find it, add a generic profile pic

## Prompt 66 — 2026-10-26

(screenshot of the Home hero) remove the light blue blurry part at the bottom of the hero wave

## Prompt 67 — 2026-10-26

make sure the front and back end are both updated

## Prompt 68 — 2026-10-26

(screenshot of the assignment submission table: GitHub repo, report.html, slides.html, optional demo video) Here is what i need to submit for this assignment. You have access to my github, create a public repo with the front and backend

## Prompt 69 — 2026-10-26

(link) https://zlisto.github.io/mgt_409_fa26/project_requirements.html#repo

## Prompt 70 — 2026-10-26

(screenshot of Nexi misreading "who can i collaborate with that works on climate and health in kenya?") bro this chatbot is so dumb, please make it smart. embed an ai agent within it

## Prompt 71 — 2026-10-26

use the .env in the homework files if is not working for you

## Prompt 72 — 2026-10-26

update the github repo with the new upgrades

## Prompt 73 — 2026-10-26

does the git repo follow these instructions? https://zlisto.github.io/mgt_409_fa26/project_requirements.html#repo

## Prompt 74 — 2026-10-26

ok now help me draft a report in html following these instructions and fulfilling every requirement (except for maybe the feedback part). It should be 10-15 pages double spaced and in normal size font when printed: https://zlisto.github.io/mgt_409_fa26/project_requirements.html#report
