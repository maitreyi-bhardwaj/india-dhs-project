# Final summary — women's education and employment in NFHS-5

A plain-language summary of six descriptive analyses. This is a learning
project, not a scientific paper: no statistical tests, no confidence intervals,
no causal claims. Every number below comes from a CSV in `docs/results/`,
produced by the scripts in `scripts/` (run them all with
`python3 scripts/run_all.py`).

## 1. Research questions

1. How does women's educational attainment vary across Indian states, and how
   is it associated with current employment?
2. Does the relationship between education and current employment change after
   accounting for age?
3. Does that relationship differ between urban and rural India?
4. How does household wealth relate to women's education and employment?
5. Which states stand out on higher education, on employment, and on the
   education–employment pattern?
6. How robust are these results (missing data, codes, sample sizes, weighting,
   small groups), and was the data file left unchanged?

## 2. Dataset

- India Standard DHS 2019–21 (NFHS-5) Individual Recode, `data/IAIR7EFL.DTA`.
- 724,115 women aged 15–49, 5,972 variables.
- Cross-sectional: each woman was interviewed once.
- The file was only ever read. Its size (5,196,403,097 bytes), modification
  time (2026-09-25 20:23:22) and SHA-256 checksum were identical before and
  after all analyses ran (`analysis_6/08_data_file_integrity.csv`).

## 3. Variables

Labels are taken from the file's own metadata (`docs/dhs_codebook.csv`).

| Variable | Codebook label | Used in |
|---|---|---|
| v024 | state | 1, 5, 6 |
| v025 | type of place of residence | 1, 3, 6 |
| v106 | highest educational level | 1–6 |
| v133 | education in single years | 1, 6 |
| v714 | respondent currently working | 1–6 |
| v190 | wealth index combined | 1, 4, 6 |
| v005 | women's individual sample weight (6 decimals) | 1–6 |
| v012 | respondent's current age | 2–6 |
| v013 | age in 5-year groups | 2, 6 (consistency check only) |

## 4. Sampling weights

- Every percentage is weighted by `w = v005 / 1,000,000`, so each woman counts
  in proportion to how many women she represents.
- Weighting matters for some estimates:
  - Nationally, weighted and unweighted results are within 1.6 points of each
    other for education and employment.
  - 18 of the 95 estimates compared in Analysis 6 differ by 2 points or more.
    Most of these are state-level figures, for example Puducherry's employment
    rate: 22.2% unweighted vs 33.0% weighted.
- The same `v005` weight is used for state-level estimates. The
  state-specific weight (`sweight`) was later checked (2026-09-27, data
  pipeline validation): within every state, `sweight` / `v005` is constant up to
  rounding, so state percentages are the same with either weight.

## 5. Cleaning decisions

- Stata missing values → missing.
- Only codes the codebook defines as real answers are kept. Anything else,
  such as DHS codes 97 = inconsistent or 98 = don't know, → missing.
- Age (`v012`) is valid if it's between 15 and 49.
- Missing values are excluded per calculation, not per woman.
- **What actually happened in this data:**
  - None of the 9 variables contains any invalid or special code.
  - `v012` agrees with `v013` for all 724,115 women.
  - The only missing data is `v714`: 615,330 women (85%) have no answer.
- Small samples follow DHS convention:
  - under 25 cases → suppressed;
  - 25–49 cases → flagged as unreliable;
  - age-standardized rates → flagged when any of their age cells is small.
- Age standardization always uses the same standard population: the weighted
  age distribution of the 108,785 women who answered `v714`.

## 6. Main descriptive findings

### Education (all 724,115 women)

- **National mix:** 22.4% have no education, 11.7% primary, 50.2% secondary and
  15.7% higher education. The weighted mean is 7.6 years of schooling.
- **By state:**
  - Higher education ranges from 7.0% (Tripura) to 36.8% (Puducherry).
  - No education ranges from 0.7% (Kerala) to 38.3% (Bihar).
- **By residence:** 26.4% of urban women have higher education, compared with
  10.5% of rural women.
- **By wealth:** 39.3% of women in the richest quintile have higher education,
  compared with 2.2% in the poorest. 44.8% of the poorest quintile have no
  education, compared with 5.7% of the richest.
- **By age:** among women who answered `v714`, 48.5% of those aged 45–49 have no
  education, compared with 4.4% of those aged 15–19.

### Employment (the 108,785 women who answered `v714`)

- **Nationally:** 25.2% are currently working.
- **By age:** employment rises from 11.1% at ages 15–19 to 35.6% at 40–44.
- **By residence:** 23.7% urban and 26.0% rural; after age standardization,
  23.1% and 26.3%.
- **By wealth:** employment is lower in richer quintiles. Age-standardized, it
  falls from 28.3% (poorest) to 19.2% (richest).
- **By state:** age-standardized employment ranges from 43.2% (Meghalaya) to
  15.6% (Bihar), or 8.8% in Lakshadweep, which has only 173 respondents.
  Standardizing moves most states' ranks by only a few places.

### Education and employment together

