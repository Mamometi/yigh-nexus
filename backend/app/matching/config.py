"""Configuration for collaboration matching: weights, expertise roles and related-topic pairs.

All of this is plain data so the scoring is auditable. Edit here (or in
config/matching_weights.json for weights) rather than in the engine.
"""
import json
from pathlib import Path

WEIGHTS_FILE = Path(__file__).resolve().parents[3] / "config" / "matching_weights.json"
CRITERIA = ("shared_interests", "complementary_expertise", "geography", "strategic_priorities", "cross_school")

DEFAULT_WEIGHTS = {"shared_interests": 0.25, "complementary_expertise": 0.30, "geography": 0.15,
                   "strategic_priorities": 0.20, "cross_school": 0.10}


def load_weights(overrides: dict | None = None) -> dict:
    """File weights (if present) <- per-request overrides, then normalized to sum to 1."""
    w = dict(DEFAULT_WEIGHTS)
    if WEIGHTS_FILE.exists():
        w.update({k: float(v) for k, v in json.loads(WEIGHTS_FILE.read_text()).items() if k in CRITERIA})
    w.update({k: float(v) for k, v in (overrides or {}).items() if k in CRITERIA and v is not None})
    if any(v < 0 for v in w.values()):
        raise ValueError("weights must be non-negative")
    total = sum(w.values())
    if total == 0:
        raise ValueError("at least one weight must be positive")
    return {k: round(v / total, 4) for k, v in w.items()}


# A match must have at least this much substantive signal (anything except cross-school)
# so that "different school" alone never produces a recommendation.
MIN_SUBSTANTIVE = 0.15
DEFAULT_MIN_SCORE = 0.30

# Shared-interest scoring saturates: beyond this many shared themes, more overlap adds nothing.
# This keeps near-identical profiles from crowding out complementary ones.
OVERLAP_SATURATION = 1.5  # in specificity-weighted units (a rare shared theme ~0.8)

# A shared topic must be at least this distinctive (0-1) to count as common ground for a methods complement.
MIN_CONTEXT_SPECIFICITY = 0.3

# ---------------------------------------------------------------- expertise roles
# "Method" keywords describe *how* someone works; everything else is a topic/domain.
# Complementarity = one person brings a method the other lacks, applied to a topic
# or setting they share or that is related.
METHOD_KEYWORDS = {
    "AI & Machine Learning", "Biostatistics & Data Science", "Digital Health", "Epidemiology", "Genomics",
    "Health Economics", "Implementation Science", "Global Health Ethics & Law", "Health Policy",
    "Medical Education & Training",
}

# ---------------------------------------------------------------- related topics
# Topic pairs judged to be scientifically adjacent, with the reason shown to users.
# Symmetric. Used for "related" (not identical) interests.
RELATED_TOPICS = {
    ("Climate Change", "Vector-Borne Disease"): "climate shifts the range and season of disease vectors",
    ("Climate Change", "Infectious Disease"): "climate affects transmission of many infections",
    ("Climate Change", "Nutrition"): "climate affects crop yields and food security",
    ("Climate Change", "Water & Sanitation"): "climate drives water scarcity and flooding",
    ("Climate Change", "Mental Health"): "climate events and heat affect mental health",
    ("Climate Change", "Cardiovascular Disease"): "heat and air pollution affect cardiovascular outcomes",
    ("Environmental Health", "Cardiovascular Disease"): "environmental exposures are cardiovascular risk factors",
    ("Environmental Health", "Maternal & Child Health"): "pregnancy and early childhood are sensitive exposure windows",
    ("Vector-Borne Disease", "Malaria"): "malaria is mosquito-borne",
    ("Vector-Borne Disease", "Neglected Tropical Diseases"): "many NTDs are vector-borne",
    ("One Health & Zoonoses", "Infectious Disease"): "most emerging infections are zoonotic",
    ("One Health & Zoonoses", "Pandemic Preparedness & Health Security"): "zoonotic spillover drives pandemic risk",
    ("Infectious Disease", "Pandemic Preparedness & Health Security"): "preparedness depends on infectious-disease science",
    ("COVID-19", "Pandemic Preparedness & Health Security"): "COVID-19 is the reference case for preparedness",
    ("Vaccines & Immunization", "Pandemic Preparedness & Health Security"): "vaccines are a core preparedness tool",
    ("Antimicrobial Resistance", "Infectious Disease"): "resistance undermines infection treatment",
    ("HIV/AIDS", "Tuberculosis"): "TB is the leading cause of death among people with HIV",
    ("HIV/AIDS", "Substance Use"): "substance use is a key driver of HIV risk",
    ("HIV/AIDS", "Reproductive & Sexual Health"): "HIV prevention is integrated with sexual and reproductive health",
    ("Mental Health", "Substance Use"): "frequent co-occurrence",
    ("Mental Health", "Humanitarian & Refugee Health"): "displacement carries a large mental-health burden",
    ("Maternal & Child Health", "Nutrition"): "maternal and child nutrition are central to both",
    ("Maternal & Child Health", "Reproductive & Sexual Health"): "continuum of reproductive and maternal care",
    ("Noncommunicable Diseases", "Cardiovascular Disease"): "CVD is the largest NCD burden",
    ("Noncommunicable Diseases", "Diabetes"): "diabetes is a major NCD",
    ("Noncommunicable Diseases", "Cancer"): "cancer is a major NCD",
    ("Diabetes", "Cardiovascular Disease"): "shared metabolic risk",
    ("Health Systems", "Health Workforce"): "the workforce is a core health-system building block",
    ("Health Systems", "Global Surgery"): "surgical access depends on health-system capacity",
    ("Health Systems", "Emergency & Critical Care"): "emergency care is a health-system function",
    ("Humanitarian & Refugee Health", "Injury & Violence"): "conflict settings combine both",
    ("Aging", "Noncommunicable Diseases"): "NCD burden rises with age",
}

