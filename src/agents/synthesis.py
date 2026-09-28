"""Final synthesis: combine the evidence into one readable answer.

The evidence (labelled statements, calculations, sources) is always produced
by code. This layer only writes the narrative on top of it:
    offline - a template that arranges the statements
    LLM     - Claude writes a summary from the evidence JSON only; then a
              number check flags any number in the text that doesn't appear
              in the evidence (a guard against hallucinated statistics).
"""

import json
import re

from src.agents.trace import CAVEAT, DATA_FACT, DOC_FACT, INFERENCE, SOURCE_FACT
from src.llm import text_of

AGENT = "Synthesis"

SYSTEM = """You write the final answer for a research and outreach decision-support system about the India NFHS-5 survey.

You receive the user's question and an evidence package. Rules:
- Use ONLY the evidence. Do not add facts, numbers or organizations that are not in it.
- Copy numbers exactly as they appear in the evidence.
- Keep three kinds of statements visibly separate: data findings, facts stated by external sources (name the source), and interpretations (say "this suggests" / "may", never present them as facts).
- Mention important caveats (small samples, subsample questions, definition choices, no confidence intervals).
- Never claim that one thing causes another.
- Be concise: a short direct answer first, then supporting points. Markdown is fine."""


def evidence_package(trace, data_report, outreach_report):
    return {
        "statements": [{"kind": s.kind, "text": s.text, "evidence": s.evidence} for s in trace.statements],
        "variables_used": trace.variables,
        "data_agent_notes (model-generated)": data_report.summary if data_report else "",
        "outreach_candidates": [{k: c[k] for k in ("name", "facts", "inference", "caveats")}
                                for c in (outreach_report.candidates if outreach_report else [])],
        "warnings": trace.warnings,
    }


def numbers_in(text):
    return re.findall(r"(?<![\w.])\d[\d,]*(?:\.\d+)?", text)


def unverified_numbers(narrative, trace, question):
    """Numbers in the narrative that no evidence number rounds to."""
    evidence_text = json.dumps([s.text for s in trace.statements] + [c.get("rows", [])[:80] for c in trace.calculations],
                               default=str) + question
    evidence = set()
    for token in numbers_in(evidence_text):
        try:
            evidence.add(float(token.replace(",", "")))
        except ValueError:
            pass
    problems = []
    for token in set(numbers_in(narrative)):
        value = float(token.replace(",", ""))
        if value <= 10 and "." not in token:
            continue   # small counts like "3 states" or list numbering
        decimals = len(token.split(".")[1]) if "." in token else 0
        if not any(round(e, decimals) == value for e in evidence):
            problems.append(token)
    return sorted(problems)


def offline_narrative(plan, trace, outreach_report):
    by_kind = lambda kind: [s.text for s in trace.statements if s.kind == kind]
    lines = []
    if plan.intent == "documentation":
        docs = by_kind(DOC_FACT)
        lines += [f"- {t}" for t in docs[:6]] or ["No matching documentation was found."]
    elif plan.intent in ("count", "percentage"):
        lines += [f"- {t}" for t in by_kind(DATA_FACT)[:6]]
    elif plan.intent in ("underserved", "outreach_only"):
        inferences = [t for t in by_kind(INFERENCE) if "most underserved" in t]
        if inferences:
            lines.append(f"**{inferences[0]}**")
        lines += [f"- {t}" for t in by_kind(DATA_FACT)[:4]]
    if outreach_report and outreach_report.candidates:
        lines += ["", "**Potentially relevant organizations and programs** (inferences, not endorsements):"]
        for number, c in enumerate(outreach_report.candidates, start=1):
            score = f" (rubric score {c['score']['total']})" if c.get("score") else ""
            lines.append(f"{number}. **{c['name']}**{score}: {c['facts'][0]['text']} [source]({c['facts'][0]['source_url']})")
        channel = [t for t in by_kind(INFERENCE) if t.startswith("Channels that already reach")]
        if channel:
            lines += ["", f"**Channels:** {channel[0]}"]
    caveats = by_kind(CAVEAT)
    if caveats:
        lines += ["", "**Caveats:** " + " ".join(caveats[:4])]
    return "\n".join(lines) if lines else "I could not answer this question offline. See the evidence and trace."


def synthesize(question, plan, trace, data_report, outreach_report, llm=None):
    if llm is None:
        narrative = offline_narrative(plan, trace, outreach_report)
        trace.step(AGENT, "wrote answer", "template", detail="offline template over labelled statements")
        return narrative
    package = evidence_package(trace, data_report, outreach_report)
    response = llm.create(system=SYSTEM, messages=[{"role": "user", "content":
                          f"Question: {question}\n\nEvidence package:\n{json.dumps(package, default=str)}"}],
                          purpose="synthesis")
    narrative = text_of(response)
    problems = unverified_numbers(narrative, trace, question)
    if problems:
        trace.warn("Number check: these numbers in the model-written summary were not found in the evidence: "
                   + ", ".join(problems) + ". Treat them with caution.")
    trace.step(AGENT, "wrote answer", "LLM", detail=f"model-written summary; unverified numbers: {problems or 'none'}")
    return "*(Model-generated summary of the evidence below.)*\n\n" + narrative


def evidence_markdown(trace):
    """Plain-text rendering of the evidence (used by the CLI)."""
    lines = ["## Evidence"]
    for kind in (DATA_FACT, DOC_FACT, SOURCE_FACT, INFERENCE, CAVEAT):
        items = [s for s in trace.statements if s.kind == kind]
        if items:
            lines.append(f"\n### {kind}")
            lines += [f"- {s.text}" + (f"  \n  _evidence: {', '.join(s.evidence[:3])}_" if s.evidence else "")
                      for s in items]
    if trace.variables:
        lines.append("\n## Variables and definitions")
        lines += [f"- `{name}`: {v['definition']} ({v['source']})" for name, v in trace.variables.items()]
    if trace.external_sources:
        lines.append("\n## External sources")
        lines += [f"- [{s['title']}]({s['url']}) ({s['via']}, accessed {s['accessed']})" for s in trace.external_sources]
    lines.append("\n## Agents and tools")
    lines += [f"- {s.agent}: {s.action} {s.tool}".rstrip() + (f" ({s.detail[:160]})" if s.detail else "")
              for s in trace.steps]
    if trace.warnings:
        lines.append("\n## Warnings")
        lines += [f"- {w}" for w in trace.warnings]
    return "\n".join(lines)
