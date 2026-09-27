"""Analysis 3: education and current employment in urban vs rural India.

Research question: Does the relationship between women's education and
employment differ between urban and rural India?

Variables: v025 (urban/rural), v106 (education), v714 (currently working),
v005 (weight), v012 (age, used for age standardization).

Why age-standardize here: urban and rural women may have different age mixes,
and Analysis 2 showed that age is strongly linked to both education and
employment. Standardizing gives every group the same age mix (that of all
women who answered v714), so the comparison is not driven by age differences.

Writes seven CSVs to docs/results/analysis_3/. Run from anywhere:

    python3 scripts/education_employment_urban_rural.py
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

OUT_DIR = RESULTS_DIR / "analysis_3"
VARS = ["v025", "v106", "v714", "v005", "v012"]
GROUP_VAR = "v025"


def main():
    print(f"Analysis 3: reading {len(VARS)} columns...")
    raw = read_columns(VARS)
    print(f"  {len(raw):,} observations")

    labels = value_labels(load_codebook(), ["v025", "v106"])
    cleaned = add_age_group(clean_variables(raw, labels))

    # Analytic sample for employment: valid v714, education, age and residence.
    analytic = cleaned.dropna(subset=["v714", "v106", "age_group", GROUP_VAR])
    print(f"  analytic sample: {len(analytic):,} women")
    shares = standard_age_shares(analytic)

    tables = education_employment_by_group(cleaned, analytic, GROUP_VAR, labels, shares)
    write_tables(tables, OUT_DIR)


if __name__ == "__main__":
    main()