# ---------------------------------------------------------------- geography
# Country -> broader regions it belongs to (for "related" geography).
COUNTRY_REGIONS = {}
for regions, countries in [
    (("East Africa", "Sub-Saharan Africa", "Africa"), ["Kenya", "Uganda", "Tanzania", "Rwanda", "Burundi", "Ethiopia", "Somalia", "South Sudan", "Sudan", "Madagascar"]),
    (("West Africa", "Sub-Saharan Africa", "Africa"), ["Ghana", "Nigeria", "Senegal", "Mali", "Niger", "Burkina Faso", "Benin", "Togo", "Liberia", "Sierra Leone", "Guinea", "Gambia"]),
    (("Southern Africa", "Sub-Saharan Africa", "Africa"), ["South Africa", "Botswana", "Zimbabwe", "Zambia", "Malawi", "Mozambique", "Namibia", "Lesotho", "Eswatini"]),
    (("Sub-Saharan Africa", "Africa"), ["Cameroon", "Democratic Republic of the Congo"]),
    (("North Africa", "Africa", "Middle East"), ["Egypt", "Morocco", "Tunisia"]),
    (("Middle East",), ["Lebanon", "Jordan", "Syria", "Iraq", "Iran", "Yemen", "Palestine", "Turkey"]),
    (("South Asia", "Asia"), ["India", "Pakistan", "Bangladesh", "Nepal", "Sri Lanka", "Bhutan", "Afghanistan"]),
    (("Southeast Asia", "Asia"), ["Vietnam", "Thailand", "Cambodia", "Laos", "Myanmar", "Malaysia", "Indonesia", "Philippines", "Timor-Leste"]),
    (("East Asia", "Asia"), ["China", "Mongolia"]),
    (("Central Asia", "Asia"), ["Kyrgyzstan", "Tajikistan", "Uzbekistan"]),
    (("Central America", "Latin America"), ["Guatemala", "Honduras", "El Salvador", "Nicaragua", "Costa Rica", "Panama", "Belize", "Mexico"]),
    (("Caribbean", "Latin America"), ["Haiti", "Dominican Republic", "Cuba", "Jamaica", "Puerto Rico"]),
    (("Latin America",), ["Brazil", "Peru", "Colombia", "Ecuador", "Bolivia", "Chile", "Argentina", "Uruguay", "Paraguay", "Venezuela"]),
    (("Eastern Europe",), ["Ukraine", "Russia"]),
]:
    for c in countries:
        COUNTRY_REGIONS[c] = set(regions)
SUB_REGIONS = {"East Africa": {"Sub-Saharan Africa", "Africa"}, "West Africa": {"Sub-Saharan Africa", "Africa"},
               "Southern Africa": {"Sub-Saharan Africa", "Africa"}, "Sub-Saharan Africa": {"Africa"},
               "North Africa": {"Africa"}, "South Asia": {"Asia"}, "Southeast Asia": {"Asia"},
               "East Asia": {"Asia"}, "Central Asia": {"Asia"}, "Central America": {"Latin America"},
               "Caribbean": {"Latin America"}}


def broader(place: str) -> set[str]:
    return COUNTRY_REGIONS.get(place, set()) | SUB_REGIONS.get(place, set())
