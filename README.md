# India DHS 2019–21 (NFHS-5) — Individual Recode analysis

Learning project using the India Standard DHS 2019–21 Individual Recode
(`data/IAIR7EFL.DTA`, 724,115 women aged 15–49 × 5,972 variables). The data file
is not included in this repository (see `.gitignore`); request it from
[The DHS Program](https://dhsprogram.com/).

- `docs/dhs_codebook.csv` / `docs/dhs_codebook.md` — every variable's label, Stata type and value labels, taken from the file's metadata.
- `scripts/` — analysis scripts (Python 3 + pandas + numpy only). Run from the project root or anywhere.
- `docs/results/` — every result table, as CSV.
- **`docs/final_summary.md`** — what the six analyses found, and what they can't tell us.
- **`docs/analysis_map.md`** — how the project fits together, from raw data to interpretation.
- `analysis.py` — the first inspection script (reads 100 rows and the metadata).
- **`src/` + `app.py`**: an agentic RAG research and outreach assistant built on the data (below).
- **`docs/how_it_works.md`**: a ground-up explanation of the assistant's architecture.

## Research & outreach assistant

Ask questions in plain language ("What does v012 mean?", "What percentage of
rural women in Bihar own a mobile phone?", "Identify an underserved population
and recommend outreach organizations") and get an answer with its evidence:
codebook definitions, the exact SQL behind every number, sources for every
external claim, and every statement labelled as a fact or an inference.

```
USER -> ORCHESTRATOR -> DATA AGENT (documentation RAG + SQL + Python analysis)
                     -> OUTREACH AGENT (curated knowledge base + web research)
                     -> SYNTHESIS -> answer + evidence + trace
```

### Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m src.data.pipeline     # data/IAIR7EFL.DTA -> data/processed/nfhs5_women.sqlite (~25 s)
.venv/bin/python -m src.rag.index         # documentation + outreach indexes -> data/index/ (~2 s)
cp .env.example .env                      # optional: add ANTHROPIC_API_KEY for LLM mode
```

### Run

```bash
.venv/bin/streamlit run app.py                                    # web interface
.venv/bin/python -m src.cli "What does v012 mean?"                 # terminal
.venv/bin/python -m pytest                                        # tests (54 + 1 known weakness)
```

### Two modes

| | Offline (no API key) | LLM mode (`ANTHROPIC_API_KEY` set) |
|---|---|---|
| Routing | keyword rules (`src/agents/router.py`) | Claude, structured JSON decision |
| Data Agent | follows the rule-based plan | Claude chooses tools in a tool-use loop |
| Outreach Agent | curated knowledge base (9 organizations verified 2026-09-27) + rubric | + live web search; unsourced facts are dropped |
| Final answer | template over labelled statements | Claude-written summary, with a check for numbers not in the evidence |
| Numbers | always SQL/Python | always SQL/Python |

LLM mode uses `claude-opus-5` with adaptive thinking and server-side refusal
fallbacks (`fallbacks: "default"`); change `LLM_MODEL` in `.env`. Its wiring is
tested with a fake client, but it has **not yet been run against the live
API** (no key was available when it was built).

### Layout

```
src/
  config.py            settings from environment variables
  llm.py               Claude API wrapper (optional)
  data/                variables.py (cleaning rules), pipeline.py (DTA -> SQLite), loader.py
  analysis/            database.py (read-only), queries.py (SQL tool), stats.py (Python analysis)
  rag/                 documents.py (chunking), embeddings.py, vector_store.py, retriever.py, index.py
  tools/               registry.py, data_tools.py (the tools agents can call)
  outreach/            profile.py (data -> outreach hand-off), knowledge_base.py, web_research.py
  agents/              orchestrator.py, router.py, data_agent.py, outreach_agent.py, synthesis.py, trace.py, facts.py
  app/ui.py            Streamlit interface
documents/             RAG corpus: methodology.md, data_dictionary.md, outreach/organizations.json
tests/                 unit tests (synthetic data), integration tests (real data), LLM tests (fake client)
```

## Descriptive analyses (Analyses 1–6)

```bash
python3 scripts/run_all.py
```

Runs Analyses 1–6 in order (about 80 seconds in total), records the data file's
fingerprint before they start, and writes `docs/results/run_log.csv` with each
script's runtime. Each script can also be run on its own. Every script reads
only the columns it needs, 20,000 rows at a time, and never writes to the data
file.

## Analysis 1: Education and employment

```bash
python3 scripts/education_employment_summary.py
```

Writes seven tables to `docs/results/` (about 12 seconds; the full file is
scanned once in 20,000-row chunks, keeping only the 7 variables below).

### 1. Research question

How does women's educational attainment vary across Indian states, and how is
it associated with current employment?

### 2. Variables used

| Variable | Meaning | Valid codes |
|---|---|---|
| `v024` | state | 36 state/UT codes (1–37, no 26) |
| `v025` | type of place of residence | 1 = urban, 2 = rural |
| `v106` | highest educational level | 0 = no education, 1 = primary, 2 = secondary, 3 = higher |
| `v133` | education in single years | 0–30 years |
| `v714` | respondent currently working | 0 = no, 1 = yes |
| `v190` | wealth index (national quintiles) | 1 = poorest … 5 = richest |
| `v005` | women's individual sample weight | integer, 6 implied decimals |

### 3. Weight

Each woman is weighted by `w = v005 / 1,000,000`. NFHS deliberately
over-samples some groups (e.g. 24.8% of interviewed women are urban, but 32.5%
after weighting), so unweighted percentages are biased.

Weighted % = 100 × Σ w (women in the category) ÷ Σ w (women with a valid answer).

The same `v005` weight is used for the state tables. Within a state, rescaling
all weights by a constant does not change a percentage, so this should match
state-weight (`sweight`) results. Later verified: within each state
`sweight` / `v005` is constant up to rounding (see `documents/data_dictionary.md`).

### 4. Missing and special codes

1. Stata missing values (`.`, `.a`–`.z`) are read as `NaN`.
2. Only the valid codes in the table above are kept. Any other value (DHS codes
   such as 9, 97 = inconsistent, 98 = don't know, 99) is set to `NaN`.
3. Missing values are excluded per variable, not per woman: a woman with no
   `v714` answer still counts in the education tables.

In this file no special codes actually occur in these 7 variables, so rule 2
removes nothing. The only missing data is the Stata-missing `v714` values.

### 5. Limitations

- **`v714` is missing for 615,330 women (85%).** Only 108,785 answered, most
  because employment was asked only in the ~15% of households selected for the
  NFHS-5 state module (later verified: `v714` is present exactly when `ssmod = 1`). All employment
  figures rest on this subsample, and small states have few answers (e.g.
  Chandigarh 129, Lakshadweep 173, Goa 303).
- **The `v005` weight is assumed valid for the employment subsample.** This holds
  if the subsample was drawn evenly within sampling areas; to be checked
  against the NFHS-5 report or the DHS Indicators code.
- **No confidence intervals.** Proper standard errors need the survey design
  variables (`v021` cluster, `v022` strata), which were not used. All results
  are point estimates.
- **Associations are not causal.** Employment by education is U-shaped (33.8%
  working with no education vs 20.7% with secondary), but this is likely
  confounded by age (many 15–19-year-olds are still studying), wealth and
  urban/rural residence. None of these are controlled for yet.

### Output files (`docs/results/`)

| File | Contents |
|---|---|
| `01_missing_values.csv` | Missing counts per variable, before and after cleaning |
| `02_frequencies.csv` | Category counts for `v106`, `v714`, `v025`, `v190` (unweighted and weighted %) |
| `03_national_education.csv` | Weighted % by education level |
| `04_national_employment.csv` | Weighted % currently working |
| `05_state_education.csv` | Weighted % by education level and mean years, per state |
| `06_state_employment.csv` | Weighted % currently working, per state, with sample size |
| `07_employment_by_education.csv` | Weighted % currently working by education level |

## Analysis 2: Education and employment, accounting for age

```bash
python3 scripts/education_employment_age.py
```

Writes seven tables to `docs/results/analysis_2/` (about 12 seconds). Uses the
same shared reading, cleaning and weighting functions (`scripts/dhs_utils.py`),
so the rules above apply unchanged. Analysis 1's outputs are not modified.

### Research question

Does the relationship between women's education and current employment change
after accounting for age?

### Variables and groups

The seven Analysis 1 variables, plus:

| Variable | Meaning | Handling |
|---|---|---|
| `v012` | respondent's current age | valid 15–49; anything else → `NaN` (none found) |
| `v013` | age in 5-year groups | consistency check only |

Age groups are the standard DHS 5-year groups: 15–19, 20–24, 25–29, 30–34,
35–39, 40–44, 45–49. Groups derived from `v012` match `v013` for all 724,115
women. `v012` has no missing or out-of-range values.

The analytic sample is the **108,785 women (15.0%) who answered `v714`**. The
answer rate is 14.9–15.2% in every age group, so the missing employment data
is not concentrated in any age group. That fits a random subsample, but doesn't
prove it.

### Method (descriptive only, no models)

1. Weighted % currently working by education, overall (the "crude" rate; same as Analysis 1).
2. The same, within each age group.
3. **Direct age standardization:** each education group's age-specific rates
   are re-weighted to the same age mix (the weighted age distribution of all
   `v714` respondents): standardized rate = Σ (age share × age-specific rate).

Following DHS convention, cells with fewer than 25 unweighted cases are
suppressed and 25–49 are flagged as unreliable. No cell was affected; the
smallest is 652 (higher education, age 45–49).

### Findings

| Education | Crude % working | Age-standardized % working |
|---|---:|---:|
| No education | 33.8 | 28.5 |
| Primary | 30.7 | 28.2 |
| Secondary | 20.7 | 22.9 |
| Higher | 23.5 | 25.2 |

- Employment rises steeply with age: 11.1% at 15–19 to 35.6% at 40–44.
- Education differs sharply by age: 48.5% of women aged 45–49 have no
  education, compared with 4.4% of those aged 15–19.
- So part of the crude pattern reflects age composition. Women with no
  education are older on average, and older women are more likely to work.
  After age standardization, the gap between no education and secondary
  shrinks from 13.1 to 5.6 percentage points.
- The pattern does not disappear. Within most age groups, secondary-educated
  women have the lowest or near-lowest employment rate, and among women aged
  40–49 the higher-educated are again among the most likely to work (37.8–38.1%).
- These are associations, not causal effects.

### Limitations

- **The employment question covers only 15% of women** (`v714` missing for 85%).
  Everything here rests on that subsample, and the `v005` weight is assumed to
  be valid for it.
- **No confidence intervals.** The survey design (`v021`, `v022`) is not yet
  used, so small differences (e.g. 1–2 points between cells) may not be meaningful.
- **Only age is accounted for.** Wealth, urban/rural residence, state, marital
  status and number of children may explain more of the pattern, and none are
  adjusted for here.
- **Cross-sectional data.** Differences between age groups mix ageing with
  generational change, so this can't show how an individual woman's
  employment changes as she gets older.

### Output files (`docs/results/analysis_2/`)

| File | Contents |
|---|---|
| `01_age_checks.csv` | `v012` missing / out-of-range counts, range, agreement with `v013` |
| `02_age_distribution_and_v714_coverage.csv` | Women and `v714` respondents per age group, answer rate, weighted age shares |
| `03_employment_by_age.csv` | Weighted % currently working by age group |
| `04_employment_by_education_and_age.csv` | Weighted % working per age × education cell, with n and reliability flag |
| `05_education_mix_by_age.csv` | Weighted education distribution within each age group |
| `06_crude_vs_age_standardized.csv` | Crude vs age-standardized % working by education |
| `07_employment_by_education_and_age_wide.csv` | Table 04 as an age × education grid |

## Analyses 3–6

These follow the same rules as Analyses 1–2 (same cleaning, same `v005`
weight, same age standardization, same small-sample flags). Results and
limitations are summarized in [`docs/final_summary.md`](docs/final_summary.md).

| # | Question | Script | Results |
|---|---|---|---|
| 3 | Does the education–employment relationship differ between urban and rural India? | `scripts/education_employment_urban_rural.py` | `docs/results/analysis_3/` |
| 4 | How does household wealth relate to women's education and employment? | `scripts/education_employment_wealth.py` | `docs/results/analysis_4/` |
| 5 | Which states stand out on higher education, employment, and the education–employment pattern? | `scripts/state_comparison.py` | `docs/results/analysis_5/` |
| 6 | Robustness and data quality: missingness, codes, sample sizes, age consistency, weighted vs unweighted, small groups, data file integrity | `scripts/data_quality_checks.py` | `docs/results/analysis_6/` |

Analysis 5 reads Analysis 1's state tables, and Analysis 6 reads the outputs of
Analyses 2–5, so run them in order (or use `run_all.py`).
