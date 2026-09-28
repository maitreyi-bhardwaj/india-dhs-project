"""Cleaning rules and derived indicators, on a synthetic data frame."""

import numpy as np
import pandas as pd

from src.data import pipeline
from src.data.variables import DERIVED, VARIABLES, VARIABLES_BY_NAME


def fake_codebook():
    rows = []
    for spec in VARIABLES:
        labels = {"s116": '{"1": "sc", "2": "st", "3": "obc", "4": "none", "8": "don\'t know"}',
                  "v155": '{"0": "cannot read", "1": "part", "2": "whole", "3": "no card", "4": "blind"}',
                  "v119": '{"0": "no", "1": "yes", "7": "not a dejure resident"}',
                  "v157": '{"0": "not at all", "1": "less", "2": "weekly"}'}.get(spec.name, "")
        rows.append({"variable_name": spec.name, "variable_label": spec.name, "stata_type": "byte",
                     "value_label_name": "", "value_labels": labels})
    return pd.DataFrame(rows).set_index("variable_name")


def raw_frame(**overrides):
    base = {spec.name: [1, 1, 1] for spec in VARIABLES}
    base.update({"caseid": ["a", "b", "c"], "v012": [20, 30, 40], "v133": [5, 97, 10],
                 "v005": [1_000_000, 2_000_000, 500_000]})
    base.update(overrides)
    return pd.DataFrame(base).astype({"caseid": str})


def test_special_codes_become_missing():
    raw = raw_frame(s116=[1, 8, 3], v155=[0, 3, 4], v119=[7, 1, 0])
    cleaned, log = pipeline.clean(raw, fake_codebook())
    assert cleaned.s116.tolist()[1] != cleaned.s116.tolist()[1]          # NaN (don't know)
    assert cleaned.v155.isna().tolist() == [False, True, True]             # 3, 4 not assessed
    assert cleaned.v119.isna().tolist() == [True, False, False]            # 7 not de jure
    assert cleaned.v133.isna().tolist() == [False, True, False]            # 97 inconsistent
    reasons = {(r["variable"], r["code"]): r["reason"] for r in log if r["code"] is not None}
    assert reasons[("s116", 8)] == "don't know"
    assert reasons[("v133", 97)] == "inconsistent"


def test_out_of_range_age_becomes_missing():
    cleaned, _ = pipeline.clean(raw_frame(v012=[14, 15, 49]), fake_codebook())
    assert cleaned.v012.isna().tolist() == [True, False, False]


def test_derived_indicators_follow_their_rules():
    df = pd.DataFrame({
        "v106": [0, 2, np.nan], "v155": [0, 2, np.nan],
        "v157": [0, 1, 0], "v158": [0, 0, np.nan], "v159": [0, 0, 0],
        "v481": [0, 1, 0], "s361": [0, 1, 1], "v457": [1, 4, np.nan],
        "v169a": [0, 1, np.nan], "v170": [0, 1, np.nan], "v171a": [0, 3, np.nan], "v714": [0, 1, np.nan],
        "v005": [1_000_000, 2_000_000, 500_000],
    })
    out = pipeline.add_derived(df)
    assert out.no_education.tolist()[:2] == [1, 0] and pd.isna(out.no_education[2])
    assert out.no_media_exposure.tolist()[:2] == [1, 0]
    assert pd.isna(out.no_media_exposure[2])          # radio missing -> can't tell
    assert out.any_anemia.tolist()[:2] == [1, 0]
    assert out.ever_used_internet.tolist()[:2] == [0, 1]
    assert out.w.tolist() == [1.0, 2.0, 0.5]


def test_every_derived_indicator_has_a_formula():
    df = pd.DataFrame({name: [0] for name in ["v106", "v155", "v157", "v158", "v159", "v481", "s361", "v457",
                                              "v169a", "v170", "v171a", "v714", "v005"]})
    out = pipeline.add_derived(df)
    assert {d.name for d in DERIVED} <= set(out.columns)


def test_cleaning_rules_agree_with_analysis_scripts():
    """scripts/dhs_utils.py (Analyses 1-6) and src/data/variables.py must use the same rules."""
    import importlib.util
    from src.config import ROOT
    spec = importlib.util.spec_from_file_location("dhs_utils", ROOT / "scripts" / "dhs_utils.py")
    dhs_utils = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dhs_utils)
    assert dhs_utils.VALID_RANGES["v012"] == VARIABLES_BY_NAME["v012"].valid_range
    assert dhs_utils.VALID_RANGES["v133"] == VARIABLES_BY_NAME["v133"].valid_range
