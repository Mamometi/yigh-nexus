"""Transparent, rule-based classification of faculty profile text.

Everything here is plain data + regexes so the rules can be read and audited.
Bump RULE_VERSION whenever a rule changes; stored classifications record it.

Confidence scores are heuristic rule scores reflecting how much textual support
was found. They are NOT calibrated probabilities.
"""
from __future__ import annotations

from .plain import plain_explanation
import re
from dataclasses import dataclass, field

RULE_VERSION = "rules-v3"  # v3: fixes from the full manual audit (see docs/classification-audit.md)

# Fields in order of how directly they describe research focus.
# Weight multiplies a match's contribution to the score.
FIELD_WEIGHTS = {"research_interests": 1.0, "title": 0.9, "activities": 0.9, "bio": 0.8}
# Titles name appointments ("…and Pediatrics", "Epidemiology (Chronic Diseases)"), not research topics:
# they can support a strategic priority but are not used for research-area keywords.
KEYWORD_FIELDS = ("research_interests", "bio", "activities")

# ---------------------------------------------------------------- strategic priorities
# "core" terms name the priority area directly; "supporting" terms are related but
# ambiguous on their own. Assignment needs >=1 core term, or >=2 distinct supporting terms.

PRIORITY_RULES = {
    "climate-health": {
        "core": [r"climate change", r"planetary health", r"climate-sensitive", r"climatic",
                 r"climat\w*\s+(?:as|in|on|and)\s+(?:a\s+)?(?:\w+\s+){0,3}(?:transmission|emergence|spread|limiting)", r"extreme heat", r"heat[- ]related",
                 r"heat ?waves?", r"global warming", r"climate[- ]sensitive"],
        "supporting": [r"climate", r"environmental health", r"air pollution", r"air quality", r"wildfires?", r"floods?",
                       r"droughts?", r"extreme weather", r"environmental exposures?", r"particulate matter",
                       r"household air pollution", r"cookstoves?", r"clean cooking", r"food security", r"water and sanitation"],
    },
    "digital-health-ai": {
        "core": [r"artificial intelligence", r"machine learning", r"deep learning", r"digital health",
                 r"m-?health", r"mobile health", r"health informatics", r"clinical informatics",
                 r"biomedical informatics", r"telemedicine", r"telehealth", r"large language models?",
                 r"natural language processing", r"\bAI\b", r"technology-enabled", r"digital (?:tools?|interventions?)"],
        "supporting": [r"data science", r"electronic health records?", r"\bEHRs?\b", r"bioinformatics", r"computational",
                       r"predictive model\w*", r"big data", r"mobile phones?", r"text messag\w+", r"smartphones?"],
    },
    "health-diplomacy-security": {
        "core": [r"health security", r"global health security", r"pandemic preparedness", r"pandemics?",
                 r"humanitarian (?:assistance|response|crises|crisis|settings|health)", r"refugees?", r"contact tracing",
                 r"COVID-19 (?:\w+\s+){0,2}(?:equity|disparities)",
                 r"COVID-19 (?:response|surveillance|modell?ing|transmission|vaccin\w+|evaluations?|policy)",
                 r"health diplomacy", r"biosecurity", r"epidemic preparedness", r"outbreak response",
                 r"global health governance", r"international health regulations"],
        "supporting": [r"outbreaks?", r"epidemics?", r"emerging infectious", r"humanitarian", r"conflicts?(?! of interest)", r"refugees?", r"global governance", r"surveillance", r"health policy",
                       r"public health surveillance", r"preparedness", r"forced migration", r"human rights", r"COVID-19"],
    },
    "health-sovereignty": {
        "core": [r"health sovereignty", r"health systems? strengthening", r"local manufactur\w+",
                 r"research capacity", r"capacity[- ]building", r"capacity strengthening",
                 r"decoloni\w+", r"country[- ]led", r"self[- ]relian\w+", r"universal health coverage"],
        "supporting": [r"health systems?", r"health workforce", r"primary health care", r"health financing",
                       r"equitable partnerships?", r"local partners?", r"community health workers?",
                       r"training (?:of|for) (?:local|health)", r"ministr(?:y|ies) of health", r"access to medicines",
                       r"supply chains?", r"implementation science", r"in-country", r"local (?:health )?professionals",
                       r"train(?:ed|ing|s) (?:\w+\s+){0,3}(?:local|health workers|physicians|nurses|clinicians|providers)", r"\bD43\b"],
    },
}