| Education | Crude % working | Age-standardized % working |
|---|---:|---:|
| No education | 33.8 | 28.5 |
| Primary | 30.7 | 28.2 |
| Secondary | 20.7 | 22.9 |
| Higher | 23.5 | 25.2 |

## 7. Important patterns

1. **Age accounts for part of the crude education gap.** Before standardizing,
   women with no education are 13.1 points more likely to be working than
   secondary-educated women. After age standardization, the gap is 5.6 points.
   Women with no education are older on average, and older women are more
   often working.
2. **The pattern isn't the same in every group.** The age-standardized gap
   between secondary and no education is:

   | Group | Gap (secondary − no education) |
   |---|---:|
   | urban | −8.6 |
   | rural | −3.8 |
   | poorest quintile | −1.6 |
   | poorer quintile | −1.8 |
   | middle quintile | −3.1 |
   | richer quintile | −6.5 |
   | richest quintile | +1.7 |

   In the three poorest quintiles, age-standardized employment is similar
   across education levels (roughly 26–31%).
3. **Higher vs secondary education varies by group.** After age
   standardization, higher-educated women are more likely to be working than
   secondary-educated women among urban women (+6.4 points) and in the richest
   quintile (+9.4). Among rural women there is no difference (−0.1).
4. **States with more higher-educated women aren't clearly the states with
   more employment.** The rank correlation across states is weak: 0.09–0.26,
   depending on the measure and whether small states are included.
5. **A few states differ from the national education gap.** By the Analysis 5
   heuristic (gap at least 10 points from national):
   - 5 of the 16 states that could be assessed differ: Arunachal Pradesh
     (secondary relatively more likely to work) and Odisha, Madhya Pradesh,
     Karnataka and Telangana (relatively less likely).
   - With a stricter minimum cell size, 3 remain: Arunachal Pradesh, Odisha
     and Madhya Pradesh.
   - 20 states/UTs could not be assessed because some of their age groups have
     too few women.

These are descriptions of the data. This project does not test *why* any of
these patterns exist.

## 8. Limitations

- **Employment is known for only 15% of women.** `v714` is missing for 85%.
  - Verified later (2026-09-27): `v714` is present for exactly the 108,785
    women with `ssmod = 1` ("household selected for the state module") and
    missing for all others, so the missingness is by survey design.
  - The share answering is about 15% in every age group, residence type and
    wealth quintile (Analysis 6, table 03).
  - `v005` is assumed to be the right weight for this subsample. That still
    needs checking against NFHS-5 documentation or the DHS Indicators code.
- **No confidence intervals.** The survey design (`v021` primary sampling unit,
  `v022` strata) wasn't used, so we can't say which differences are
  statistically meaningful. Differences of a few points, especially for
  states or small cells, may be noise.
- **Thresholds are judgement calls:**
  - "small state" = under 500 respondents;
  - "differs substantially" = at least 10 points;
  - "material" weighted/unweighted difference = at least 2 points;
  - minimum age cell = 10 women.
  They are documented in the scripts; other reasonable choices could change
  which states are highlighted (Analysis 6, table 07).
- **Only one adjustment at a time.** Age is standardized, but age, wealth,
  residence and state are never adjusted for together.
- **`v714` is a single yes/no item** ("currently working"). The project doesn't
  look at type of work, pay, or work in the past 12 months.
- **`v190` is used only as a ranking** (poorest … richest). How the index is
  built isn't documented in the data file and wasn't reviewed.

## 9. What cannot be concluded

- That education **causes** higher or lower employment, or that increasing
  education would change employment rates. The data are observational and
  cross-sectional.
- That wealth, rural residence or state **causes** any of the differences shown.
- That any individual woman's employment would change as she ages. Differences
  between age groups mix the effects of age with differences between
  generations.
- **Why** women with no education, or women in poorer households, are more often
  currently working. Nothing in these analyses measures reasons.
- That the state-level patterns in Analysis 5 are statistically different from
  the national pattern.
- Anything about the 85% of women not asked `v714`, beyond the assumption that
  the subsample represents them.

## 10. Potential next research questions

All of the variables below appear in `docs/dhs_codebook.csv`. None has been
analysed yet.

1. **Add confidence intervals** using `v021` (primary sampling unit) and `v022`
   (sample strata), to see which differences are larger than sampling noise.
2. **Check the subsample weight:** `ssmod` now confirms which women are in the
   employment subsample, and `sweight` is proportional to `v005` within states.
   Still open: whether NFHS-5 recommends a different weight for state-module
   questions.
3. **Look at other employment measures:** `v731` (worked in last 12 months),
   `v717` (occupation grouped), `v741` (type of earnings), `v732` (all
   year/seasonal).
4. **Add marital status and children:** `v501` (current marital status) and
   `v201` (total children ever born).
5. **Adjust for several factors at once** (age, wealth, residence, state), for
   example with a weighted regression, still interpreted as association rather
   than cause.
6. **Use within-state wealth quintiles** (`s190s`) instead of the national
   quintiles when comparing states.
7. **Check results against the official DHS Indicators code**, as planned at
   the start of the project.
