"""The Orchestrator: decides which agents a question needs, runs them in
order, and hands the result to the synthesis step.

    question -> plan -> Data Agent? -> (population) -> Outreach Agent? -> synthesis -> Answer

Routing:
    offline - router.plan_question (keyword rules, fully traceable)
    LLM     - Claude returns a structured routing decision (JSON schema);
              if that call fails, the offline plan is used.

The orchestrator itself never touches data or the web; it only decides and
delegates. That keeps each agent small and testable.
"""

import json
from dataclasses import dataclass

from src.agents import data_agent, outreach_agent, synthesis
from src.agents.router import plan_question
from src.agents.trace import CAVEAT, Trace
from src.llm import get_llm
from src.outreach.profile import build_profile
from src.rag.retriever import get_retriever

AGENT = "Orchestrator"

ROUTING_SCHEMA = {
    "type": "object",
    "properties": {
        "needs_data_agent": {"type": "boolean"},
        "needs_outreach_agent": {"type": "boolean"},
        "data_task": {"type": "string"},
        "reasoning": {"type": "string"},
    },
    "required": ["needs_data_agent", "needs_outreach_agent", "data_task", "reasoning"],
    "additionalProperties": False,
}

ROUTING_SYSTEM = """You route questions in a research and outreach system about the India NFHS-5 women's survey.

Agents:
- Data Agent: variable definitions (codebook RAG), counts, weighted percentages, comparisons, identifying underserved groups, channel reach from the data.
- Outreach Agent: external research on NGOs, public programs and communication channels for a population. It needs a target population, which the Data Agent provides (or the previous answer's population, given as context).

Decide which agents are needed. Do not call the Outreach Agent unless the user asks about organizations, programs, partners or channels. Write data_task as a precise instruction for the Data Agent."""


@dataclass
class Answer:
    question: str
    markdown: str
    trace: Trace
    population: dict = None

    @property
    def mode(self):
        return self.trace.mode


def route_with_llm(question, context_population, llm, plan):
    context = json.dumps({"previous_population": context_population}) if context_population else "none"
    decision = llm.json(system=ROUTING_SYSTEM, prompt=f"Question: {question}\nContext: {context}",
                        schema=ROUTING_SCHEMA, purpose="routing", max_tokens=2000)
    plan.needs_data = decision["needs_data_agent"]
    plan.needs_outreach = decision["needs_outreach_agent"]
    return decision


def answer_question(question, context_population=None, llm="auto"):
    """Answer one question. `context_population` is the previous answer's
    population (a dict with 'filters'), so follow-ups like "which NGOs could
    reach this population?" work."""
    trace = Trace(question)
    llm = get_llm() if llm == "auto" else llm
    trace.mode = f"LLM ({llm.model})" if llm else "offline (rule-based routing, template answers)"

    variables = get_retriever("docs").variables_in(question)
    plan = plan_question(question, variables, context_population)
    trace.step(AGENT, "planned", "rule-based router", detail="; ".join(plan.reasons))

    data_task = question
    if llm is not None:
        try:
            decision = route_with_llm(question, context_population, llm, plan)
            data_task = decision["data_task"]
            trace.step(AGENT, "decided", "LLM routing",
                       detail=f"data={plan.needs_data}, outreach={plan.needs_outreach}: {decision['reasoning']}")
        except Exception as exc:
            trace.warn(f"LLM routing failed ({type(exc).__name__}); used the rule-based plan instead.")

    data_report = None
    if plan.needs_data:
        trace.step(AGENT, "delegated", "Data Agent", detail=data_task[:200])
        if llm is not None:
            data_report = data_agent.run_llm(data_task, trace, llm,
                                             needs_population=plan.needs_outreach and not context_population)
        else:
            data_report = data_agent.run_offline(plan, question, trace, context_population)

    population = data_report.population if data_report else None
    if population is None and plan.needs_outreach and context_population:
        population = build_profile(context_population["filters"], trace, context_population.get("description"))

    outreach_report = None
    if plan.needs_outreach:
        if population is None:
            trace.say(CAVEAT, "Outreach research needs a target population; none was identified.")
        else:
            trace.step(AGENT, "delegated", "Outreach Agent", detail=population.description)
            outreach_report = outreach_agent.run(population, trace, llm)

    markdown = synthesis.synthesize(question, plan, trace, data_report, outreach_report, llm)
    if llm is not None:
        trace.llm_calls = llm.calls
    return Answer(question=question, markdown=markdown, trace=trace,
                  population=population.to_dict() if population else None)