# ---------------------------------------------------------------- standardized keywords
# standard name -> synonyms (regex). Matches are case-insensitive, word-bounded.

STANDARD_KEYWORDS = {
    "HIV/AIDS": [r"HIV", r"AIDS", r"antiretroviral"],
    "Tuberculosis": [r"tuberculosis", r"\bTB\b"],
    "Malaria": [r"malaria", r"plasmodium"],
    "Neglected Tropical Diseases": [r"neglected tropical", r"trypanosom\w+", r"leishmania\w*", r"schistosom\w+", r"sleeping sickness", r"chagas"],
    "Vector-Borne Disease": [r"vector[- ]borne", r"mosquito\w*", r"tsetse", r"dengue", r"zika"],
    "Infectious Disease": [r"infectious diseases?", r"infections?"],
    "COVID-19": [r"COVID-19", r"SARS-CoV-2", r"coronavirus"],
    "Vaccines & Immunization": [r"vaccin\w+", r"immuniz\w+"],
    "Antimicrobial Resistance": [r"antimicrobial resistance", r"antibiotic resistance", r"drug[- ]resistan\w+"],
    "One Health & Zoonoses": [r"one health", r"zoono\w+"],
    "Maternal & Child Health": [r"maternal", r"newborns?", r"neonatal", r"child health", r"infant (?:health|mortality|feeding)", r"perinatal", r"prenatal", r"breastfeeding",
                                r"pediatric(?:s|ians?)?", r"infants?", r"adolescent (?:health|medicine)",
                                r"children and adolescents", r"child and adolescent"],
    "Reproductive & Sexual Health": [r"reproductive", r"family planning", r"contracepti\w+", r"sexual health"],
    "Nutrition": [r"nutrition", r"human nutrition", r"malnutrition", r"undernutrition", r"stunting", r"obesity", r"food insecurity", r"diet(?:ary)?"],
    "Mental Health": [r"mental health", r"mental illness", r"psychiatr(?:y|ic|ists?)", r"depression", r"anxiety", r"PTSD",
                      r"post-?traumatic", r"psychological trauma", r"trauma[- ]informed", r"trauma exposure", r"suicid\w+", r"psychosis", r"schizophrenia"],
    "Substance Use": [r"substance use", r"addiction", r"opioids?", r"alcohol use", r"tobacco", r"smoking", r"drug use", r"people who inject drugs"],
    "Noncommunicable Diseases": [r"non-?communicable", r"\bNCDs?\b", r"chronic diseases?"],
    "Cardiovascular Disease": [r"cardiovascular", r"(?<!pulmonary )hypertension(?!, pulmonary)", r"heart (?:disease|failure)", r"cardiometabolic", r"stroke"],
    "Diabetes": [r"diabet\w+"],
    "Cancer": [r"cancers?", r"oncolog\w+", r"tumou?rs?"],
    "Global Surgery": [r"global surgery", r"surgical care"],
    "Emergency & Critical Care": [r"emergency medicine", r"emergency care", r"critical care", r"trauma care"],
    "Injury & Violence": [r"injury prevention", r"(?<!kidney )(?<!tissue )(?<!lung )(?<!liver )(?<!nerve )(?<!traumatic )injur(?:y|ies)\b(?! after)(?! in the)", r"violence", r"road safety", r"road traffic"],
    "Aging": [r"ag(?:e)?ing(?! face)", r"ageism", r"older adults", r"gerontolog\w+", r"dementia"],
    "Environmental Health": [r"environmental health", r"air pollution", r"environmental exposures?"],
    "Climate Change": [r"climate change", r"climate"],
    "Water & Sanitation": [r"sanitation", r"\bWASH\b", r"safe water", r"drinking water", r"clean water", r"water access"],
    "Health Systems": [r"health systems? (?:strengthening|research|performance|reform)", r"(?<!mental )(?<!maternal )(?<!child )health services",
                        r"primary (?:health )?care", r"health systems?"],
    "Health Policy": [r"health policy", r"policy (?:research|analysis|evaluation)", r"policymak\w+", r"policy[- ]relevant"],
    "Health Economics": [r"health economics", r"cost-effectiveness", r"economic evaluation", r"health financing"],
    "Health Equity": [r"health equity", r"health disparities", r"inequit\w+", r"social determinants"],
    "Health Workforce": [r"health workforce", r"community health workers?", r"nursing workforce", r"task[- ]shifting"],
    "Implementation Science": [r"implementation science", r"implementation research"],
    "Epidemiology": [r"epidemiolog\w+"],
    "Biostatistics & Data Science": [r"biostatistic\w+", r"statistical (?:methods|modeling)", r"data science", r"causal inference", r"bayesian"],
    "Genomics": [r"genomic\w*", r"genomes?", r"genome sequencing", r"genetic epidemiology", r"population genetics", r"genetic (?:diversity|variation|susceptibility)"],
    "AI & Machine Learning": [r"artificial intelligence", r"machine learning", r"deep learning", r"\bAI\b"],
    "Digital Health": [r"digital health", r"m-?health", r"mobile health", r"telemedicine", r"telehealth", r"health informatics", r"technology-enabled"],
    "Pandemic Preparedness & Health Security": [r"pandemic preparedness", r"pandemics?", r"health security", r"outbreaks?", r"epidemic preparedness"],
    "Humanitarian & Refugee Health": [r"humanitarian", r"refugees?", r"displaced (?:people|persons|populations)", r"migrant health"],
    "Global Health Ethics & Law": [r"bioethic\w+", r"(?:research|global health|medical|public health) ethics", r"health law", r"ethics", r"human rights"],
    "Medical Education & Training": [r"medical education", r"health professions education", r"nursing education", r"graduate medical education",
                                     r"global health education", r"residency (?:education|curricul\w+)", r"clinical training of",
                                     r"(?:establish|develop|launch|direct|build|lead)\w*\s+(?:\w+\s+){0,4}training programs?",
                                     r"(?<!vocational )training programs?", r"curricul(?:a|um)",
                                     r"\bD43\b", r"capacity[- ]building trainings?", r"curricul(?:a|um) (?:development|for)",
                                     r"train(?:ed|ing|s) (?:\w+\s+){0,3}(?:local|health workers|physicians|nurses|clinicians|providers)"],
}

