"""Python analysis on top of the SQL queries: the "Python analysis tool".

SQL is good at "filter, group, sum". Some steps are clearer in Python:
combining several queries into one ranking, age standardization (a weighted
average of age-specific rates), and comparing groups. Every function here
calls queries.weighted_percentage() for the actual numbers, so each result
keeps the SQL behind it.
"""

from dataclasses import dataclass, field

from src.analysis.database import label_for
from src.analysis.queries import sample_flag, weighted_percentage
from src.config import MIN_GROUP_N_FOR_RANKING
from src.data.variables import DEFAULT_UNDERSERVED_INDICATORS, DERIVED, DERIVED_BY_NAME

AGE_GROUP_COLUMN = "v013"   # DHS 5-year age groups (verified equal to the groups of v012)


@dataclass
class AnalysisResult:
    title: str
    rows: list
    queries: list                   # QueryResult.to_dict() for every SQL query used
    variables: list
    method: list
    notes: list = field(default_factory=list)
    summary: dict = field(default_factory=dict)   # small facts about the whole result

    def to_dict(self):
        return {"title": self.title, "rows": self.rows, "queries": self.queries, "variables": self.variables,
                "method": self.method, "notes": self.notes, "summary": self.summary}


def group_key(row, group_by):
    return tuple(row[g] for g in group_by)


def group_label(row, group_by):
    return ", ".join(str(row[f"{g}_label"]) for g in group_by)


# ---------------------------------------------------------------------------
# Underserved ranking
# ---------------------------------------------------------------------------
def rank_underserved_groups(group_by=("v024", "v025"), indicators=None, filters=None,
                            min_n=MIN_GROUP_N_FOR_RANKING, top_k=10):
    """Rank groups by a simple deprivation score.

    score = average of the group's weighted % on each deprivation indicator
            (equal weights; higher = more women lacking these things).

    This is one transparent, adjustable definition of "underserved", not an
    official measure. Groups with fewer than `min_n` women are not ranked.
    """
    group_by = list(group_by)
    indicators = list(indicators or DEFAULT_UNDERSERVED_INDICATORS)
    for name in indicators:
        if DERIVED_BY_NAME.get(name) is None or DERIVED_BY_NAME[name].kind != "deprivation":
            raise ValueError(f"{name!r} is not a deprivation indicator")

    per_indicator, queries = {}, []
    national = {}
    for name in indicators:
        result = weighted_percentage({"indicator": name}, filters, group_by)
        per_indicator[name] = {group_key(r, group_by): r for r in result.rows}
        queries.append(result.to_dict())
        overall = weighted_percentage({"indicator": name}, filters)
        national[name] = overall.rows[0]["weighted_pct"] if overall.rows else None

    base = per_indicator[indicators[0]]
    rows = []
    for key, first in base.items():
        row = {g: first[g] for g in group_by}
        row.update({f"{g}_label": first[f"{g}_label"] for g in group_by})
        row["group"] = group_label(first, group_by)
        row["n_women"] = first["n_in_population"]
        values = []
        for name in indicators:
            cell = per_indicator[name].get(key)
            pct = cell["weighted_pct"] if cell else None
            row[f"pct_{name}"] = pct
            row[f"n_{name}"] = cell["n_valid"] if cell else 0
            values.append(pct)
        complete = all(v is not None for v in values)
        row["deprivation_score"] = round(sum(values) / len(values), 2) if complete else None
        row["ranked"] = complete and row["n_women"] >= min_n
        rows.append(row)

    ranked = sorted([r for r in rows if r["ranked"]], key=lambda r: -r["deprivation_score"])
    for position, row in enumerate(ranked, start=1):
        row["rank"] = position
    national_score = round(sum(national.values()) / len(national), 2) if all(
        v is not None for v in national.values()) else None

    return AnalysisResult(
        title=f"Groups ranked by deprivation score ({', '.join(group_by)})",
        rows=ranked[:top_k],
        queries=queries,
        variables=sorted({v for name in indicators for v in DERIVED_BY_NAME[name].sources}
                         | set(group_by) | {"w (= v005 / 1,000,000)"}),
        method=[
            "For each indicator, compute the weighted % of women lacking it in each group (SQL).",
            "Deprivation score = simple average of those percentages (equal weight per indicator).",
            f"Only groups with at least {min_n} women are ranked.",
            "Indicators used: " + "; ".join(f"{n} = {DERIVED_BY_NAME[n].rule}" for n in indicators),
        ],
        notes=[
            f"National reference: " + ", ".join(f"{n} {national[n]}%" for n in indicators)
            + f"; national score {national_score}.",
            f"{len(ranked)} of {len(rows)} groups met the size threshold and had all indicators.",
            "This definition of 'underserved' is a project choice; different indicators or weights "
            "can change the ranking.",
        ],
        summary={"n_groups_ranked": len(ranked), "n_groups": len(rows), "national_score": national_score},
    )


