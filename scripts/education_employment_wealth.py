"""Analysis 4: household wealth, education and current employment.

Research question: How does household wealth relate to women's education and
employment?

Variables: v190 (wealth index, national quintiles), v106 (education),
v714 (currently working), v005 (weight), v012 (age, for age standardization).

Note: the codebook labels v190 "wealth index combined", with codes
1 = poorest ... 5 = richest. The Stata file does not document how the index
is constructed; that is described in DHS methodology documents, which this
project has not used yet. So we treat v190 only as a ranking into five groups.

Why age-standardize here: wealth groups may have different age mixes, and
Analysis 2 showed age is strongly linked to both education and employment.
Standardizing uses the same age mix (all v714 respondents) for every group.

Writes seven CSVs to docs/results/analysis_4/. Run from anywhere:

    python3 scripts/education_employment_wealth.py
"""

from dhs_utils import (
    RESULTS_DIR,
    add_age_group,
    clean_variables,
    education_employment_by_group,
    load_codebook,
    read_columns,
    standard_age_shares,
    value_labels,
    write_tables,
)

OUT_DIR = RESULTS_DIR / "analysis_4"
VARS = ["v190", "v106", "v714", "v005", "v012"]
GROUP_VAR = "v190"


def main():
    print(f"Analysis 4: reading {len(VARS)} columns...")
    raw = read_columns(VARS)
    print(f"  {len(raw):,} observations")

    labels = value_labels(load_codebook(), ["v190", "v106"])
    cleaned = add_age_group(clean_variables(raw, labels))

    # Analytic sample for employment: valid v714, education, age and wealth.
    analytic = cleaned.dropna(subset=["v714", "v106", "age_group", GROUP_VAR])
    print(f"  analytic sample: {len(analytic):,} women")
    shares = standard_age_shares(analytic)

    tables = education_employment_by_group(cleaned, analytic, GROUP_VAR, labels, shares)
    write_tables(tables, OUT_DIR)


if __name__ == "__main__":
    main()
