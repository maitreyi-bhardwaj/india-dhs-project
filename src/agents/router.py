"""Rule-based question understanding (offline mode).

Without an LLM, the orchestrator still needs to decide what a question asks
for. This module does it with transparent keyword rules and returns a Plan.
Every rule that fired is recorded in plan.reasons, so the routing decision is
as traceable as the numbers.

It handles the common question shapes (definitions, counts, percentages,
"underserved", outreach). Anything unusual is better handled in LLM mode.
"""

import re
from dataclasses import dataclass, field

from src.analysis.database import value_labels
from src.data.variables import GROUPING_COLUMNS

OUTREACH_WORDS = r"\b(ngos?|non-?profits?|charit\w*|organi[sz]ations?|outreach|channels?|partners?|programs?|programmes?|campaigns?|reach (them|this|these|her|women)|market\w*|communicat\w*)\b"
UNDERSERVED_WORDS = r"\b(underserved|under-served|most deprived|deprived|disadvantaged|marginali[sz]ed|vulnerable|left behind|prioriti[sz]e|priority|neediest|most in need)\b"
DOC_WORDS = r"\b(what does|what is|meaning|mean|define|definition|categor\w*|codebook|which variables?|what variables?|relevant variables?|how (is|was|are) .* (measured|defined|coded)|methodolog\w*|weights?|limitations?|missing)\b"
PERCENT_WORDS = r"(%|\bpercent\w*|\bshare\b|\bproportion\b|\brate\b|\bfraction\b)"
COUNT_WORDS = r"\bhow many\b|\bnumber of (respondents|women)\b|\bcount\b"
NEGATION = r"\b(no|not|don'?t|do not|does not|doesn'?t|without|never|lack\w*|cannot|can'?t|unable)\b"

# keyword -> (outcome if positive, outcome if negated)
OUTCOME_RULES = [
    (r"mobile|cell ?phone|phone", {"indicator": "owns_mobile_phone"}, {"indicator": "no_mobile_phone"}),
    (r"bank", {"indicator": "has_bank_account"}, {"indicator": "no_bank_account"}),
    (r"internet|online", {"indicator": "ever_used_internet"}, {"indicator": "never_used_internet"}),
    (r"insur", {"variable": "v481", "codes": [1]}, {"indicator": "no_health_insurance"}),
    (r"an(a)?emi", {"indicator": "any_anemia"}, {"indicator": "any_anemia"}),
    (r"asha|anganwadi|health worker|frontline|community health", {"indicator": "met_frontline_worker"},
     {"indicator": "no_frontline_worker_contact"}),
    (r"\b(work\w*|employ\w*|job)", {"indicator": "currently_working"}, {"indicator": "not_working"}),
    (r"\b(tv|television)\b", {"indicator": "watches_tv"}, {"variable": "v159", "codes": [0]}),
    (r"radio", {"indicator": "listens_radio"}, {"variable": "v158", "codes": [0]}),
    (r"newspaper|magazine", {"indicator": "reads_newspaper"}, {"variable": "v157", "codes": [0]}),
    (r"\bmedia\b", {"indicator": "no_media_exposure"}, {"indicator": "no_media_exposure"}),
    (r"\b(illiterate|literacy|literate|read)\b", {"variable": "v155", "codes": [1, 2]}, {"indicator": "cannot_read"}),
    (r"higher education|college|university", {"variable": "v106", "codes": [3]}, {"variable": "v106", "codes": [0, 1, 2]}),
    (r"secondary", {"variable": "v106", "codes": [2]}, None),
    (r"primary", {"variable": "v106", "codes": [1]}, None),
    (r"no education|uneducated|never (been to|attended) school|no schooling", {"indicator": "no_education"},
     {"indicator": "no_education"}),
]

GROUP_BY_RULES = [
    (r"\bby state|across states|each state|state-wise|statewise|which states?\b", "v024"),
    (r"\bby district|across districts|which districts?\b", "sdist"),
    (r"urban (and|vs\.?|versus|or) rural|rural (and|vs\.?|versus|or) urban|by residence", "v025"),
    (r"\bby wealth|wealth quintiles?|by quintile|rich(er)? (and|vs) poor", "v190"),
    (r"\bby age|age groups?\b", "v013"),
    (r"\bby education|education levels?\b", "v106"),
    (r"\bby caste|caste|scheduled (caste|tribe)", "s116"),
    (r"\bby religion\b", "v130"),
]

AGE_RANGE = re.compile(r"(?:aged?|ages|between)?\s*(\d{2})\s*(?:-|–|—|to|and)\s*(\d{2})\s*(?:years?|year-olds?|yrs)?")


@dataclass
class Plan:
    intent: str                      # documentation | count | percentage | underserved | outreach_only | unknown
    needs_data: bool
    needs_outreach: bool
    outcome: dict = None
    filters: list = field(default_factory=list)
    group_by: list = field(default_factory=list)
    variables_mentioned: list = field(default_factory=list)
    reasons: list = field(default_factory=list)