# ---------------------------------------------------------------------------
# Age standardization
# ---------------------------------------------------------------------------
def age_standardized_rates(outcome, group_by, filters=None):
    """Crude and directly age-standardized weighted % of `outcome` by group.

    standardized % = sum over age groups a of (standard share_a x group's % in age a)

    The standard shares are the weighted age distribution of all women (in the
    filtered population) with a valid outcome, so every group is compared as
    if it had the same age mix.
    """
    group_by = list(group_by)
    crude = weighted_percentage(outcome, filters, group_by)
    by_age = weighted_percentage(outcome, filters, group_by + [AGE_GROUP_COLUMN])
    ages = weighted_percentage(outcome, filters, [AGE_GROUP_COLUMN])
    total_weight = sum(r["weighted_denominator"] for r in ages.rows)
    shares = {r[AGE_GROUP_COLUMN]: r["weighted_denominator"] / total_weight for r in ages.rows}

    cells = {}
    for r in by_age.rows:
        cells.setdefault(group_key(r, group_by), {})[r[AGE_GROUP_COLUMN]] = r

    rows = []
    for r in crude.rows:
        key = group_key(r, group_by)
        age_cells = cells.get(key, {})
        smallest = min((age_cells[a]["n_valid"] if a in age_cells else 0) for a in shares)
        standardized = None
        if smallest > 0:
            # Use unsuppressed values: weighted_numerator / weighted_denominator.
            standardized = round(100 * sum(
                shares[a] * age_cells[a]["weighted_numerator"] / age_cells[a]["weighted_denominator"]
                for a in shares), 2)
        rows.append({
            **{g: r[g] for g in group_by}, **{f"{g}_label": r[f"{g}_label"] for g in group_by},
            "group": group_label(r, group_by),
            "n_valid": r["n_valid"],
            "crude_pct": r["weighted_pct"],
            "age_standardized_pct": standardized if r["weighted_pct"] is not None else None,
            "smallest_age_cell_n": smallest,
            "age_cell_reliability": sample_flag(smallest) if smallest else "no cases in an age group",
        })
    return AnalysisResult(
        title=f"Crude vs age-standardized: {crude.title}",
        rows=rows,
        queries=[crude.to_dict(), by_age.to_dict(), ages.to_dict()],
        variables=sorted(set(crude.variables) | {AGE_GROUP_COLUMN}),
        method=[
            "Crude % = weighted % in each group (SQL).",
            "Age-specific % for each group x DHS 5-year age group (v013) (SQL).",
            "Standard population = weighted age distribution of all women with a valid answer.",
            "Age-standardized % = sum(standard share x age-specific %) (Python).",
        ],
        notes=["Age standardization removes differences in age mix; it does not adjust for anything else.",
               "Rates whose smallest age cell has fewer than 25 women are noisy."],
    )


# ---------------------------------------------------------------------------
# Channel reach (which communication channels already reach a population)
# ---------------------------------------------------------------------------
REACH_INDICATORS = [d.name for d in DERIVED if d.kind == "reach" and d.name != "currently_working"]


def channel_reach(filters=None):
    """Weighted % of the population reached by each channel indicator."""
    rows, queries = [], []
    for name in REACH_INDICATORS:
        result = weighted_percentage({"indicator": name}, filters)
        queries.append(result.to_dict())
        row = result.rows[0] if result.rows else {"weighted_pct": None, "n_valid": 0, "reliability": "no data"}
        info = DERIVED_BY_NAME[name]
        rows.append({"indicator": name, "description": info.description, "rule": info.rule,
                     "universe": info.universe, "weighted_pct": row["weighted_pct"],
                     "n_valid": row["n_valid"], "reliability": row["reliability"]})
    rows.sort(key=lambda r: -(r["weighted_pct"] or -1))
    return AnalysisResult(
        title="Channel reach in the target population",
        rows=rows, queries=queries,
        variables=sorted({v for n in REACH_INDICATORS for v in DERIVED_BY_NAME[n].sources} | {"w (= v005 / 1,000,000)"}),
        method=["Weighted % of women in the population for whom each channel indicator is 1 (SQL)."],
        notes=["Phone, internet and bank indicators come only from the state-module subsample (ssmod = 1)."],
    )


def population_filters_from_group(row, group_by):
    """Turn a ranked group (e.g. Bihar, rural) back into filters."""
    return [{"variable": g, "op": "=", "value": row[g]} for g in group_by]


def describe_group(row, group_by):
    return "; ".join(f"{g} = {label_for(g, row[g])}" for g in group_by)
