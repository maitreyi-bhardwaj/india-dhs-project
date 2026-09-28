# Data dictionary: analysis database

The variables in `data/processed/nfhs5_women.sqlite`, built by `src/data/pipeline.py` from the India DHS 2019-21 (NFHS-5) Individual Recode. Descriptions and value labels come from the Stata file's own metadata (`docs/dhs_codebook.csv`). One row = one woman aged 15-49.

**Missing values:** Stata missing values become NULL. Codes that are not real answers (for example 'don't know' or 'not a de jure resident') and values outside the valid range also become NULL. Every change is counted in the `cleaning_log` table.

**Weights:** `w = v005 / 1,000,000` is the weight used for every percentage.

## Variables

### caseid: case identification

- Topic: identifier; Stata type: `str15`; kind: id
- Valid values: (identifier / design value)
- Special codes set to missing: none
- Universe (who has a value): all women; valid 724,115, missing 0 (0.0%)
- Note: Unique respondent ID (text).

### v001: cluster number

- Topic: survey design; Stata type: `long`; kind: design
- Valid values: (identifier / design value)
- Special codes set to missing: none
- Universe (who has a value): all women; valid 724,115, missing 0 (0.0%)
- Note: Cluster number.

### v021: primary sampling unit

- Topic: survey design; Stata type: `long`; kind: design
- Valid values: (identifier / design value)
- Special codes set to missing: none
- Universe (who has a value): all women; valid 724,115, missing 0 (0.0%)
- Note: Primary sampling unit (needed for standard errors).

### v022: sample strata for sampling errors

- Topic: survey design; Stata type: `long`; kind: design
- Valid values: (identifier / design value)
- Special codes set to missing: none
- Universe (who has a value): all women; valid 724,115, missing 0 (0.0%)
- Note: Sample strata for sampling errors.

### v005: women's individual sample weight (6 decimals)

- Topic: survey design; Stata type: `long`; kind: weight
- Valid values: (identifier / design value)
- Special codes set to missing: none
- Universe (who has a value): all women; valid 724,115, missing 0 (0.0%)
- Note: National women's weight, 6 implied decimals.

### sweight: sample weight (6 decimals) (state level)

- Topic: survey design; Stata type: `long`; kind: weight
- Valid values: (identifier / design value)
- Special codes set to missing: none
- Universe (who has a value): all women; valid 724,115, missing 0 (0.0%)
- Note: State-level weight, 6 implied decimals.

### ssmod: household selected for the state module

- Topic: survey design; Stata type: `byte`; kind: categorical
- Valid values: 0=no; 1=yes
- Special codes set to missing: none
- Universe (who has a value): all women; valid 724,115, missing 0 (0.0%)
- Note: 1 = household selected for the state module. Employment, phone, bank and internet questions exist only for these women (verified: v714 is missing exactly when ssmod = 0).

### v024: state

- Topic: geography; Stata type: `byte`; kind: categorical
- Valid values: 36 labelled codes (see codebook)
- Special codes set to missing: none
- Universe (who has a value): all women; valid 724,115, missing 0 (0.0%)

### sdist: district

- Topic: geography; Stata type: `int`; kind: categorical
- Valid values: 707 labelled codes (see codebook)
- Special codes set to missing: none
- Universe (who has a value): all women; valid 724,115, missing 0 (0.0%)
- Note: 707 districts; many have small samples.

### v025: type of place of residence

- Topic: geography; Stata type: `byte`; kind: categorical
- Valid values: 1=urban; 2=rural
- Special codes set to missing: none
- Universe (who has a value): all women; valid 724,115, missing 0 (0.0%)

### v012: respondent's current age

- Topic: demographics; Stata type: `byte`; kind: numeric
- Valid values: 15-49
- Special codes set to missing: none
- Universe (who has a value): all women; valid 724,115, missing 0 (0.0%)
- Note: Survey interviewed women aged 15-49.

### v013: age in 5-year groups

- Topic: demographics; Stata type: `byte`; kind: categorical
- Valid values: 1=15-19; 2=20-24; 3=25-29; 4=30-34; 5=35-39; 6=40-44; 7=45-49
- Special codes set to missing: none
- Universe (who has a value): all women; valid 724,115, missing 0 (0.0%)

### v130: religion

- Topic: demographics; Stata type: `byte`; kind: categorical
- Valid values: 1=hindu; 2=muslim; 3=christian; 4=sikh; 5=buddhist / neo-buddhist; 6=jain; 7=jewish; 8=parsi / zoroastrian; 9=no religion; 96=other
- Special codes set to missing: none
- Universe (who has a value): all women; valid 724,115, missing 0 (0.0%)
- Note: 96 = 'other' is a real answer and is kept.

### s116: belong to a scheduled caste, a scheduled tribe, other backward class

- Topic: demographics; Stata type: `byte`; kind: categorical
- Valid values: 1=schedule caste; 2=schedule tribe; 3=obc; 4=none of them
- Special codes set to missing: 8=don't know
- Universe (who has a value): 685,424 women with a valid value; valid 685,424, missing 38,691 (5.34%)

### v501: current marital status

- Topic: demographics; Stata type: `byte`; kind: categorical
- Valid values: 0=never in union  [includes: married gauna not performed]; 1=married; 2=living with partner; 3=widowed; 4=divorced; 5=no longer living together/separated
- Special codes set to missing: none
- Universe (who has a value): all women; valid 724,115, missing 0 (0.0%)

### v201: total children ever born

- Topic: demographics; Stata type: `byte`; kind: numeric
- Valid values: 0-20
- Special codes set to missing: none
- Universe (who has a value): all women; valid 724,115, missing 0 (0.0%)

### v106: highest educational level

- Topic: education; Stata type: `byte`; kind: categorical
- Valid values: 0=no education; 1=primary; 2=secondary; 3=higher
- Special codes set to missing: none
- Universe (who has a value): all women; valid 724,115, missing 0 (0.0%)

### v133: education in single years

- Topic: education; Stata type: `byte`; kind: numeric
- Valid values: 0-30
- Special codes set to missing: 97=inconsistent
- Universe (who has a value): all women; valid 724,115, missing 0 (0.0%)

### v149: educational attainment

- Topic: education; Stata type: `byte`; kind: categorical
- Valid values: 0=no education; 1=incomplete primary; 2=complete primary; 3=incomplete secondary; 4=complete secondary; 5=higher
- Special codes set to missing: none
- Universe (who has a value): all women; valid 724,115, missing 0 (0.0%)

### v155: literacy

- Topic: education; Stata type: `byte`; kind: categorical
- Valid values: 0=cannot read at all; 1=able to read only parts of sentence; 2=able to read whole sentence
- Special codes set to missing: 3=no card with required language; 4=blind/visually impaired
- Universe (who has a value): 719,947 women with a valid value; valid 719,947, missing 4,168 (0.58%)
- Note: Codes 3 and 4 mean reading ability could not be assessed, so they become missing.

### v190: wealth index combined

- Topic: wealth; Stata type: `byte`; kind: categorical
- Valid values: 1=poorest; 2=poorer; 3=middle; 4=richer; 5=richest
- Special codes set to missing: none
- Universe (who has a value): all women; valid 724,115, missing 0 (0.0%)
- Note: National wealth quintile.

### s190s: wealth index within state

- Topic: wealth; Stata type: `byte`; kind: categorical
- Valid values: 1=poorest; 2=poorer; 3=middle; 4=richer; 5=richest
- Special codes set to missing: none
- Universe (who has a value): all women; valid 724,115, missing 0 (0.0%)
- Note: Wealth quintile within the woman's state.

### v714: respondent currently working

- Topic: employment; Stata type: `byte`; kind: categorical
- Valid values: 0=no; 1=yes
- Special codes set to missing: none
- Universe (who has a value): state-module women only (ssmod = 1); valid 108,785, missing 615,330 (84.98%)

### v731: respondent worked in last 12 months

- Topic: employment; Stata type: `byte`; kind: categorical
- Valid values: 0=no; 1=in the past year; 2=currently working; 3=have a job, but on leave last 7 days
- Special codes set to missing: none
- Universe (who has a value): state-module women only (ssmod = 1); valid 108,785, missing 615,330 (84.98%)

### v717: respondent's occupation (grouped)

- Topic: employment; Stata type: `byte`; kind: categorical
- Valid values: 0=not working; 1=professional / technical / managerial; 3=clerical; 4=sales; 5=services / household and domestic; 6=agricultural; 7=skilled and unskilled manual; 9=other
- Special codes set to missing: 98=don't know
- Universe (who has a value): 108,654 women with a valid value; valid 108,654, missing 615,461 (84.99%)

### v741: type of earnings from respondent's work

- Topic: employment; Stata type: `byte`; kind: categorical
- Valid values: 0=not paid; 1=cash only; 2=cash and in-kind; 3=in-kind only
- Special codes set to missing: none
- Universe (who has a value): 34,976 women with a valid value; valid 34,976, missing 689,139 (95.17%)
- Note: Asked only of women who work.

### v157: frequency of reading newspaper or magazine

- Topic: media and access; Stata type: `byte`; kind: categorical
- Valid values: 0=not at all; 1=less than once a week; 2=at least once a week; 3=almost every day
- Special codes set to missing: none
- Universe (who has a value): all women; valid 724,115, missing 0 (0.0%)

### v158: frequency of listening to radio

- Topic: media and access; Stata type: `byte`; kind: categorical
- Valid values: 0=not at all; 1=less than once a week; 2=at least once a week; 3=almost every day
- Special codes set to missing: none
- Universe (who has a value): all women; valid 724,115, missing 0 (0.0%)

### v159: frequency of watching television

- Topic: media and access; Stata type: `byte`; kind: categorical
- Valid values: 0=not at all; 1=less than once a week; 2=at least once a week; 3=almost every day
- Special codes set to missing: none
- Universe (who has a value): all women; valid 724,115, missing 0 (0.0%)

### v169a: owns a mobile telephone

- Topic: media and access; Stata type: `byte`; kind: categorical
- Valid values: 0=no; 1=yes
- Special codes set to missing: none
- Universe (who has a value): state-module women only (ssmod = 1); valid 108,785, missing 615,330 (84.98%)

### v170: has an account in a bank or other financial institution

- Topic: media and access; Stata type: `byte`; kind: categorical
- Valid values: 0=no; 1=yes
- Special codes set to missing: none
- Universe (who has a value): state-module women only (ssmod = 1); valid 108,785, missing 615,330 (84.98%)

### v171a: use of internet

- Topic: media and access; Stata type: `byte`; kind: categorical
- Valid values: 0=never; 1=yes, last 12 months; 2=yes, before last 12 months; 3=yes, can't establish when
- Special codes set to missing: none
- Universe (who has a value): state-module women only (ssmod = 1); valid 108,785, missing 615,330 (84.98%)

### v481: covered by health insurance

- Topic: health; Stata type: `byte`; kind: categorical
- Valid values: 0=no; 1=yes
- Special codes set to missing: none
- Universe (who has a value): all women; valid 724,115, missing 0 (0.0%)

### s361: met with an anganwadi worker, asha or other community health worker in last 3 mo

- Topic: health; Stata type: `byte`; kind: categorical
- Valid values: 0=no; 1=yes
- Special codes set to missing: none
- Universe (who has a value): 724,105 women with a valid value; valid 724,105, missing 10 (0.0%)

### v457: anemia level

- Topic: health; Stata type: `byte`; kind: categorical
- Valid values: 1=severe; 2=moderate; 3=mild; 4=not anemic
- Special codes set to missing: none
- Universe (who has a value): 690,153 women with a valid value; valid 690,153, missing 33,962 (4.69%)
- Note: Only for women whose hemoglobin was measured.

### v119: household has: electricity

- Topic: household; Stata type: `byte`; kind: categorical
- Valid values: 0=no; 1=yes
- Special codes set to missing: 7=not a dejure resident
- Universe (who has a value): 705,803 women with a valid value; valid 705,803, missing 18,312 (2.53%)

## Derived indicators (project definitions, not official DHS indicators)

### no_education: Has no education

- Rule: v106 = 0 (no education)
- Source variables: v106
- Universe: all women (724,115 women with a value)
- Type: deprivation (higher = more underserved)

### cannot_read: Cannot read at all

- Rule: v155 = 0 (cannot read at all); missing if v155 is 3 or 4
- Source variables: v155
- Universe: all women assessed (719,947 women with a value)
- Type: deprivation (higher = more underserved)

### no_media_exposure: No exposure to newspaper, radio or TV

- Rule: v157 = 0 AND v158 = 0 AND v159 = 0 (each 'not at all')
- Source variables: v157, v158, v159
- Universe: all women (724,115 women with a value)
- Type: deprivation (higher = more underserved)

### no_health_insurance: Not covered by health insurance

- Rule: v481 = 0
- Source variables: v481
- Universe: all women (724,115 women with a value)
- Type: deprivation (higher = more underserved)

### no_frontline_worker_contact: Did not meet an Anganwadi worker, ASHA or other community health worker (last 3 months)

- Rule: s361 = 0
- Source variables: s361
- Universe: all women (724,105 women with a value)
- Type: deprivation (higher = more underserved)

### any_anemia: Has any anemia (severe, moderate or mild)

- Rule: v457 in (1, 2, 3)
- Source variables: v457
- Universe: women with a hemoglobin measurement (690,153 women with a value)
- Type: deprivation (higher = more underserved)

### no_mobile_phone: Does not own a mobile phone

- Rule: v169a = 0
- Source variables: v169a
- Universe: state-module women only (ssmod = 1) (108,785 women with a value)
- Type: deprivation (higher = more underserved)

### no_bank_account: Has no bank or financial institution account

- Rule: v170 = 0
- Source variables: v170
- Universe: state-module women only (ssmod = 1) (108,785 women with a value)
- Type: deprivation (higher = more underserved)

### never_used_internet: Has never used the internet

- Rule: v171a = 0
- Source variables: v171a
- Universe: state-module women only (ssmod = 1) (108,785 women with a value)
- Type: deprivation (higher = more underserved)

### not_working: Not currently working

- Rule: v714 = 0
- Source variables: v714
- Universe: state-module women only (ssmod = 1) (108,785 women with a value)
- Type: deprivation (higher = more underserved)

### reads_newspaper: Reads a newspaper or magazine at all

- Rule: v157 >= 1
- Source variables: v157
- Universe: all women (724,115 women with a value)
- Type: reach (channel reach)

### listens_radio: Listens to the radio at all

- Rule: v158 >= 1
- Source variables: v158
- Universe: all women (724,115 women with a value)
- Type: reach (channel reach)

### watches_tv: Watches television at all

- Rule: v159 >= 1
- Source variables: v159
- Universe: all women (724,115 women with a value)
- Type: reach (channel reach)

### owns_mobile_phone: Owns a mobile phone

- Rule: v169a = 1
- Source variables: v169a
- Universe: state-module women only (ssmod = 1) (108,785 women with a value)
- Type: reach (channel reach)

### ever_used_internet: Has ever used the internet

- Rule: v171a in (1, 2, 3)
- Source variables: v171a
- Universe: state-module women only (ssmod = 1) (108,785 women with a value)
- Type: reach (channel reach)

### met_frontline_worker: Met an Anganwadi worker, ASHA or other community health worker (last 3 months)

- Rule: s361 = 1
- Source variables: s361
- Universe: all women (724,105 women with a value)
- Type: reach (channel reach)

### has_bank_account: Has a bank or financial institution account

- Rule: v170 = 1
- Source variables: v170
- Universe: state-module women only (ssmod = 1) (108,785 women with a value)
- Type: reach (channel reach)

### currently_working: Currently working

- Rule: v714 = 1
- Source variables: v714
- Universe: state-module women only (ssmod = 1) (108,785 women with a value)
- Type: reach (channel reach)

## Verified relationships between variables

Each statement below was checked on all rows by the pipeline (table `validation_checks`).

- PASS: row count. 724,115 rows (expected 724,115)
- PASS: caseid is unique. 724,115 unique IDs
- PASS: weights are positive. v005 min 3462, sweight min 2724
- PASS: v013 is the 5-year group of v012. 0 mismatches
- PASS: v149 is a finer version of v106. 0 mismatches (v149 0->0, 1-2->1, 3-4->2, 5->3)
- PASS: v133 = 0 years when v106 = no education. 0 exceptions
- PASS: v714 is present exactly for state-module women (ssmod = 1). 0 rows differ; answered: 108,785
- PASS: v169a is present exactly for state-module women (ssmod = 1). 0 rows differ; answered: 108,785
- PASS: v170 is present exactly for state-module women (ssmod = 1). 0 rows differ; answered: 108,785
- PASS: v171a is present exactly for state-module women (ssmod = 1). 0 rows differ; answered: 108,785
- PASS: v731 is present exactly for state-module women (ssmod = 1). 0 rows differ; answered: 108,785
- PASS: sweight = v005 x a constant within each state. largest relative spread of sweight/v005 within a state: 2.39e-04. So state-level percentages are the same with either weight.
- PASS: v021 (PSU) equals v001 (cluster). 0 rows differ