def find_places(text, variable):
    """Match value labels of v024 (states) or sdist (districts) as whole words."""
    matches = []
    for code, label in value_labels().get(variable, {}).items():
        name = label.lower().strip()
        if len(name) >= 3 and re.search(rf"(?<![a-z]){re.escape(name)}(?![a-z])", text):
            matches.append((code, name))
    # prefer the longest names ("madhya pradesh" over a shorter overlapping name)
    matches.sort(key=lambda m: -len(m[1]))
    kept = []
    for code, name in matches:
        if not any(name in other for _, other in kept):
            kept.append((code, name))
    return kept


def plan_question(question, variables_mentioned=(), context_population=None):
    text = question.lower()
    reasons = []

    # "Which population should an NGO prioritize?" mentions an NGO but asks about
    # a population, so "should/could an NGO" alone does not trigger outreach.
    outreach_text = re.sub(r"\b(should|could|would|can|must) an? (ngo|organi[sz]ation)\b", "", text)
    wants_outreach = bool(re.search(OUTREACH_WORDS, outreach_text))
    wants_underserved = bool(re.search(UNDERSERVED_WORDS, text))
    wants_doc = bool(re.search(DOC_WORDS, text)) or bool(variables_mentioned)
    wants_percent = bool(re.search(PERCENT_WORDS, text))
    wants_count = bool(re.search(COUNT_WORDS, text))

    # --- population filters --------------------------------------------------
    filters = []
    age = AGE_RANGE.search(text)
    if age and 15 <= int(age.group(1)) <= int(age.group(2)) <= 49:
        filters.append({"variable": "v012", "op": "between", "value": [int(age.group(1)), int(age.group(2))]})
        reasons.append(f"age range {age.group(1)}-{age.group(2)} -> filter v012 between")
    states = find_places(text, "v024")
    if states:
        filters.append({"variable": "v024", "op": "in", "value": [c for c, _ in states]})
        reasons.append(f"state(s) {[n for _, n in states]} -> filter v024")
    districts = [d for d in find_places(text, "sdist") if d[1] not in {n for _, n in states}]
    if districts:
        filters.append({"variable": "sdist", "op": "in", "value": [c for c, _ in districts]})
        reasons.append(f"district(s) {[n for _, n in districts]} -> filter sdist")
    group_by = []
    for pattern, column in GROUP_BY_RULES:
        if re.search(pattern, text) and column not in group_by:
            group_by.append(column)
            reasons.append(f"'{pattern}' -> group by {column}")
    if "v025" not in group_by:
        if re.search(r"\brural\b", text):
            filters.append({"variable": "v025", "op": "=", "value": 2})
            reasons.append("'rural' -> filter v025 = 2")
        elif re.search(r"\burban\b", text):
            filters.append({"variable": "v025", "op": "=", "value": 1})
            reasons.append("'urban' -> filter v025 = 1")
    if "v190" not in group_by:
        for word, code in [("poorest", 1), ("poorer", 2), ("richest", 5), ("richer", 4)]:
            if re.search(rf"\b{word}\b", text):
                filters.append({"variable": "v190", "op": "=", "value": code})
                reasons.append(f"'{word}' -> filter v190 = {code}")
                break

    # --- what is being measured -------------------------------------------------
    outcome = None
    negated = bool(re.search(NEGATION, text))
    for pattern, positive, negative in OUTCOME_RULES:
        if re.search(pattern, text):
            outcome = negative if (negated and negative) else positive
            reasons.append(f"'{pattern}' ({'negated' if negated and negative else 'positive'}) -> outcome {outcome}")
            break

    # --- intent -----------------------------------------------------------------
    if wants_underserved:
        intent = "underserved"
    elif wants_outreach and not (wants_percent or wants_count):
        intent = "outreach_only"
    elif wants_count and not wants_percent:
        intent = "count"
    elif wants_percent and outcome:
        intent = "percentage"
    elif wants_doc:
        intent = "documentation"
    elif outcome:
        intent = "percentage"
        reasons.append("no explicit keyword, but a measurable characteristic -> percentage")
    else:
        intent = "unknown"
    reasons.insert(0, f"intent = {intent}")

    needs_outreach = wants_outreach or intent == "outreach_only"
    needs_data = intent != "outreach_only" or (not filters and context_population is None)
    if intent == "outreach_only" and not filters and context_population is None:
        reasons.append("outreach requested but no population given -> first identify one with the Data Agent")
        intent = "underserved"
    return Plan(intent=intent, needs_data=needs_data, needs_outreach=needs_outreach, outcome=outcome,
                filters=filters, group_by=group_by, variables_mentioned=list(variables_mentioned),
                reasons=reasons)


GROUP_NAMES = {column: name for name, column in GROUPING_COLUMNS.items()}
