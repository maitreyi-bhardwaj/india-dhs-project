"""Analysis 6: robustness and data-quality checks for Analyses 1-5.

Checks:
    1. Missingness of every variable used.
    2. Invalid / special codes (values outside the valid sets in dhs_utils).
    3. Sample sizes overall and by residence, wealth, age group and state.
    4. v012 (age) vs v013 (5-year age group) consistency.
    5. Whether results change materially when
         a. using unweighted instead of weighted percentages
         b. excluding very small groups
    6. That the original data file was not modified.

"Material" is a judgement call, documented here:
    MATERIAL_DIFFERENCE = 2 percentage points between weighted and unweighted.

Run scripts 1-5 first (run_all.py does this and also records the data file's
fingerprint before they run). Writes CSVs to docs/results/analysis_6/.

    python3 scripts/data_quality_checks.py
"""

import json
import re

import pandas as pd

from dhs_utils import (
    AGE_LABELS,
    DATA_PATH,
    ORIGINAL_DTA_MTIME,
    ORIGINAL_DTA_SIZE,
    RESULTS_DIR,
    ROOT,
    VALID_RANGES,
    add_age_group,
    clean_variables,
    dta_fingerprint,
    load_codebook,
    read_columns,
    unweighted_rate,
    valid_codes_for,
    value_labels,
    weighted_pct,
    weighted_rate,
    write_tables,
)

OUT_DIR = RESULTS_DIR / "analysis_6"
FINGERPRINT_BEFORE = OUT_DIR / "dta_fingerprint_before.json"
VARS = ["v024", "v025", "v106", "v133", "v714", "v190", "v005", "v012", "v013"]
LABELLED_VARS = ["v024", "v025", "v106", "v714", "v190", "v013"]

MATERIAL_DIFFERENCE = 2.0
SMALL_STATE_N = 500   # same rule as Analysis 5


# ---------------------------------------------------------------------------
# 1-2. Missingness and codes
# ---------------------------------------------------------------------------
def missingness(raw, cleaned, codebook):
    rows = []
    for var in VARS:
        clean_col = "w" if var == "v005" else var
        stata_missing = int(raw[var].isna().sum())
        missing_after = int(cleaned[clean_col].isna().sum())
        rows.append({
            "variable": var,
            "label": codebook.loc[var, "variable_label"],
            "n_total": len(raw),
            "stata_missing": stata_missing,
            "invalid_or_special_codes": missing_after - stata_missing,
            "valid": len(raw) - missing_after,
            "pct_valid": round(100 * (len(raw) - missing_after) / len(raw), 2),
        })
    return pd.DataFrame(rows)


def code_audit(raw, labels, codebook):
    """Every value found outside the valid set, plus every codebook-labelled
    code that our rules exclude (e.g. v133 97 = inconsistent), with counts."""
    rows = []
    for var in VARS:
        present = raw[var].dropna()
        codebook_codes = json.loads(codebook.loc[var, "value_labels"] or "{}")
        if var == "v005":
            invalid = present[present <= 0]
            rule = "weight must be > 0"
        elif var in VALID_RANGES:
            low, high = VALID_RANGES[var]
            invalid = present[~present.between(low, high)]
            rule = f"valid range {low}-{high}"
        else:
            invalid = present[~present.isin(valid_codes_for(var, labels))]
            rule = "valid codes from codebook"

        for code, count in invalid.value_counts().items():
            rows.append({"variable": var, "rule": rule, "source": "found in data",
                         "code": code, "codebook_meaning": codebook_codes.get(str(int(code)), "(not in codebook)"),
                         "count": int(count)})
        # Codebook codes that the rules treat as missing (special codes).
        for code, meaning in codebook_codes.items():
            code = int(code)
            is_excluded = (var in VALID_RANGES and not VALID_RANGES[var][0] <= code <= VALID_RANGES[var][1])
            if is_excluded:
                rows.append({"variable": var, "rule": rule, "source": "special code defined in codebook",
                             "code": code, "codebook_meaning": meaning, "count": int((present == code).sum())})
        if len(invalid) == 0:
            rows.append({"variable": var, "rule": rule, "source": "found in data",
                         "code": None, "codebook_meaning": "no invalid values found", "count": 0})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 3. Sample sizes
