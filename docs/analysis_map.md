# Analysis map

How this project gets from a 5.2 GB Stata file to the findings in
[`final_summary.md`](final_summary.md). Each stage feeds the next.

```
 1. RAW DATA          data/IAIR7EFL.DTA  (5.2 GB, never modified, not in git)
        │
        ▼
 2. METADATA          docs/dhs_codebook.csv, docs/dhs_codebook.md
        │             (variable labels + value labels, read from the file's header)
        ▼
 3. SCRIPTS           scripts/*.py  — one per analysis, all sharing dhs_utils.py
        │
        ▼
 4. READING           read_columns(): 20,000 rows at a time, only the needed columns
        │
        ▼
 5. CLEANING          clean_variables(): invalid / special codes → missing
        │             add_age_group(): v012 → DHS 5-year groups
        ▼
 6. WEIGHTED          weighted_pct(), weighted_rate(): weight w = v005 / 1,000,000
    ANALYSIS          age_standardized_rate(): same age mix for every group
        │             sample_flag(): DHS small-sample rules
        ▼
 7. RESULTS           docs/results/**/*.csv  — plain tables, one per question
        │
        ▼
 8. INTERPRETATION    README.md (method per analysis), docs/final_summary.md (findings)
```

## 1. Raw data

`data/IAIR7EFL.DTA` is the India DHS 2019–21 (NFHS-5) Individual Recode: one row
per woman aged 15–49 (724,115 rows) and 5,972 columns. It is listed in
`.gitignore` so it can never be committed. No script writes to it; Analysis 6
checks this with a SHA-256 checksum taken before and after the other analyses.

## 2. Metadata / codebook

A Stata file stores descriptions next to the data. We extracted them once into:

- `docs/dhs_codebook.csv` — machine-readable: `variable_name`, `variable_label`,
  `stata_type`, `value_label_name`, `value_labels` (JSON, e.g. `{"1": "urban", "2": "rural"}`).
- `docs/dhs_codebook.md` — the same, human-readable and searchable.

Every script takes variable meanings and code labels from the CSV codebook, not
from memory. `analysis.py` (the very first script) shows how to read this
metadata directly with `StataReader`.

## 3. Scripts

| Script | Role | Reads from the data |
|---|---|---|
| `dhs_utils.py` | Shared helpers (no results of its own) | — |
| `education_employment_summary.py` | Analysis 1: education and employment, national and by state | v024 v025 v106 v133 v714 v190 v005 |
| `education_employment_age.py` | Analysis 2: accounting for age | + v012 v013 |
| `education_employment_urban_rural.py` | Analysis 3: urban vs rural | v025 v106 v714 v005 v012 |
| `education_employment_wealth.py` | Analysis 4: wealth quintiles | v190 v106 v714 v005 v012 |
| `state_comparison.py` | Analysis 5: state patterns (also reads Analysis 1's CSVs) | v024 v106 v714 v005 v012 |
| `data_quality_checks.py` | Analysis 6: robustness and data quality (also reads 2–5's CSVs) | all 9 variables |
| `run_all.py` | Runs 1–6 in order, records the data fingerprint and runtimes | — |

Why a shared module: if the cleaning rule for, say, `v106` lived in six
different files, they could quietly drift apart. With `dhs_utils.py`, every
analysis uses exactly the same rules, and a fix in one place fixes them all.

## 4. Reading

`read_columns()` in `dhs_utils.py`:

- opens the file with `pandas.io.stata.StataReader` (read-only);
- reads 20,000 rows at a time, asking only for the needed columns;
- stitches the chunks together.

The whole file is still scanned (rows are stored one after another), but only
a few columns are kept, so each script needs ~12 seconds and under 1 GB of
memory instead of trying to load 5.2 GB.

## 5. Cleaning

`clean_variables()` applies the same three rules to every analysis:

1. Stata's own missing values become `NaN` automatically.
2. Only valid answers are kept (the table below); anything else, including DHS
   codes such as 97 = inconsistent or 98 = don't know, becomes `NaN`.
3. The weight column `w = v005 / 1,000,000` is added.

| Variable | Valid values (from the codebook) |
|---|---|
| v024 state | its 36 labelled codes |
| v025 residence | 1 urban, 2 rural |
| v106 education | 0 none, 1 primary, 2 secondary, 3 higher |
| v133 years of education | 0–30 |
| v714 currently working | 0 no, 1 yes |
| v190 wealth | 1 poorest … 5 richest |
| v012 age | 15–49 |
| v013 age group | its 7 labelled codes |

Missing values are dropped per calculation, not per woman: a woman who wasn't
asked `v714` still counts in the education tables.

Analysis 6 confirmed that, in practice, none of these variables contain
special or out-of-range codes. The only missing data is `v714`, missing for 85%
of women.

## 6. Weighted analysis

- **Weighted percentage:** `100 × Σw(in category) ÷ Σw(valid answers)`.
  Weights correct for NFHS sampling some groups more heavily than others.
- **Age standardization (direct):** `Σ over age groups (standard share × age-specific rate)`.
  The standard is the weighted age distribution of all 108,785 `v714`
  respondents, the same in every analysis, so standardized rates can be
  compared across analyses. It answers "what would this group's employment
  rate be if it had the same age mix as everyone else?"
- **Small samples (DHS convention):** fewer than 25 unweighted cases → the
  percentage is suppressed. 25–49 cases → shown but flagged as unreliable.
  Standardized rates are flagged when any of their age cells is small.
- **Not done:** survey-design standard errors / confidence intervals (need
  `v021`, `v022`), regression models, causal analysis.

## 7. Results

```
docs/results/
├── 01_… 07_*.csv       Analysis 1 (national + state)
├── analysis_2/          age
├── analysis_3/          urban / rural
├── analysis_4/          wealth
├── analysis_5/          states
├── analysis_6/          data quality + data file fingerprint
└── run_log.csv          runtime of each script in the last run_all.py
```

Every table reports unweighted `n` next to weighted percentages, so you can
always see how many women a number is based on.

## 8. Interpretation

- `README.md` — per-analysis method, variables, and limitations.
- `docs/final_summary.md` — main descriptive findings, what cannot be
  concluded, and possible next questions.

All findings are descriptive associations in cross-sectional survey data. They
do not show that education, age, wealth or place of residence *causes* any
difference in employment.
