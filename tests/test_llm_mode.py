"""LLM-mode wiring, tested with a fake Claude client (no API key, no cost).

The fake returns scripted responses shaped like the Messages API, so we can
check that our code: sends the right request settings, executes the tools
the model asks for, records evidence from tool outputs (not model text),
flags numbers the model made up, and drops web facts without a real source.
"""

import json
from types import SimpleNamespace as NS

import pytest

from src.agents.trace import DATA_FACT, Trace
from src.llm import LLM
from tests.conftest import requires_real_data


def text_block(text):
    return NS(type="text", text=text, citations=None)


def tool_use(name, arguments, id_="toolu_1"):
    return NS(type="tool_use", name=name, input=arguments, id=id_)


def message(*blocks, stop="end_turn"):
    return NS(content=list(blocks), stop_reason=stop, model="claude-opus-5",
              usage=NS(input_tokens=10, output_tokens=5))


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        self.beta = NS(messages=NS(create=self.create))

    def create(self, **kwargs):
        self.requests.append(kwargs)
        return self.responses.pop(0)


def test_request_settings():
    client = FakeClient([message(text_block("hi"))])
    LLM(client=client, model="claude-opus-5").create(system="s", messages=[{"role": "user", "content": "q"}])
    request = client.requests[0]
    assert request["thinking"] == {"type": "adaptive"}
    assert request["fallbacks"] == "default" and request["betas"] == ["server-side-fallback-2026-07-01"]


def test_refusal_is_raised():
    from src.llm import LLMRefusal
    client = FakeClient([message(text_block(""), stop="refusal")])
    with pytest.raises(LLMRefusal):
        LLM(client=client).create(system="s", messages=[{"role": "user", "content": "q"}])


def test_number_guard_flags_invented_numbers():
    from src.agents.synthesis import unverified_numbers
    trace = Trace("q")
    trace.say(DATA_FACT, "25.23% of women are currently working (n = 108,785).")
    assert unverified_numbers("About 25.2% work (n = 108,785).", trace, "q") == []
    assert unverified_numbers("About 25.2% work, and 61.8% in Bihar.", trace, "q") == ["61.8"]


def test_web_research_drops_unsourced_facts():
    from src.outreach.profile import PopulationProfile
    from src.outreach.web_research import research
    search_result = NS(type="web_search_tool_result",
                       content=[NS(url="https://real.example.org/about", title="Real Org")])
    extraction = {"organizations": [
        {"name": "Real Org", "type": "NGO", "geography": "Bihar",
         "facts": [{"text": "Works with rural women.", "source_url": "https://real.example.org/about"},
                   {"text": "Invented claim.", "source_url": "https://made-up.example.com"}],
         "channels": ["SHGs"], "relevance_reasoning": "fits", "caveats": []},
        {"name": "Invented Org", "type": "NGO", "geography": "?",
         "facts": [{"text": "x", "source_url": "https://nowhere.example.com"}],
         "channels": [], "relevance_reasoning": "?", "caveats": []},
    ]}
    client = FakeClient([message(search_result, text_block("notes")),
                         message(text_block(json.dumps(extraction)))])
    trace = Trace("q")
    profile = PopulationProfile(description="women in rural Bihar", filters=[], states=["bihar"])
    candidates = research(profile, LLM(client=client), trace)
    assert [c["name"] for c in candidates] == ["Real Org"]
    assert [f["text"] for f in candidates[0]["facts"]] == ["Works with rural women."]
    assert any("Hallucination guard" in w for w in trace.warnings)


@pytest.mark.integration
@requires_real_data
def test_data_agent_executes_the_tool_the_model_chooses():
    from src.agents.data_agent import run_llm
    client = FakeClient([
        message(tool_use("weighted_percentage", {"outcome": {"indicator": "currently_working"}}), stop="tool_use"),
        message(text_block("Model summary: about a quarter of women work.")),
    ])
    trace = Trace("What share of women work?")
    report = run_llm("What share of women work?", trace, LLM(client=client))
    facts = [s.text for s in trace.statements if s.kind == DATA_FACT]
    assert any("25.23%" in f for f in facts)                 # number from SQL, not from the model
    assert "weighted_percentage" in trace.tools_used()
    # messages: [0] user task, [1] assistant tool_use, [2] user tool_result, ...
    tool_result = client.requests[1]["messages"][2]["content"][0]
    assert tool_result["type"] == "tool_result" and tool_result["tool_use_id"] == "toolu_1"
    assert report.summary.startswith("Model summary")


@pytest.mark.integration
@requires_real_data
def test_orchestrator_llm_routing():
    from src.agents.orchestrator import answer_question
    routing = {"needs_data_agent": True, "needs_outreach_agent": False,
               "data_task": "Define v012 using lookup_variable.", "reasoning": "definition question"}
    client = FakeClient([
        message(text_block(json.dumps(routing))),
        message(tool_use("lookup_variable", {"name": "v012"}), stop="tool_use"),
        message(text_block("v012 is the respondent's current age.")),
        message(text_block("**v012** = respondent's current age (codebook).")),
    ])
    answer = answer_question("What does v012 mean?", llm=LLM(client=client))
    assert answer.mode.startswith("LLM")
    assert "lookup_variable" in answer.trace.tools_used()
    assert "Outreach Agent" not in answer.trace.agents_used()
    assert "Model-generated" in answer.markdown