# ---------------------------------------------------------------------------
def sample_sizes(cleaned, labels):
    rows = [{"dimension": "all women", "group": "all", "n_women": len(cleaned),
             "n_answered_v714": int(cleaned["v714"].notna().sum())}]
    dimensions = [("v025", labels["v025"]), ("v190", labels["v190"]), ("v024", labels["v024"])]
    for var, var_labels in dimensions:
        for code, meaning in var_labels.items():
            group = cleaned[cleaned[var] == code]
            rows.append({"dimension": var, "group": meaning, "n_women": len(group),
                         "n_answered_v714": int(group["v714"].notna().sum())})
    for age in AGE_LABELS:
        group = cleaned[cleaned["age_group"] == age]
        rows.append({"dimension": "age_group", "group": age, "n_women": len(group),
                     "n_answered_v714": int(group["v714"].notna().sum())})
    table = pd.DataFrame(rows)
    table["pct_answered_v714"] = (100 * table.n_answered_v714 / table.n_women).round(2)
    return table


def small_cell_summary():
    """Count how many cells in Analyses 2-5 carry each small-sample flag."""
    rows = []
    for folder in ["analysis_2", "analysis_3", "analysis_4", "analysis_5"]:
        for path in sorted((RESULTS_DIR / folder).glob("*.csv")):
            table = pd.read_csv(path)
            flag_columns = [c for c in table.columns if "reliability" in c or c == "sample_size_flag"]
            for column in flag_columns:
                for flag, count in table[column].value_counts().items():
                    rows.append({"file": f"{folder}/{path.name}", "flag_column": column,
                                 "flag": flag, "n_cells": int(count), "n_cells_total": len(table)})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 4. Age consistency
# ---------------------------------------------------------------------------
def age_crosstab(raw, cleaned, labels):
    """Rows = age group derived from v012, columns = v013. Only the diagonal
    should have counts if the two variables agree."""
    table = pd.crosstab(cleaned["age_group"], raw["v013"].map(labels["v013"]))
    table = table.reindex(index=AGE_LABELS, columns=AGE_LABELS, fill_value=0)
    table.index.name = "age_group_from_v012"
    table.columns.name = None
    mismatches = int(table.values.sum() - table.values.trace())
    table["mismatches_in_row"] = table.sum(axis=1) - pd.Series(
        {a: table.loc[a, a] for a in AGE_LABELS})
    return table, mismatches


# ---------------------------------------------------------------------------
# 5a. Weighted vs unweighted
# ---------------------------------------------------------------------------
def compare_row(estimate, group, n, unweighted, weighted):
    difference = weighted - unweighted
    return {
        "estimate": estimate,
        "group": group,
        "n_unweighted": int(n),
        "unweighted_pct": round(unweighted, 2),
        "weighted_pct": round(weighted, 2),
        "weighted_minus_unweighted": round(difference, 2),
        "material_difference": abs(difference) >= MATERIAL_DIFFERENCE,
    }


