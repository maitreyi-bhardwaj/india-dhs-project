# Methodology notes

How this project computes numbers from the NFHS-5 (India DHS 2019-21) Individual
Recode. Every statement here was checked in the data by this project's
pipeline or analysis scripts; nothing is copied from external DHS documents.

## The dataset

The file `data/IAIR7EFL.DTA` is the Individual Recode: one row per woman aged
15-49 who was interviewed (724,115 women) and 5,972 variables. Variable
descriptions and value labels come from the Stata file's own metadata,
extracted to `docs/dhs_codebook.csv`.

## Sampling weights

NFHS does not select women with equal probability, so every percentage must be
weighted. The women's weight is `v005`, stored as an integer with six implied
decimals: the weight used is `w = v005 / 1,000,000`.

A weighted percentage is: sum of `w` for women with the characteristic, divided
by the sum of `w` for women with a valid answer, times 100.

The denominator must only include women with a valid (non-missing) answer.
In SQL, `SUM(w * x)` silently skips missing `x`, but `SUM(w)` does not, so the
denominator is written `SUM(CASE WHEN x IS NOT NULL THEN w END)`. Getting this
wrong gives badly wrong results: for current employment it gives 3.76% instead
of the correct 25.23%.

There is also a state-level weight, `sweight`. Within each state, `sweight`
divided by `v005` is constant up to rounding (largest relative spread 0.024%),
so percentages within a state are the same with either weight.

## The state module subsample

Some questions were asked only of women in households selected for the "state
module" (`ssmod = 1`): current employment (`v714`), work in the last 12 months
(`v731`), mobile phone ownership (`v169a`), bank account (`v170`) and internet
use (`v171a`). These variables are missing for exactly the 615,330 women with
`ssmod = 0`, and present for the 108,785 women with `ssmod = 1` (about 15%).
The share of women in the state module is about 15% in every age group,
residence type and wealth quintile.

## Missing and special codes

- Stata's own missing values become missing (NULL).
- Codes that are not real answers become missing. Examples in this project:
  `s116` code 8 = "don't know"; `v155` codes 3 = "no card with required language"
  and 4 = "blind/visually impaired" (reading ability not assessed); `v717`
  code 98 = "don't know"; `v119` code 7 = "not a dejure resident"; `v133` code
  97 = "inconsistent".
- Numeric variables outside their valid range become missing (for example
  age `v012` must be 15-49).

## Age groups

`v013` is the DHS 5-year age group (15-19 ... 45-49). It agrees with the
5-year group of `v012` (current age) for every woman.

## Age standardization

Older women are both less educated and more likely to be working, so crude
comparisons between groups can reflect differences in age mix. A directly
age-standardized rate re-weights a group's age-specific rates to a standard age
distribution: the weighted age distribution of all women with a valid answer.
Standardized rate = sum over the 7 age groups of (standard share x the group's
rate in that age group).

## Small samples

Following the DHS convention used in this project: a percentage based on fewer
than 25 unweighted women is suppressed, and one based on 25-49 women is
flagged as unreliable. Age-standardized rates are flagged when any of their
age cells is small. Groups with fewer than 200 women are not ranked.

## What "underserved" means in this project

There is no single official definition. This project uses a transparent,
adjustable deprivation score: the average of a group's weighted percentages on
five indicators measured for all women: no education (`v106 = 0`), cannot read
at all (`v155 = 0`), no exposure to newspaper, radio or TV (`v157`, `v158`, `v159`
all 0), no health insurance (`v481 = 0`), and no contact with an Anganwadi
worker, ASHA or other community health worker in the last 3 months
(`s361 = 0`). Higher scores mean more women lack these things. Different
indicators or weights can change the ranking.

## Limitations

- No confidence intervals: survey-design standard errors (using `v021` primary
  sampling units and `v022` strata) are not yet computed, so small differences
  between groups may not be meaningful.
- All results are descriptive associations from cross-sectional data. They do
  not show causes.
- The wealth index `v190` is used only as a ranking into five quintiles; how
  it is constructed is not documented in the data file.