# ---------------------------------------------------------------- geography
REGIONS = ["Sub-Saharan Africa", "East Africa", "West Africa", "Southern Africa", "North Africa", "Latin America",
           "Caribbean", "South Asia", "Southeast Asia", "East Asia", "Middle East", "Central America", "Central Asia",
           "Eastern Europe", "Pacific Islands", "Africa", "Asia", "LMICs", "low- and middle-income countries"]
COUNTRIES = ["Afghanistan", "Australia", "Canada", "Greece", "Italy", "Japan", "Korea", "South Korea", "Spain", "United Kingdom", "Germany", "France", "Switzerland", "Argentina", "Bangladesh", "Belize", "Benin", "Bhutan", "Bolivia", "Botswana", "Brazil",
             "Burkina Faso", "Burundi", "Cambodia", "Cameroon", "Chile", "China", "Colombia", "Costa Rica", "Cuba",
             "Democratic Republic of the Congo", "DRC", "Dominican Republic", "Ecuador", "Egypt", "El Salvador",
             "Eswatini", "Ethiopia", "Gambia", "Ghana", "Guatemala", "Guinea", "Haiti", "Honduras", "India",
             "Indonesia", "Iran", "Iraq", "Jamaica", "Jordan", "Kenya", "Kyrgyzstan", "Laos", "Lebanon", "Lesotho",
             "Liberia", "Madagascar", "Malawi", "Malaysia", "Mali", "Mexico", "Mongolia", "Morocco", "Mozambique",
             "Myanmar", "Namibia", "Nepal", "Nicaragua", "Niger", "Nigeria", "Pakistan", "Palestine", "Gaza", "Panama",
             "Papua New Guinea", "Paraguay", "Peru", "Philippines", "Puerto Rico", "Russia", "Rwanda", "Senegal",
             "Sierra Leone", "Somalia", "South Africa", "South Sudan", "Sri Lanka", "Sudan", "Syria", "Tajikistan",
             "Tanzania", "Thailand", "Timor-Leste", "Togo", "Tunisia", "Turkey", "Uganda", "Ukraine", "Uruguay",
             "Uzbekistan", "Venezuela", "Vietnam", "Yemen", "Zambia", "Zimbabwe"]