def weighted_vs_unweighted(cleaned, labels):
    rows = []
    answered = cleaned.dropna(subset=["v714"])

    # Share of women in each education level, nationally.
    edu_weighted = weighted_pct(cleaned, "v106")
    edu_unweighted = 100 * cleaned["v106"].value_counts(normalize=True)
    edu_counts = cleaned["v106"].value_counts()
    for code, meaning in labels["v106"].items():
        rows.append(compare_row("% of women with this education level", meaning,
                                edu_counts[code], edu_unweighted[code], edu_weighted[code]))

    # Share with higher education, by state.
    higher = cleaned.dropna(subset=["v106"]).assign(is_higher=lambda d: (d["v106"] == 3).astype(float))
    state_w = weighted_rate(higher, "v024", value="is_higher")
    state_u = unweighted_rate(higher, "v024", value="is_higher")
    state_n = higher.groupby("v024").size()
    for code in state_w.index:
        rows.append(compare_row("% with higher education, by state", labels["v024"][int(code)],
                                state_n[code], state_u[code], state_w[code]))

    # Employment: overall and by each grouping used in Analyses 1-5.
    overall_w = 100 * (answered["v714"] * answered["w"]).sum() / answered["w"].sum()
    overall_u = 100 * answered["v714"].mean()
    rows.append(compare_row("% currently working", "all respondents", len(answered), overall_u, overall_w))
    for var, var_labels, name in [("v106", labels["v106"], "by education"),
                                  ("age_group", {a: a for a in AGE_LABELS}, "by age group"),
                                  ("v025", labels["v025"], "by residence"),
                                  ("v190", labels["v190"], "by wealth"),
                                  ("v024", labels["v024"], "by state")]:
        w = weighted_rate(answered, var)
        u = unweighted_rate(answered, var)
        n = answered.groupby(var, observed=True).size()
        for key in w.index:
            group = var_labels[key if var == "age_group" else int(key)]
            rows.append(compare_row(f"% currently working, {name}", group, n[key], u[key], w[key]))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 5b. Excluding very small groups
