"""Analysis 2: education and current employment, accounting for age.

Research question: Does the relationship between women's education and current
employment change after accounting for age?

Descriptive only (no models). Uses the Analysis 1 variables plus:
    v012  respondent's current age
    v013  age in 5-year groups (consistency check against v012)

Writes seven CSVs to docs/results/analysis_2/. Run from anywhere:

    python3 scripts/education_employment_age.py
"""

import pandas as pd

from dhs_utils import (
    AGE_LABELS,
    RESULTS_DIR,
    add_age_group,
    age_standardized_rate,
    clean_variables,
    is_suppressed,
    load_codebook,
    read_columns,
    sample_flag,
    standard_age_shares,
    value_labels,
    weighted_pct,
    weighted_rate,
    write_tables,
)

OUT_DIR = RESULTS_DIR / "analysis_2"
VARS = ["v024", "v025", "v106", "v133", "v714", "v190", "v005", "v012", "v013"]
LABELLED_VARS = ["v024", "v025", "v106", "v714", "v190", "v013"]


def age_checks(raw, cleaned):
    """v012 missing / out-of-range values, and agreement with v013.

    v012 has no value labels, so there are no DHS special codes to look for:
    only Stata-missing values or ages outside the eligible range 15-49.
    """
    derived_code = cleaned["age_group"].cat.codes + 1  # 15-19 -> 1 ... 45-49 -> 7 (v013's coding)
    both = cleaned["age_group"].notna() & raw["v013"].notna()
    return pd.DataFrame([
        ("n_total", len(raw)),
        ("v012_stata_missing", int(raw["v012"].isna().sum())),
        ("v012_out_of_range_15_49", int((raw["v012"].notna() & ~raw["v012"].between(15, 49)).sum())),
        ("v012_valid", int(cleaned["v012"].notna().sum())),
        ("v012_min", int(cleaned["v012"].min())),
        ("v012_max", int(cleaned["v012"].max())),
        ("v013_stata_missing", int(raw["v013"].isna().sum())),
        ("age_group_matches_v013", int((derived_code[both] == raw.loc[both, "v013"]).sum())),
        ("age_group_differs_from_v013", int((derived_code[both] != raw.loc[both, "v013"]).sum())),
    ], columns=["check", "value"])


def age_distribution(cleaned):
    """Per age group: how many women, and how many answered v714.

    Keeps the employment missingness explicit: if v714 was asked of a random
    subsample, the share answering should be similar in every age group.
    """
    groups = cleaned.dropna(subset=["age_group"]).groupby("age_group", observed=True)
    table = pd.DataFrame({
        "n_women": groups.size(),
        "n_answered_v714": groups["v714"].count(),
    })
    table["pct_answered_v714_unweighted"] = (100 * table.n_answered_v714 / table.n_women).round(2)
    table["pct_of_all_women_weighted"] = weighted_pct(cleaned, "age_group").round(2)
    answered = cleaned.dropna(subset=["v714"])
    table["pct_of_v714_respondents_weighted"] = weighted_pct(answered, "age_group").round(2)
    return table


def employment_by_age(analytic):
    counts = analytic.groupby("age_group", observed=True).size()
    rates = weighted_rate(analytic, "age_group")
    return pd.DataFrame({"n_answered_v714": counts, "pct_currently_working": rates.round(2)})


def employment_by_education_and_age(analytic, labels):
    """One row per (age group, education) cell, with n and a small-sample flag."""
    rates = weighted_rate(analytic, ["age_group", "v106"])
    rows = []
    for (age, edu), cell in analytic.groupby(["age_group", "v106"], observed=True):
        n = len(cell)
        flag = sample_flag(n)
        rows.append({
            "age_group": age,
            "v106": int(edu),
            "education": labels["v106"][int(edu)],
            "n_answered_v714": n,
            "pct_currently_working": None if is_suppressed(flag) else round(rates[(age, edu)], 2),
            "reliability": flag,
        })
    return pd.DataFrame(rows)


def education_by_age(analytic, labels):
    """Weighted education mix within each age group (among v714 respondents).
    Shows how differently educated the age groups are, which is why age can
    distort the overall education-employment pattern."""
    table = weighted_pct(analytic, "v106", by="age_group").unstack("v106").round(2)
    table.columns = [f"pct_{labels['v106'][int(c)].replace(' ', '_')}" for c in table.columns]
    return table


def crude_vs_age_standardized(analytic, labels, shares):
    """Crude vs directly age-standardized employment rate for each education level.

    If the gap between education levels shrinks after standardization, part of
    the crude pattern reflects the groups' different age mixes.
    """
    crude = weighted_rate(analytic, "v106")
    rows = []
    for edu in sorted(analytic["v106"].unique()):
        group_data = analytic[analytic.v106 == edu]
        std_rate, smallest = age_standardized_rate(group_data, shares)
        rows.append({
            "v106": int(edu),
            "education": labels["v106"][int(edu)],
            "n_answered_v714": len(group_data),
            "smallest_age_cell_n": smallest,
            "crude_pct_currently_working": round(crude[edu], 2),
            "age_standardized_pct_currently_working": None if std_rate is None else round(std_rate, 2),
        })
    table = pd.DataFrame(rows)
    table["difference_std_minus_crude"] = (
        table.age_standardized_pct_currently_working - table.crude_pct_currently_working
    ).round(2)
    return table


def main():
    print(f"Analysis 2: reading {len(VARS)} columns...")
    raw = read_columns(VARS)
    print(f"  {len(raw):,} observations")

    codebook = load_codebook()
    labels = value_labels(codebook, LABELLED_VARS)
    cleaned = add_age_group(clean_variables(raw, labels))

    # Analytic sample: women with a valid v714 answer (the ~15% employment
    # subsample), a valid education level and a valid age.
    analytic = cleaned.dropna(subset=["v714", "v106", "age_group"])
    print(f"  analytic sample: {len(analytic):,} women ({100 * len(analytic) / len(raw):.1f}% of all)")
    shares = standard_age_shares(analytic)

    cells = employment_by_education_and_age(analytic, labels)
    wide = cells.pivot(index="age_group", columns="education", values="pct_currently_working")
    wide = wide[[labels["v106"][c] for c in sorted(labels["v106"])]].reindex(AGE_LABELS)
    wide.index.name = "age_group"

    tables = {
        "01_age_checks": age_checks(raw, cleaned),
        "02_age_distribution_and_v714_coverage": (age_distribution(cleaned), True),
        "03_employment_by_age": (employment_by_age(analytic), True),
        "04_employment_by_education_and_age": cells,
        "05_education_mix_by_age": (education_by_age(analytic, labels), True),
        "06_crude_vs_age_standardized": crude_vs_age_standardized(analytic, labels, shares),
        "07_employment_by_education_and_age_wide": (wide, True),
    }
    write_tables(tables, OUT_DIR)


if __name__ == "__main__":
    main()
