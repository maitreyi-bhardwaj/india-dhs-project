"""Offline routing: does each test question go to the right place?"""

import pytest

from tests.conftest import requires_real_data

pytestmark = [pytest.mark.integration, requires_real_data]  # the router reads state/district labels


def plan(question):
    from src.agents.router import plan_question
    from src.rag.retriever import get_retriever
    return plan_question(question, get_retriever("docs").variables_in(question))


@pytest.mark.parametrize("question, intent, outreach", [
    ("What does v012 mean?", "documentation", False),
    ("What categories does s116 contain?", "documentation", False),
    ("What variables are relevant to women's employment?", "documentation", False),
    ("How many respondents are aged 18–24?", "count", False),
    ("What percentage of rural women do not have health insurance?", "percentage", False),
    ("What population appears most underserved according to this dataset?", "underserved", False),
    ("Which population should an NGO prioritize?", "underserved", False),
    ("Which NGOs or outreach channels could potentially reach this population?", "underserved", True),
    ("Identify an underserved population and recommend potentially relevant outreach organizations and channels.",
     "underserved", True),
])
def test_intent_and_agents(question, intent, outreach):
    p = plan(question)
    assert p.intent == intent, p.reasons
    assert p.needs_outreach is outreach


def test_entities_are_extracted():
    p = plan("What percentage of women aged 18-24 in Bihar own a mobile phone?")
    assert p.outcome == {"indicator": "owns_mobile_phone"}
    assert {"variable": "v012", "op": "between", "value": [18, 24]} in p.filters
    assert {"variable": "v024", "op": "in", "value": [10]} in p.filters


def test_negation_selects_deprivation_indicator():
    assert plan("What share of rural women do not have a bank account?").outcome == {"indicator": "no_bank_account"}


def test_grouping_words():
    assert plan("What percentage of women are currently working, by state?").group_by == ["v024"]
    assert plan("Compare urban and rural women on internet use").group_by == ["v025"]
