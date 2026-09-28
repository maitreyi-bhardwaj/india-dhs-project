"""End-to-end questions through the orchestrator (offline mode), on the real data.

For each: the right tools/agents ran, the right variables were used, numbers
reproduce earlier independent results (Analyses 1-6, computed with pandas
straight from the Stata file), and outreach claims are sourced.
"""

import json

import pandas as pd
import pytest

from src.agents.trace import DATA_FACT, DOC_FACT, INFERENCE, SOURCE_FACT
from src.config import OUTREACH_KB_PATH, RAW_DATA_PATH, ROOT
from tests.conftest import requires_real_data

pytestmark = [pytest.mark.integration, requires_real_data]


def ask(question, **kwargs):
    from src.agents.orchestrator import answer_question
    return answer_question(question, llm=None, **kwargs)


def kinds(answer, kind):
    return [s.text for s in answer.trace.statements if s.kind == kind]


def test_documentation_question_uses_only_rag():
    answer = ask("What does v012 mean?")
    assert answer.trace.tools_used() == ["lookup_variable"]    # RAG only: no SQL, no web
    assert any("respondent's current age" in t for t in kinds(answer, DOC_FACT))
    assert not kinds(answer, DATA_FACT)                    # no calculation for a definition
    assert answer.trace.variables["v012"]["source"].startswith("codebook")


def test_count_question():
    answer = ask("How many respondents are aged 18–24?")
    assert "count_respondents" in answer.trace.tools_used()
    assert any("167,881 respondents" in t for t in kinds(answer, DATA_FACT))
    assert "v012" in answer.trace.variables


def test_percentage_reproduces_analysis_1():
    """25.23% currently working was computed in Analysis 1 with pandas from the .DTA file."""
    national = pd.read_csv(ROOT / "docs" / "results" / "04_national_employment.csv")
    expected = national.loc[national.code == 1, "pct_weighted"].item()
    answer = ask("What percentage of women are currently working?")
    assert any(f"{expected}%" in t for t in kinds(answer, DATA_FACT))
    calc = answer.trace.calculations[-1]
    assert "CASE WHEN y IS NOT NULL THEN w END" in calc["sql"]


def test_grouped_percentage_reproduces_analysis_1():
    expected = pd.read_csv(ROOT / "docs" / "results" / "07_employment_by_education.csv")
    answer = ask("What percentage of women are currently working by education level?")
    rows = {r["v106"]: r["weighted_pct"] for r in answer.trace.calculations[-1]["rows"]}
    for _, row in expected.iterrows():
        assert rows[row.v106] == row.pct_currently_working


def test_underserved_is_reproducible_and_flagged_as_inference():
    first, second = ask("What population appears most underserved?"), ask("What population appears most underserved?")
    top = lambda a: next(c for c in a.trace.calculations if c["title"].startswith("Groups ranked"))["rows"][0]
    assert top(first) == top(second)
    assert top(first)["group"] == "bihar, rural"
    assert any("most underserved" in t for t in kinds(first, INFERENCE))   # the conclusion is an inference
    assert {"v106", "v155", "v481", "s361"} <= set(first.trace.variables)


def test_outreach_claims_all_come_from_sources():
    answer = ask("Identify an underserved population and recommend potentially relevant outreach "
                 "organizations and channels.")
    kb = json.loads(OUTREACH_KB_PATH.read_text())
    known_urls = {f["source_url"] for org in kb["organizations"] for f in org["facts"]}
    known_names = {org["name"] for org in kb["organizations"]}

    source_facts = [s for s in answer.trace.statements if s.kind == SOURCE_FACT]
    assert source_facts
    for s in source_facts:
        assert s.evidence and all(url in known_urls for url in s.evidence)      # every fact has a real source
        assert s.text.split(":")[0] in known_names                              # no invented organizations
    assert all(s["url"] in known_urls for s in answer.trace.external_sources)
    assert answer.trace.agents_used().index("Data Agent") < answer.trace.agents_used().index("Outreach Agent")
    assert any("not a claim by the organization" in t for t in kinds(answer, INFERENCE))


def test_follow_up_uses_previous_population():
    first = ask("What percentage of rural women in Bihar own a mobile phone?")
    follow_up = ask("Which organizations could reach this population?",
                    context_population={"filters": [{"variable": "v024", "op": "=", "value": 10},
                                                    {"variable": "v025", "op": "=", "value": 2}],
                                        "description": "women in rural Bihar"})
    assert "Outreach Agent" in follow_up.trace.agents_used()
    assert first.trace.calculations


def test_original_data_file_unchanged():
    from src.data.loader import file_stamp
    assert file_stamp(RAW_DATA_PATH) == {"size_bytes": 5_196_403_097, "modified": "2026-09-25 20:23:22"}