# Place-like strings that are not research sites.
GEO_NOT_PLACES = re.compile(r"Middle Niger|Niger (?:River|Delta)|Geneva,?\s+Switzerland|Guinea[- ]pigs?|Turkey (?:meat|bird)|"
                            r"\((?:Australia|Canada|UK|USA)\)|\b[A-Z][a-z]+ (?:Journal|Studies)\b")

# High-income countries are rarely a global-health research focus; they need a research sentence of their own
# (not an activity location or a long partner-country list) to count.
HIGH_INCOME = {"Australia", "Canada", "Greece", "Italy", "Japan", "Korea", "South Korea", "Spain", "United Kingdom",
               "Germany", "France", "Switzerland"}

GEO_ALIASES = {"DRC": "Democratic Republic of the Congo", "low- and middle-income countries": "LMICs", "Gaza": "Palestine"}

# A sentence only supports a geographic *research* interest if it contains a research cue...
GEO_RESEARCH_CUES = re.compile(
    r"\b(research\w*|stud(?:y|ies|ying)|project\w*|trials?|programs?|collaborat\w+|partner\w*|cohorts?|field ?work|"
    r"sites?|work(?:s|ed|ing)? (?:in|with|across)|conduct\w*|implement\w*|surveillance|interventions?|"
    r"investigat\w+|lead\w*|led|based in|clinic\w*|communit(?:y|ies)|populations?|outbreaks?)\b", re.I)
# ...and is not about the person's own education or background.
GEO_BIOGRAPHY_CUES = re.compile(
    r"\b(born|grew up|native of|raised|received (?:his|her|their) |earned|graduated|graduate of|alumn\w+|"
    r"degree|M\.?D\.?|Ph\.?D\.?|MPH|residency|undergraduate|medical school|completed (?:his|her|their))\b", re.I)


# ---------------------------------------------------------------- context filters
# Sentences about a person's own education, career history, service roles or publications are not
# claims about their research. They are skipped for every classifier (bio and activity text).
NON_RESEARCH_SENTENCE = re.compile(
    r"\b(?:received (?:his|her|their|a|an) (?:M\.?D|Ph\.?D|MPH|B\.?A|B\.?S|M\.?S|master|doctora|degree|bachelor|undergraduate|medical|nursing|training)"
    r"|earned (?:his|her|their|a|an)|graduated|graduate of|alumn\w+|degree in|master'?s (?:degree|in)|(?:MPH|MSc?|PhD|MD|DrPH|BA|BS) (?:in|from)"
    r"|completed (?:his|her|their) (?:residency|fellowship|training|internship|PhD|MD|degree|education)|residency (?:at|in)|internship|(?:attended|completed|graduated from) medical school"
    r"|undergraduate|postdoctoral (?:training|fellowship) at|trained (?:at|in)|born (?:in|and)|raised in|grew up|originally from|native of|lived in"
    r"|sabbatical|editorial board|associate editor|editor of|serves? on the (?:board|committee|council)|grant reviewer|study section|reviewer for"
    r"|taught (?:courses?|classes)|teaches courses?|course director|mentor(?:ed|s|ing)? (?:to |for )?(?:students|trainees)"
    r"|prior to (?:joining|graduate)|before joining|previously (?:served|held|worked) as|held (?:faculty|research) positions"
    r"|faculty member at|positions in|early in (?:his|her|their) career|biotech(?:nology)? industry|plans to|as an? (?:undergraduate|college student)"
    r"|has taught|taught|advised|advisor to|consultant (?:to|for)|consulted|in the (?:1[89]|20)\d0s|historical"
    r"|sabbaticals?|undergrad\w*|postdoctoral|post-doctoral|as a (?:post)?doctoral fellow|fellowship (?:in|at)"
    r"|during (?:his|her|their) (?:fellowship|residency|training)|(?:was|served as) (?:a )?(?:faculty|professor|assistant professor)"
    r"|faculty (?:in|at) [^.]* at the University|fellowship training|did (?:additional )?(?:fellowship|residency)|\bintern\b|law school"
    r"|trustee|on the board|comprises|faculty members in|co-produced|\bfilm\b|documentary|board[- ]certifi\w+|certification in"
    r"|(?:received|completed|has|with) (?:\w+ )?training in)", re.I)
