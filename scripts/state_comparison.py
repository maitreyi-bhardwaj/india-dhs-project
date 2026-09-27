"""Analysis 5: state patterns in education and employment.

Builds on Analysis 1's state tables (docs/results/05_state_education.csv and
06_state_employment.csv) and extends them with:
    - top/bottom states for higher education and for employment
    - age-standardized state employment rates
    - employment by education within each state
    - states whose education-employment pattern differs from the national one

Variables read from the data: v024 (state), v106 (education), v714 (currently
working), v005 (weight), v012 (age, for age standardization).

DECISION RULES (documented here because they are judgement calls, not DHS rules):
    SMALL_STATE_N = 500
        A state with fewer than 500 women answering v714 is flagged as a
        "small sample" and its employment rate should be read with caution.
    MIN_AGE_CELL_N = 10
        A state's education gap is only assessed if every age group has at
        least 10 women in both education groups being compared (7 ages x 2
        education levels = 14 cells). Otherwise the age-standardized rates rest
        on too few women.
    DIFFERENCE_THRESHOLD = 10 percentage points
        A state "differs substantially" if its age-standardized gap is at least
        10 points away from the national gap. This is a rough heuristic, NOT a
        statistical test: without survey-design standard errors we cannot say
        whether a difference is statistically significant.

Writes six CSVs to docs/results/analysis_5/. Run Analysis 1 first.

    python3 scripts/state_comparison.py
"""

import sys

import pandas as pd

from dhs_utils import (
    RESULTS_DIR,
    SUPPRESS_BELOW,
    add_age_group,
    age_standardized_rate,
    clean_variables,
    is_suppressed,
    load_codebook,
    read_columns,
    sample_flag,
    standard_age_shares,
    value_labels,
    weighted_rate,
    write_tables,
)

OUT_DIR = RESULTS_DIR / "analysis_5"
VARS = ["v024", "v106", "v714", "v005", "v012"]

SMALL_STATE_N = 500
MIN_AGE_CELL_N = 10
DIFFERENCE_THRESHOLD = 10.0
TOP_N = 5

# The main contrast: secondary (v106 = 2) minus no education (v106 = 0).
# It is the largest gap in the national pattern (Analyses 1 and 2).
LOW_EDU, HIGH_EDU = 0, 2


def load_analysis_1_tables():
    """Read Analysis 1's state tables (this script extends them, it doesn't redo them)."""
    edu_path = RESULTS_DIR / "05_state_education.csv"
    emp_path = RESULTS_DIR / "06_state_employment.csv"
    if not edu_path.exists() or not emp_path.exists():
        sys.exit("Analysis 1 results not found. Run scripts/education_employment_summary.py first.")
    return pd.read_csv(edu_path), pd.read_csv(emp_path)


def small_state_label(n):
    return "small sample (n<500)" if n < SMALL_STATE_N else "ok"


def top_and_bottom(table, column, n_column, extra_columns=()):
    """The TOP_N highest and TOP_N lowest states on `column`."""
    ranked = table.sort_values(column, ascending=False).reset_index(drop=True)
    ranked["rank_high_to_low"] = ranked.index + 1
    top = ranked.head(TOP_N).assign(position="highest")
    bottom = ranked.tail(TOP_N).assign(position="lowest")
    columns = ["position", "rank_high_to_low", "v024", "state", column, n_column, *extra_columns]
    return pd.concat([top, bottom])[columns]


def state_employment_standardized(analytic, labels, shares):
    """Crude and age-standardized employment rate for every state.
    Standardizing checks whether a state's rank is driven by its age mix."""
    crude = weighted_rate(analytic, "v024")
    rows = []
    for code in sorted(analytic["v024"].unique()):
        state_data = analytic[analytic["v024"] == code]
        std_rate, smallest = age_standardized_rate(state_data, shares)
        rows.append({
            "v024": int(code),
            "state": labels["v024"][int(code)],
            "n_answered_v714": len(state_data),
            "sample_size_flag": small_state_label(len(state_data)),
            "crude_pct_currently_working": round(crude[code], 2),
            "age_standardized_pct_currently_working": None if std_rate is None else round(std_rate, 2),
            "smallest_age_cell_n": smallest,
        })
    table = pd.DataFrame(rows)
    table["rank_crude"] = table.crude_pct_currently_working.rank(ascending=False, method="min").astype(int)
    table["rank_age_standardized"] = table.age_standardized_pct_currently_working.rank(
        ascending=False, method="min").astype("Int64")
    return table.sort_values("age_standardized_pct_currently_working", ascending=False)


def state_employment_by_education(analytic, labels):
    """Crude weighted employment rate for each state x education cell."""
    rates = weighted_rate(analytic, ["v024", "v106"])
    rows = []
    for (state, edu), cell in analytic.groupby(["v024", "v106"]):
        flag = sample_flag(len(cell))
        rows.append({
            "v024": int(state),
            "state": labels["v024"][int(state)],
            "v106": int(edu),
            "education": labels["v106"][int(edu)],
            "n_answered_v714": len(cell),
            "pct_currently_working": None if is_suppressed(flag) else round(rates[(state, edu)], 2),
            "reliability": flag,
        })
    return pd.DataFrame(rows)


