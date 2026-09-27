"""Shared helpers for the India DHS 2019-21 (NFHS-5) analysis scripts.

Every analysis script imports from here, so that all analyses use exactly the
same rules for:
    - reading the Stata file (chunked, only the needed columns, read-only)
    - cleaning (which codes count as valid answers)
    - weighting (v005 / 1,000,000)
    - small-sample flags
    - age standardization

This file does not produce any results by itself.
"""

import hashlib
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths (worked out from this file's location, so scripts run from any folder)
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "data" / "IAIR7EFL.DTA"
CODEBOOK_PATH = ROOT / "docs" / "dhs_codebook.csv"
RESULTS_DIR = ROOT / "docs" / "results"

# 20,000 rows per chunk keeps peak memory under ~1 GB. (Each full row is
# ~7 KB on disk; we only keep a few columns from each chunk.)
CHUNK_ROWS = 20_000

# Size and modification time of the original file, recorded on 2026-09-25
# before any analysis was run. Used by data_quality_checks.py to confirm the
# file was never changed.
ORIGINAL_DTA_SIZE = 5_196_403_097
ORIGINAL_DTA_MTIME = "2026-09-25 20:23:22"

# Standard DHS 5-year age groups (the same groups as v013's value labels).
# pd.cut with right=False makes each bin include its left edge: [15, 20) = 15-19.
AGE_BINS = [15, 20, 25, 30, 35, 40, 45, 50]
AGE_LABELS = ["15-19", "20-24", "25-29", "30-34", "35-39", "40-44", "45-49"]

# DHS reporting convention for small samples (unweighted number of cases):
#   fewer than 25 -> percentage is suppressed (not shown)
#   25 to 49      -> shown, but flagged as unreliable
SUPPRESS_BELOW = 25
FLAG_BELOW = 50


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------
def read_columns(columns, path=DATA_PATH, chunksize=CHUNK_ROWS):
    """Read only `columns` from the Stata file, `chunksize` rows at a time.

    Why chunks: the file is 5.2 GB, far too big to load at once.
    Why `columns=` inside each read: pandas then drops the other ~5,960
    columns *before* its slow conversion steps. That is ~3x faster and uses
    ~3x less memory than reading whole chunks and selecting columns afterwards.

    StataReader only ever reads the file; it cannot modify it.
    """
    parts = []
    with pd.io.stata.StataReader(path, convert_categoricals=False) as reader:
        while True:
            try:
                chunk = reader.read(nrows=chunksize, columns=columns)
            except StopIteration:  # pandas signals "no rows left" this way
                break
            if len(chunk) == 0:
                break
            parts.append(chunk)
    return pd.concat(parts, ignore_index=True)


def dta_fingerprint(path=DATA_PATH):
    """Size, modification time and SHA-256 checksum of the data file.

    The checksum is a 64-character "fingerprint" of the file's contents: if even
    one byte changed, the checksum would be completely different. Reading the
    file to compute it does not change it.
    """
    sha = hashlib.sha256()
    with open(path, "rb") as f:  # "rb" = read-only, binary
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            sha.update(block)
    stat = path.stat()
    return {
        "size_bytes": stat.st_size,
        "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        "sha256": sha.hexdigest(),
    }


# ---------------------------------------------------------------------------
# Codebook (built earlier from the Stata metadata; see docs/dhs_codebook.csv)
# ---------------------------------------------------------------------------
def load_codebook():
    return pd.read_csv(CODEBOOK_PATH, dtype=str, keep_default_na=False).set_index("variable_name")


def value_labels(codebook, variables):
    """{variable: {code: meaning}} for each variable, from the codebook."""
    labels = {}
    for var in variables:
        mapping = json.loads(codebook.loc[var, "value_labels"])
        labels[var] = {int(code): meaning for code, meaning in mapping.items()}
    return labels


# ---------------------------------------------------------------------------
# Cleaning
# ---------------------------------------------------------------------------
# Valid answers for each coded variable. Any other value is treated as missing.
# These come straight from the codebook's value labels; DHS "don't know",
# "inconsistent" and "missing" codes (e.g. 9, 97, 98, 99) are deliberately NOT
# in these sets, so they become missing.
VALID_CODES = {
    "v025": {1, 2},                 # 1 = urban, 2 = rural
    "v106": {0, 1, 2, 3},           # no education, primary, secondary, higher
    "v714": {0, 1},                 # 0 = no, 1 = yes
    "v190": {1, 2, 3, 4, 5},        # poorest ... richest
}
# v024 (state) and v013 (age group) use every code in their value labels.
CODES_FROM_LABELS = ["v024", "v013"]

# Variables that are plain numbers (no value labels for real answers):
# keep values inside the range, anything else becomes missing.
VALID_RANGES = {
    "v133": (0, 30),   # years of education; drops 97 = inconsistent, 98/99
    "v012": (15, 49),  # age; the survey interviewed women aged 15-49
}


def valid_codes_for(var, labels):
    if var in CODES_FROM_LABELS:
        return set(labels[var])
    return VALID_CODES[var]


def clean_variables(raw, labels):
    """Return a cleaned copy of `raw`: every non-valid value becomes NaN.

    Rule 1: Stata's own missing values (., .a-.z) are already NaN, because
            pandas converts them when reading.
    Rule 2: only valid codes/ranges (above) are kept; everything else -> NaN.
    Rule 3: the weight column `w` is v005 / 1,000,000 (see below).

    Missing values are handled per variable, not per woman: a woman with a
    missing v714 still counts in tables that don't use v714.
    """
    cleaned = pd.DataFrame(index=raw.index)
    for var in raw.columns:
        if var in VALID_CODES or var in CODES_FROM_LABELS:
            cleaned[var] = raw[var].where(raw[var].isin(valid_codes_for(var, labels)))
        elif var in VALID_RANGES:
            low, high = VALID_RANGES[var]
            cleaned[var] = raw[var].where(raw[var].between(low, high))

    # v005 is stored as an integer with 6 implied decimals (193444 = 0.193444).
    # Dividing by 1,000,000 does not change any percentage (it cancels out in
    # the ratio), but keeps weighted totals on the right scale.
    if "v005" in raw.columns:
        cleaned["w"] = raw["v005"] / 1_000_000
    return cleaned


def add_age_group(cleaned):
    """Add an `age_group` column (standard DHS 5-year groups) from v012."""
    cleaned = cleaned.copy()
    cleaned["age_group"] = pd.cut(cleaned["v012"], bins=AGE_BINS, labels=AGE_LABELS, right=False)
    return cleaned


# ---------------------------------------------------------------------------
# Weighted estimates
# ---------------------------------------------------------------------------
def as_list(columns):
    return [columns] if isinstance(columns, str) else list(columns)


def weighted_pct(data, var, by=None):
    """Weighted % of each category of `var`, optionally within groups `by`.

        % = 100 * sum(w for women in the category) / sum(w for women with a valid answer)

    Women with a missing `var` (or `by`) are left out of the denominator.
    """
    data = data.dropna(subset=[var] + ([by] if by else []))
    keys = ([by] if by else []) + [var]
    weight_sums = data.groupby(keys, observed=True)["w"].sum()
    if by:
        denominator = weight_sums.groupby(level=0, observed=True).transform("sum")
    else:
        denominator = weight_sums.sum()
    return 100 * weight_sums / denominator


def weighted_rate(data, group_cols, value="v714"):
    """Weighted % with `value` == 1 within each group (value must be 0/1).

    For a 0/1 variable, the weighted % of 1s equals
        100 * sum(w * value) / sum(w)
    which is the same formula as weighted_pct, written for a yes/no variable.
    """
    group_cols = as_list(group_cols)
    data = data.dropna(subset=[value] + group_cols)
    data = data.assign(weighted_value=data[value] * data["w"])
    groups = data.groupby(group_cols, observed=True)
    return 100 * groups["weighted_value"].sum() / groups["w"].sum()


def weighted_mean(data, var):
    data = data.dropna(subset=[var])
    return np.average(data[var], weights=data["w"])


def unweighted_rate(data, group_cols, value="v714"):
    """Plain (unweighted) % with `value` == 1, for comparison with weighted results."""
    group_cols = as_list(group_cols)
    data = data.dropna(subset=[value] + group_cols)
    return 100 * data.groupby(group_cols, observed=True)[value].mean()


# ---------------------------------------------------------------------------
# Small-sample flags
# ---------------------------------------------------------------------------
def sample_flag(n):
    """DHS convention for a percentage based on `n` unweighted cases."""
    if n < SUPPRESS_BELOW:
        return "suppressed (n<25)"
    if n < FLAG_BELOW:
        return "unreliable (n 25-49)"
    return "ok"


def is_suppressed(flag):
    return flag.startswith("suppressed")


def standardized_flag(smallest_age_cell_n):
    """Flag for an age-standardized rate, based on its smallest age cell.

    A standardized rate combines 7 age-specific rates. If one of them rests on
    very few women, the standardized rate is noisier than its total n suggests.
    """
    if smallest_age_cell_n == 0:
        return "not computed (an age group has no cases)"
    if smallest_age_cell_n < SUPPRESS_BELOW:
        return "caution (an age cell has n<25)"
    if smallest_age_cell_n < FLAG_BELOW:
        return "caution (an age cell has n 25-49)"
    return "ok"


# ---------------------------------------------------------------------------
# Age standardization (descriptive, not a model)
# ---------------------------------------------------------------------------
def standard_age_shares(analytic):
    """The standard population: weighted age distribution of ALL women who
    answered v714. Using one shared standard makes every standardized rate in
    every analysis directly comparable."""
    shares = weighted_pct(analytic, "age_group") / 100
    shares.index = shares.index.astype(str)
    return shares.reindex(AGE_LABELS)


def age_standardized_rate(group_data, shares):
    """Direct age standardization for one group of women.

        standardized rate = sum over age groups a of  share_a * rate_a

    i.e. the employment rate this group would have if its age mix were the
    same as the standard population's. Returns (rate or None, smallest age cell n).
    """
    counts = group_data["age_group"].astype(str).value_counts().reindex(AGE_LABELS, fill_value=0)
    smallest = int(counts.min())
    if smallest == 0:
        return None, smallest
    rates = weighted_rate(group_data, "age_group")
    rates.index = rates.index.astype(str)
    rates = rates.reindex(AGE_LABELS)
    return float((shares * rates).sum()), smallest


# ---------------------------------------------------------------------------
# Shared table builder for "education x employment, split by a grouping
# variable" (used by the urban/rural and wealth analyses)
# ---------------------------------------------------------------------------
def education_employment_by_group(cleaned, analytic, group_var, labels, shares):
    """Build the standard set of tables for one grouping variable (e.g. v025).

    `cleaned`  : all women (used for education distributions and sample sizes)
    `analytic` : women with valid v714, v106, age and group (used for employment)
    """
    group_labels = labels[group_var]
    edu_labels = labels["v106"]
    tables = {}

    # 1. Sample sizes, and how many answered the employment question.
    rows = []
    for code, meaning in group_labels.items():
        women = cleaned[cleaned[group_var] == code]
        answered = analytic[analytic[group_var] == code]
        rows.append({
            group_var: code,
            "group": meaning,
            "n_women": len(women),
            "n_answered_v714": len(answered),
            "pct_answered_v714_unweighted": round(100 * len(answered) / len(women), 2),
            "weighted_mean_age_of_v714_respondents": round(weighted_mean(answered, "v012"), 2),
        })
    tables["01_sample_sizes"] = pd.DataFrame(rows)

    # 2. Education distribution (all women, not just the v714 subsample).
    edu = weighted_pct(cleaned, "v106", by=group_var).unstack("v106").round(2)
    edu.columns = [f"pct_{edu_labels[int(c)].replace(' ', '_')}" for c in edu.columns]
    edu.insert(0, "n_women", cleaned.dropna(subset=["v106"]).groupby(group_var).size())
    edu.insert(0, "group", [group_labels[int(c)] for c in edu.index])
    edu.index = edu.index.astype(int)
    tables["02_education_distribution"] = edu.reset_index()

    # 3. Employment by group: crude and age-standardized.
    crude = weighted_rate(analytic, group_var)
    rows = []
    for code, meaning in group_labels.items():
        group_data = analytic[analytic[group_var] == code]
        std_rate, smallest = age_standardized_rate(group_data, shares)
        rows.append({
            group_var: code,
            "group": meaning,
            "n_answered_v714": len(group_data),
            "crude_pct_currently_working": round(crude[code], 2),
            "age_standardized_pct_currently_working": None if std_rate is None else round(std_rate, 2),
            "smallest_age_cell_n": smallest,
            "standardized_reliability": standardized_flag(smallest),
        })
    tables["03_employment_by_group"] = pd.DataFrame(rows)

    # 4. Employment by education x group: crude and age-standardized, per cell.
    crude_cells = weighted_rate(analytic, [group_var, "v106"])
    rows = []
    for code, meaning in group_labels.items():
        for edu_code, edu_meaning in edu_labels.items():
            cell = analytic[(analytic[group_var] == code) & (analytic["v106"] == edu_code)]
            n = len(cell)
            flag = sample_flag(n)
            std_rate, smallest = age_standardized_rate(cell, shares) if n > 0 else (None, 0)
            rows.append({
                group_var: code,
                "group": meaning,
                "v106": edu_code,
                "education": edu_meaning,
                "n_answered_v714": n,
                "crude_pct_currently_working": None if is_suppressed(flag) else round(crude_cells[(code, edu_code)], 2),
                "crude_reliability": flag,
                "age_standardized_pct_currently_working": None if std_rate is None else round(std_rate, 2),
                "smallest_age_cell_n": smallest,
                "standardized_reliability": standardized_flag(smallest),
            })
    cells = pd.DataFrame(rows)
    tables["04_employment_by_education_and_group"] = cells

    # 5 and 6. The same cells as easy-to-read grids (rows = education, columns = group).
    edu_order = [edu_labels[c] for c in sorted(edu_labels)]
    group_order = [group_labels[c] for c in sorted(group_labels)]
    for name, column in [("05_crude_grid", "crude_pct_currently_working"),
                         ("06_age_standardized_grid", "age_standardized_pct_currently_working")]:
        grid = cells.pivot(index="education", columns="group", values=column)
        tables[name] = grid.reindex(index=edu_order, columns=group_order).reset_index()

    # 7. Education gaps within each group, to compare the *shape* of the
    #    education-employment relationship across groups.
    rows = []
    for code, meaning in group_labels.items():
        row = {group_var: code, "group": meaning}
        for kind, column in [("crude", "crude_pct_currently_working"),
                             ("age_std", "age_standardized_pct_currently_working")]:
            rates = cells[cells[group_var] == code].set_index("v106")[column]
            row[f"{kind}_gap_secondary_minus_no_education"] = _difference(rates.get(2), rates.get(0))
            row[f"{kind}_gap_higher_minus_secondary"] = _difference(rates.get(3), rates.get(2))
        rows.append(row)
    tables["07_education_gaps"] = pd.DataFrame(rows)
    return tables


def _difference(a, b):
    if a is None or b is None or pd.isna(a) or pd.isna(b):
        return None
    return round(a - b, 2)


# ---------------------------------------------------------------------------
# Writing results
# ---------------------------------------------------------------------------
def write_tables(tables, out_dir):
    """Write each table to `out_dir/<name>.csv`.

    `tables` maps a name to either a DataFrame (index not written) or a
    (DataFrame, keep_index) pair.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, table in tables.items():
        keep_index = False
        if isinstance(table, tuple):
            table, keep_index = table
        filename = name if name.endswith(".csv") else f"{name}.csv"
        table.to_csv(out_dir / filename, index=keep_index)
        print(f"  wrote {(out_dir / filename).relative_to(ROOT)}")