# Citation-like sentences: publication titles, journals, publisher places.
CITATION = re.compile(r"\(\d{4}\)|\([^)]*\b(?:19|20)\d{2}\b[^)]*\)|\d+\s*\(\d+\):\s*\d+|\bJ\b [A-Z]|\bet al\b|\bjournal of\b|\bPLoS\b|\bBMC\b|\bLancet\b|\bJAMA\b|Circulation:|: [A-Z][\w ]+ (?:Press|Centre|Center)\b|\bdoi\b")
# Time-marker uses of "pandemic" ("since the pandemic") are not pandemic research.
PANDEMIC_AS_SUBJECT = re.compile(r"\b(?:evaluat\w+|model+ing|research|stud(?:y|ies|ied)|respon\w+|vaccin\w+|transmission|"
                                 r"surveillance|outcomes|impacts?|effects?|equity) (?:on|of|to|in|for|during)\b", re.I)
PANDEMIC_AS_TIME = re.compile(r"\b(?:since|during|before|after|amid|throughout|through|as)\s+the\s+(?:global\s+)?(?:covid(?:-19)?\s+)?pandemic", re.I)

# Proper names of institutions, funders, programs and journals are masked before matching,
# so "Yale Cancer Center", "National Institute of Mental Health" or "Yale New Haven Health System"
# don't create topic tags.
_INST_HEAD = (r"(?:Center|Centre|Institute|Institution|Department|Dept\.?|Office|School|College|Committee|Council|Program|Programme"
              r"|Foundation|Society|Association|Health System|Hospital|Journal|Initiative|Service|Scholars|Award|Fellowship|Network|Unit|Division|Board|Agency|Consortium)")
_CAP = r"(?:[A-Z][\w'&.\-]*|&|of|for|and|on|in|the|de)"
INSTITUTION = re.compile(rf"\b(?:[A-Z][\w'&.\-]*\s+(?:{_CAP}\s+)*)?{_INST_HEAD}\b(?:\s+(?:of|for|on)\s+(?:[A-Z][\w'&.\-]*\s+(?:and\s+|&\s+)?)*[A-Z][\w'&.\-]*)?")


def mask_institutions(text: str) -> str:
    """Replace institution names with spaces (same length, so match positions stay valid)."""
    return INSTITUTION.sub(lambda m: " " * len(m.group(0)), text)


_PLACE_WORDS = None


def _looks_like_title(sent: str) -> bool:
    """Publication/talk titles in bios: most longer words capitalised, ignoring place names
    (a list of countries is not a title) and requiring no ordinary sentence verbs."""
    global _PLACE_WORDS
    if _PLACE_WORDS is None:
        _PLACE_WORDS = {w for n in REGIONS + COUNTRIES for w in n.split()}
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z\-']+", sent) if len(w) > 3 and w not in _PLACE_WORDS]
    if re.match(r"\s*(?:She|He|They|Her|His|Their|Dr\.?|Professor|In|As|With|Since)\b", sent):
        return False
    if len(words) < 6 or re.search(r"\b(?:is|are|was|were|has|have|had|leads?|led|directs?|studies|works?|focus(?:es)?)\b", sent):
        return False
    return sum(w[0].isupper() for w in words) / len(words) > 0.75