# ---------------------------------------------------------------------------
def small_group_sensitivity(cleaned, labels):
    rows = []
    answered = cleaned.dropna(subset=["v714", "v106", "v024"])
    state_n = answered.groupby("v024").size()
    small_states = state_n[state_n < SMALL_STATE_N].index
    without_small = answered[~answered["v024"].isin(small_states)]

    # (a) National employment by education with and without small states.
    all_rates = weighted_rate(answered, "v106")
    reduced_rates = weighted_rate(without_small, "v106")
    for code, meaning in labels["v106"].items():
        difference = reduced_rates[code] - all_rates[code]
        rows.append({
            "check": "national % working by education, excluding states with <500 v714 respondents",
            "item": meaning,
            "all_groups": round(all_rates[code], 2),
            "excluding_small_groups": round(reduced_rates[code], 2),
            "difference": round(difference, 2),
            "material_difference": abs(difference) >= MATERIAL_DIFFERENCE,
            "note": f"{len(small_states)} states/UTs excluded: "
                    + "; ".join(labels["v024"][int(s)] for s in small_states),
        })

    # (b) State-level rank correlations, from Analysis 5.
    corr_path = RESULTS_DIR / "analysis_5" / "06_state_level_correlations.csv"
    if corr_path.exists():
        corr = pd.read_csv(corr_path)
        for measure in corr["employment_measure"].unique():
            values = corr[corr.employment_measure == measure].set_index("states_included")[
                "spearman_correlation_with_pct_higher_education"]
            rows.append({
                "check": "state-level Spearman correlation: % higher education vs employment (Analysis 5)",
                "item": measure,
                "all_groups": values.iloc[0],
                "excluding_small_groups": values.iloc[1],
                "difference": round(values.iloc[1] - values.iloc[0], 3),
                "material_difference": None,
                "note": "both |r| < 0.3 (weak)" if values.abs().max() < 0.3 else "at least one |r| >= 0.3",
            })

    # (c) Analysis 5 pattern classification with a stricter age-cell minimum.
    gap_path = RESULTS_DIR / "analysis_5" / "05_state_education_gap_vs_national.csv"
    if gap_path.exists():
        gaps = pd.read_csv(gap_path)
        gaps = gaps[gaps.v024 != 0]
        # Analysis 5's rule: assess a state only if every age cell has >= 10 women.
        # Stricter version: require >= 25 (the DHS suppression threshold).
        assessed_10 = gaps[~gaps.pattern.str.startswith("not assessed")]
        assessed_25 = assessed_10[assessed_10.smallest_age_cell_n >= 25]
        differing_10 = assessed_10[assessed_10.pattern.str.startswith("differs")]
        differing_25 = assessed_25[assessed_25.pattern.str.startswith("differs")]
        for item, value_10, value_25 in [("number of states assessed", len(assessed_10), len(assessed_25)),
                                         ("number of states classified as differing", len(differing_10),
                                          len(differing_25))]:
            rows.append({
                "check": "Analysis 5 classification: min age cell 10 (all_groups) vs 25 (excluding_small_groups)",
                "item": item,
                "all_groups": value_10,
                "excluding_small_groups": value_25,
                "difference": value_25 - value_10,
                "material_difference": None,
                "note": "differing at 10: " + "; ".join(differing_10.state)
                        + " | differing at 25: " + "; ".join(differing_25.state),
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 6. Data file integrity
# ---------------------------------------------------------------------------
def scripts_never_write_data():
    """Look through every script for code that could write a Stata file or
    open the data file for writing. This is a simple text search, not proof,
    but together with the fingerprint check it is strong evidence."""
    suspicious = re.compile(r"to_stata|StataWriter|open\([^)]*DATA_PATH[^)]*['\"][wa]")
    findings = []
    for path in sorted((ROOT / "scripts").glob("*.py")):
        if path.name == "data_quality_checks.py":
            continue  # this file contains the search pattern itself
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            if suspicious.search(line):
                findings.append(f"{path.name}:{number}")
    return findings


def integrity_checks():
    after = dta_fingerprint()
    before = json.loads(FINGERPRINT_BEFORE.read_text()) if FINGERPRINT_BEFORE.exists() else None
    findings = scripts_never_write_data()

    rows = [
        ("size_bytes_now", after["size_bytes"], ORIGINAL_DTA_SIZE, after["size_bytes"] == ORIGINAL_DTA_SIZE),
        ("modified_now", after["modified"], ORIGINAL_DTA_MTIME, after["modified"] == ORIGINAL_DTA_MTIME),
    ]
    if before:
        rows.append(("sha256_before_scripts_1_5 vs now", after["sha256"], before["sha256"],
                     after["sha256"] == before["sha256"]))
        rows.append(("fingerprint_before_recorded_at", before.get("recorded_at"), "", True))
    else:
        rows.append(("sha256_before_scripts_1_5 vs now", after["sha256"],
                     "no 'before' fingerprint (run run_all.py)", None))
    rows.append(("scripts_writing_to_data_file", "; ".join(findings) or "none found", "none", not findings))
    return pd.DataFrame(rows, columns=["check", "observed", "expected", "passed"])


def main():
    print(f"Analysis 6: reading {len(VARS)} columns...")
    raw = read_columns(VARS)
    print(f"  {len(raw):,} observations")

    codebook = load_codebook()
    labels = value_labels(codebook, LABELLED_VARS)
    cleaned = add_age_group(clean_variables(raw, labels))

    crosstab, mismatches = age_crosstab(raw, cleaned, labels)
    print(f"  v012 vs v013 mismatches: {mismatches}")
    print("  computing data file checksum (reads 5.2 GB, read-only)...")
    integrity = integrity_checks()

    tables = {
        "01_missingness": missingness(raw, cleaned, codebook),
        "02_code_audit": code_audit(raw, labels, codebook),
        "03_sample_sizes": sample_sizes(cleaned, labels),
        "04_small_cell_summary": small_cell_summary(),
        "05_v012_v013_crosstab": (crosstab, True),
        "06_weighted_vs_unweighted": weighted_vs_unweighted(cleaned, labels),
        "07_small_group_sensitivity": small_group_sensitivity(cleaned, labels),
        "08_data_file_integrity": integrity,
    }
    write_tables(tables, OUT_DIR)

    comparison = tables["06_weighted_vs_unweighted"]
    print(f"  weighted vs unweighted: {int(comparison.material_difference.sum())} of "
          f"{len(comparison)} estimates differ by >= {MATERIAL_DIFFERENCE} points")
    print(f"  integrity checks passed: {integrity.passed.tolist()}")


if __name__ == "__main__":
    main()