def education_gap_by_state(analytic, labels, shares):
    """For each state: the secondary minus no-education employment gap,
    crude and age-standardized, compared with the national gap."""

    def gap_for(data):
        low = data[data["v106"] == LOW_EDU]
        high = data[data["v106"] == HIGH_EDU]
        low_std, low_small = age_standardized_rate(low, shares)
        high_std, high_small = age_standardized_rate(high, shares)
        crude = weighted_rate(data[data["v106"].isin([LOW_EDU, HIGH_EDU])], "v106")
        # Same DHS rule as everywhere else: no percentage from fewer than 25 women.
        crude_low = crude_or_none(crude.get(LOW_EDU), len(low))
        crude_high = crude_or_none(crude.get(HIGH_EDU), len(high))
        return {
            "n_no_education": len(low),
            "n_secondary": len(high),
            "crude_pct_no_education": crude_low,
            "crude_pct_secondary": crude_high,
            "crude_gap": None if crude_low is None or crude_high is None else round(crude_high - crude_low, 2),
            "age_std_pct_no_education": None if low_std is None else round(low_std, 2),
            "age_std_pct_secondary": None if high_std is None else round(high_std, 2),
            "age_std_gap": None if low_std is None or high_std is None else round(high_std - low_std, 2),
            "smallest_age_cell_n": min(low_small, high_small),
        }

    national = gap_for(analytic)
    rows = []
    for code in sorted(analytic["v024"].unique()):
        row = {"v024": int(code), "state": labels["v024"][int(code)]}
        row.update(gap_for(analytic[analytic["v024"] == code]))
        row["national_age_std_gap"] = national["age_std_gap"]
        row["national_crude_gap"] = national["crude_gap"]
        row["pattern"] = classify_pattern(row, national["age_std_gap"])
        if row["age_std_gap"] is not None:
            row["age_std_gap_minus_national"] = round(row["age_std_gap"] - national["age_std_gap"], 2)
        rows.append(row)
    table = pd.DataFrame(rows)
    national_row = pd.DataFrame([{"v024": 0, "state": "INDIA (national)", **national,
                                  "national_age_std_gap": national["age_std_gap"],
                                  "national_crude_gap": national["crude_gap"],
                                  "pattern": "reference", "age_std_gap_minus_national": 0.0}])
    return pd.concat([national_row, table.sort_values("age_std_gap_minus_national", ascending=False)],
                     ignore_index=True)


def crude_or_none(rate, n):
    """Rounded rate, or None if it rests on fewer than 25 women (DHS convention)."""
    if rate is None or pd.isna(rate) or n < SUPPRESS_BELOW:
        return None
    return round(rate, 2)


def classify_pattern(row, national_gap):
    """Apply the decision rules from the top of this file."""
    if row["smallest_age_cell_n"] < MIN_AGE_CELL_N or row["age_std_gap"] is None:
        return f"not assessed (an age cell has n<{MIN_AGE_CELL_N})"
    difference = row["age_std_gap"] - national_gap
    if difference >= DIFFERENCE_THRESHOLD:
        return "differs: secondary relatively MORE likely to work than nationally"
    if difference <= -DIFFERENCE_THRESHOLD:
        return "differs: secondary relatively LESS likely to work than nationally"
    return "similar to national"


def spearman(a, b):
    """Spearman rank correlation = ordinary (Pearson) correlation of the ranks.
    Written out by hand so the project doesn't need scipy."""
    both = pd.DataFrame({"a": a, "b": b}).dropna()
    return both["a"].rank().corr(both["b"].rank())


def state_level_correlations(state_edu, state_std):
    """Rank correlation across states between higher education and employment.

    Spearman correlation compares the *ranks* of states (1st, 2nd, ...), so a
    few extreme states can't dominate it. Values run from -1 to +1.
    This is an ecological (state-level) association: it says nothing about
    whether more-educated *individual women* are more likely to work.
    """
    merged = state_edu[["v024", "pct_higher"]].merge(
        state_std[["v024", "n_answered_v714", "crude_pct_currently_working",
                   "age_standardized_pct_currently_working"]], on="v024")
    rows = []
    for subset_name, subset in [("all 36 states/UTs", merged),
                                ("excluding small samples (n<500)", merged[merged.n_answered_v714 >= SMALL_STATE_N])]:
        for measure in ["crude_pct_currently_working", "age_standardized_pct_currently_working"]:
            rows.append({
                "states_included": subset_name,
                "n_states": len(subset),
                "employment_measure": measure,
                "spearman_correlation_with_pct_higher_education":
                    round(spearman(subset["pct_higher"], subset[measure]), 3),
            })
    return pd.DataFrame(rows)


def main():
    state_edu, state_emp = load_analysis_1_tables()

    print(f"Analysis 5: reading {len(VARS)} columns...")
    raw = read_columns(VARS)
    print(f"  {len(raw):,} observations")

    labels = value_labels(load_codebook(), ["v024", "v106"])
    cleaned = add_age_group(clean_variables(raw, labels))
    analytic = cleaned.dropna(subset=["v714", "v106", "age_group", "v024"])
    shares = standard_age_shares(analytic)

    state_emp = state_emp.assign(sample_size_flag=state_emp.n_answered_v714.apply(small_state_label))
    state_std = state_employment_standardized(analytic, labels, shares)
    gaps = education_gap_by_state(analytic, labels, shares)

    tables = {
        "01_higher_education_top_bottom": top_and_bottom(state_edu, "pct_higher", "n_women"),
        "02_employment_top_bottom": top_and_bottom(state_emp, "pct_currently_working", "n_answered_v714",
                                                   ["sample_size_flag"]),
        "03_state_employment_crude_vs_age_standardized": state_std,
        "04_state_employment_by_education": state_employment_by_education(analytic, labels),
        "05_state_education_gap_vs_national": gaps,
        "06_state_level_correlations": state_level_correlations(state_edu, state_std),
    }
    write_tables(tables, OUT_DIR)

    counts = gaps[gaps.v024 != 0]["pattern"].value_counts()
    print("  pattern counts:", counts.to_dict())


if __name__ == "__main__":
    main()