def clean_title(title: str) -> str:
    """Faculty titles carry affiliate titles and department qualifiers, which aren't research claims:
    'Professor of Epidemiology (Chronic Diseases); Affiliated Faculty, Climate Change and Health'."""
    blank = lambda m: " " * len(m.group(0))  # same length, so quotes from the original title stay exact
    t = re.sub(r"Affiliated Faculty,[^;]*", blank, title)
    return re.sub(r"\([^)]*\)", blank, t)


def usable_sentence(field: str, sent: str) -> bool:
    if field in ("bio", "activities") and (NON_RESEARCH_SENTENCE.search(sent) or CITATION.search(sent)):
        return False
    if field == "bio" and _looks_like_title(sent):
        return False
    return True


RESEARCH_FOCUS = re.compile(r"\bfocus(?:es|ed|ing)? on\b|\b(?:research|stud(?:y|ies)|projects?|work|scholarship|investigat\w+|interests?)\b", re.I)


def is_list_mention(sent: str, span: tuple[int, int]) -> bool:
    """True when the matched term is one item of an enumeration ('… on malaria, HIV, nutrition, cognitive
    development …') or an example ('e.g. breast cancer'). A single such mention is weak evidence."""
    if RESEARCH_FOCUS.search(sent):
        return False  # "her research focuses on X, Y and Z" names the person's own topics
    s, _e = span
    return bool(re.search(r"(?:e\.g\.|for example|such as|ranging from)", sent[:s], re.I))


# ---------------------------------------------------------------- helpers

@dataclass
class Evidence:
    field: str
    term: str
    snippet: str
    span: tuple[int, int] = (0, 0)  # position within the sentence; used to drop nested matches
    sentence: str = ""              # full sentence (snippet may be shortened)

    def as_dict(self):
        return {"field": self.field, "term": self.term, "snippet": self.snippet}


@dataclass
class Result:
    label: str                       # priority slug / keyword name / region name
    confidence: float
    confidence_label: str
    explanation: str
    evidence: list[Evidence] = field(default_factory=list)


def _compile(terms):
    return [(t, re.compile(rf"(?<![\w-]){t}(?![\w-])", re.I if not re.search(r"[A-Z]{2}", t) else 0)) for t in terms]


_PRIORITY_RX = {slug: {k: _compile(v) for k, v in r.items()} for slug, r in PRIORITY_RULES.items()}
_KEYWORD_RX = {k: _compile(v) for k, v in STANDARD_KEYWORDS.items()}
_GEO_RX = [(n, re.compile(rf"(?<![\w-]){re.escape(n)}(?![\w-])")) for n in sorted(REGIONS + COUNTRIES, key=len, reverse=True)]


_ABBREV = re.compile(r"\b(Dr|Prof|Drs|St|Mr|Mrs|Ms|Jr|Sr|vs|al|e\.g|i\.e|U\.S|Ph\.D|M\.D|No)\.")


def sentences(text: str) -> list[str]:
    """Split into sentences without breaking after abbreviations such as 'Dr.' or 'e.g.'."""
    protected = _ABBREV.sub(lambda m: m.group(0).replace(".", "\u2024"), text)
    parts = re.split(r"(?<=[.!?;])\s+|\n+|\s*;\s*", protected)
    return [p.replace("\u2024", ".").strip() for p in parts if p.strip()]


