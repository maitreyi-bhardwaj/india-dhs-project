"""Analysis 1: education and current employment, nationally and by state.

Research question: How does women's educational attainment vary across Indian
states, and how is it associated with current employment?

Reads 7 variables from data/IAIR7EFL.DTA (chunked, read-only) and writes seven
CSVs to docs/results/. Run from anywhere:

    python3 scripts/education_employment_summary.py
"""

import pandas as pd

from dhs_utils import (
    RESULTS_DIR,
    clean_variables,
    load_codebook,
    read_columns,
    value_labels,
    weighted_mean,
    weighted_pct,
    write_tables,
)

VARS = ["v024", "v025", "v106", "v133", "v714", "v190", "v005"]
LABELLED_VARS = ["v024", "v025", "v106", "v714", "v190"]


def missing_table(raw, cleaned, codebook):
    """Missing values per variable: Stata-missing, and after applying the cleaning rules."""
    table = pd.DataFrame({
        "variable": VARS,
        "label": [codebook.loc[v, "variable_label"] for v in VARS],
        "n_total": len(raw),
        "missing_stata": [int(raw[v].isna().sum()) for v in VARS],
        "missing_after_cleaning": [int(cleaned["w" if v == "v005" else v].isna().sum()) for v in VARS],
    })
    table["pct_missing_after_cleaning"] = (100 * table.missing_after_cleaning / table.n_total).round(2)
    return table


def frequency_table(cleaned, labels):
    """Unweighted counts plus unweighted and weighted % for each category."""
    rows = []
    for var in ["v106", "v714", "v025", "v190"]:
        counts = cleaned[var].value_counts().sort_index()
        weighted = weighted_pct(cleaned, var)
        for code in counts.index:
            rows.append({
                "variable": var,
                "code": int(code),
                "meaning": labels[var][int(code)],
                "n_unweighted": int(counts[code]),
                "pct_unweighted": round(100 * counts[code] / counts.sum(), 2),
                "pct_weighted": round(weighted[code], 2),
            })
    return pd.DataFrame(rows)


def state_education_table(cleaned, labels):
    """Weighted % in each education level, and weighted mean years, per state."""
    pct = weighted_pct(cleaned, "v106", by="v024").unstack("v106").round(2)
    pct.columns = [f"pct_{labels['v106'][int(c)].replace(' ', '_')}" for c in pct.columns]
    years = (
        cleaned.dropna(subset=["v133"])
        .groupby("v024")
        .apply(lambda state: weighted_mean(state, "v133"), include_groups=False)
        .round(2)
    )
    table = pd.concat([cleaned.groupby("v024").v106.count().rename("n_women"), pct,
                       years.rename("mean_years_education")], axis=1)
    table.insert(0, "state", [labels["v024"][int(s)] for s in table.index])
    table.index = table.index.astype(int)
    table.index.name = "v024"
    return table.sort_values("pct_higher", ascending=False)


def state_employment_table(cleaned, labels):
    """Weighted % currently working per state, with the number who answered v714."""
    pct = weighted_pct(cleaned, "v714", by="v024").unstack("v714")
    table = pd.DataFrame({
        "state": [labels["v024"][int(s)] for s in pct.index],
        "n_answered_v714": cleaned.groupby("v024").v714.count().reindex(pct.index).values,
        "pct_currently_working": pct[1].round(2).values,
    }, index=pct.index.astype(int))
    table.index.name = "v024"
    return table.sort_values("pct_currently_working", ascending=False)


def employment_by_education_table(cleaned, labels):
    pct = weighted_pct(cleaned, "v714", by="v106").unstack("v714")
    return pd.DataFrame({
        "v106": pct.index.astype(int),
        "education": [labels["v106"][int(c)] for c in pct.index],
        "n_answered_v714": cleaned.dropna(subset=["v714"]).groupby("v106").size().values,
        "pct_currently_working": pct[1].round(2).values,
    })


def main():
    print(f"Analysis 1: reading {len(VARS)} columns...")
    raw = read_columns(VARS)
    print(f"  {len(raw):,} observations")

    codebook = load_codebook()
    labels = value_labels(codebook, LABELLED_VARS)
    cleaned = clean_variables(raw, labels)

    freq = frequency_table(cleaned, labels)
    national_cols = ["code", "meaning", "n_unweighted", "pct_weighted"]
    tables = {
        "01_missing_values": missing_table(raw, cleaned, codebook),
        "02_frequencies": freq,
        "03_national_education": freq[freq.variable == "v106"][national_cols],
        "04_national_employment": freq[freq.variable == "v714"][national_cols],
        "05_state_education": (state_education_table(cleaned, labels), True),
        "06_state_employment": (state_employment_table(cleaned, labels), True),
        "07_employment_by_education": employment_by_education_table(cleaned, labels),
    }
    write_tables(tables, RESULTS_DIR)
    print(f"  national weighted mean years of education (v133): {weighted_mean(cleaned, 'v133'):.2f}")


if __name__ == "__main__":
    main()