def _snippet(sentence: str, span: tuple[int, int] | None = None, limit: int = 280) -> str:
    """The sentence, or a window of it that always contains the matched term."""
    if len(sentence) <= limit:
        return sentence
    start = 0 if not span else max(0, min(span[0] - limit // 3, len(sentence) - limit))
    piece = sentence[start:start + limit]
    return ("…" if start else "") + piece + ("…" if start + limit < len(sentence) else "")


def _find(texts: dict[str, str], rx_list) -> list[Evidence]:
    """All (field, term, sentence) hits, one per distinct term per field."""
    out, seen = [], set()
    for fld, text in texts.items():
        for sent in sentences(text):
            if not usable_sentence(fld, sent):
                continue
            scan = clean_title(sent) if fld == "title" else sent
            masked = mask_institutions(scan) if fld != "research_interests" else scan
            for term, rx in rx_list:
                m = rx.search(masked)
                if m and term.startswith("pandemic") and PANDEMIC_AS_TIME.search(sent) and \
                        len(re.findall(r"pandemic", sent, re.I)) == 1 and not PANDEMIC_AS_SUBJECT.search(sent):
                    continue
                if m and (fld, term) not in seen:
                    seen.add((fld, term))
                    out.append(Evidence(fld, sent[m.start():m.end()], _snippet(sent, m.span()), m.span(), sent))
    return out


def _drop_nested(hits: list[Evidence]) -> list[Evidence]:
    """Drop a hit contained in a longer hit from the same sentence
    (e.g. 'health systems' inside 'health systems strengthening') so it isn't counted twice."""
    def inside(a, b):
        return (a is not b and a.field == b.field and a.snippet == b.snippet
                and b.span[0] <= a.span[0] and a.span[1] <= b.span[1] and (b.span[1] - b.span[0]) > (a.span[1] - a.span[0]))
    return [h for h in hits if not any(inside(h, o) for o in hits)]


def label_for(score: float) -> str:
    return "high" if score >= 0.7 else "medium" if score >= 0.45 else "low"


def _weighted(hits: list[Evidence], per_term: float) -> float:
    best = {}
    for h in hits:  # count each distinct term once, at its strongest field
        best[h.term.lower()] = max(best.get(h.term.lower(), 0), FIELD_WEIGHTS.get(h.field, 0.7))
    return per_term * sum(best.values())


def _fields(hits):
    return sorted({h.field.replace("_", " ") for h in hits})


# ---------------------------------------------------------------- classifiers

def classify_priorities(texts: dict[str, str]) -> dict[str, Result]:
    out = {}
    for slug, groups in _PRIORITY_RX.items():
        core = _find(texts, groups["core"])
        kept = _drop_nested(core + _find(texts, groups["supporting"]))
        core, supp = [h for h in kept if h in core], [h for h in kept if h not in core]
        n_core, n_supp = len({h.term.lower() for h in core}), len({h.term.lower() for h in supp})
        if n_core == 0 and n_supp < 2:
            continue
        score = round(min(0.95, 0.25 + _weighted(core, 0.3) + _weighted(supp, 0.1)), 2)
        only_checkbox = all(h.field == "research_interests" for h in core + supp)
        if only_checkbox and not (len({h.term.lower() for h in core + supp}) >= 2 and core):
            continue  # a single self-selected interest with no description isn't enough for a strategic priority
        if only_checkbox:
            score = min(score, 0.5)
        parts = []
        if n_core:
            parts.append(f"{n_core} core term(s) ({', '.join(sorted({h.term for h in core}))})")
        if n_supp:
            parts.append(f"{n_supp} supporting term(s) ({', '.join(sorted({h.term for h in supp}))})")
        if only_checkbox:
            parts.append("only from several entries in the profile's research-interest list, without a supporting description")
        expl = (f"Matched {' and '.join(parts)} in the profile {' / '.join(_fields(core + supp))}. "
                + ("Assigned because at least one core term was found." if n_core else
                   "Assigned on supporting terms only (no core term), so treat as tentative."))
        out[slug] = Result(slug, score, label_for(score), plain_explanation(expl), core + supp)
    return out


# Short forms accepted only in the faculty member's own research-interest list (too ambiguous in prose).
INTEREST_LIST_TERMS = {
    "Aging": [r"aging", r"ageing", r"geriatrics?"],
    "Maternal & Child Health": [r"pediatrics?", r"adolescent", r"child health"],
    "Digital Health": [r"informatics"],
    "Noncommunicable Diseases": [r"chronic diseases?"],
    "Mental Health": [r"psychiatry", r"behavioral health"],
    "Health Systems": [r"health services", r"primary care"],
}
_INTEREST_RX = {k: _compile(v) for k, v in INTEREST_LIST_TERMS.items()}


def extract_keywords(texts: dict[str, str]) -> dict[str, Result]:
    texts = {k: v for k, v in texts.items() if k in KEYWORD_FIELDS}
    out = {}
    for name, rx in _KEYWORD_RX.items():
        hits = _find(texts, rx)
        if name in _INTEREST_RX and texts.get("research_interests"):
            extra = _find({"research_interests": texts["research_interests"]}, _INTEREST_RX[name])
            seen_terms = {(h.field, h.term.lower()) for h in hits}
            hits += [h for h in extra if (h.field, h.term.lower()) not in seen_terms]
        if not hits:
            continue
        if len(hits) < 2 and all(h.field in ("bio", "activities") and is_list_mention(h.sentence, h.span) for h in hits):
            continue  # a single mention inside an enumeration isn't evidence of research focus
        in_list = any(h.field == "research_interests" for h in hits)
        n_mentions = len(hits)
        # Listed by the faculty member themselves = strongest support; a single bio mention = weakest.
        score = 0.9 if in_list else 0.75 if n_mentions >= 2 or any(h.field == "title" for h in hits) else 0.5
        where = "listed in the profile's research interests" if in_list else f"mentioned in the profile {' / '.join(_fields(hits))}"
        out[name] = Result(name, score, label_for(score),
                           f"'{name}' {where} via term(s): {', '.join(sorted({h.term for h in hits}))}.", hits)
    return out


def extract_geography(texts: dict[str, str]) -> dict[str, Result]:
    """Only keep places tied to research activity; skip education/biography sentences."""
    out: dict[str, Result] = {}
    for fld, text in texts.items():
        for sent in sentences(text):
            if not usable_sentence(fld, sent):
                continue
            scan = GEO_NOT_PLACES.sub(lambda m: " " * len(m.group(0)), sent)
            if fld != "activity_locations":
                scan = mask_institutions(scan)
            matched_spans = []
            for name, rx in _GEO_RX:
                for m in rx.finditer(scan):
                    if any(a <= m.start() < b for a, b in matched_spans):
                        continue  # e.g. "Africa" inside "South Africa"
                    matched_spans.append((m.start(), m.end()))
                    canonical = GEO_ALIASES.get(name, name)
                    n_places = sum(1 for _n, _rx in _GEO_RX if _rx.search(scan))
                    if canonical in HIGH_INCOME and (fld == "activity_locations" or n_places >= 3):
                        continue
                    if fld == "activity_locations":
                        strength, why = 0.95, "listed as a location of a research/international activity on the profile"
                    elif fld == "research_interests":
                        strength, why = 0.9, "listed as a research interest"
                    elif GEO_BIOGRAPHY_CUES.search(sent) and not GEO_RESEARCH_CUES.search(sent):
                        continue
                    elif GEO_RESEARCH_CUES.search(sent):
                        cue = GEO_RESEARCH_CUES.search(sent).group(0)
                        strength, why = (0.6, f"named alongside research activity ('{cue}')")
                        if n_places >= 5:
                            strength, why = 0.4, f"named in a long list of {n_places} places alongside research activity"
                        if GEO_BIOGRAPHY_CUES.search(sent):
                            strength, why = 0.4, f"named with research activity ('{cue}') but the sentence also describes training/background"
                    else:
                        continue  # place mentioned without research context: not explicit support
                    ev = Evidence(fld, m.group(0), _snippet(sent, m.span()))
                    prev = out.get(canonical)
                    if prev:
                        prev.evidence.append(ev)
                        if strength > prev.confidence:
                            prev.confidence, prev.explanation = strength, f"{canonical} {why} in the profile {fld.replace('_', ' ')}."
                    else:
                        out[canonical] = Result(canonical, strength, "", f"{canonical} {why} in the profile {fld.replace('_', ' ')}.", [ev])
    for r in out.values():
        if len(r.evidence) >= 2:
            r.confidence = round(min(0.9, r.confidence + 0.15), 2)
            r.explanation += f" Supported by {len(r.evidence)} separate statements."
        r.confidence_label = label_for(r.confidence)
    return out


def region_kind(name: str) -> str:
    return "region" if name in REGIONS or name == "LMICs" else "country"
