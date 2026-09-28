"""Live web research for the Outreach Agent (LLM mode only).

Two LLM calls:
    1. research: Claude uses Anthropic's server-side web_search tool (and our
       knowledge-base tool) and writes notes. Every URL it saw is collected
       from the search-result blocks and citations - by our code, not by
       asking the model which URLs it used.
    2. extract: a second call turns the notes into structured JSON
       (organizations, facts with source URLs, inferences).

Hallucination guard: any fact whose source_url was not actually returned by
web search or the knowledge base is dropped, and organizations left with no
sourced facts are dropped. The number of dropped items is recorded in the trace.
"""

import json
from datetime import date

from src.llm import text_of
from src.outreach.knowledge_base import search_knowledge_base
from src.tools.registry import tool_result_text

WEB_SEARCH_TOOL = {"type": "web_search_20260209", "name": "web_search", "max_uses": 6}
KB_TOOL = {
    "name": "search_outreach_knowledge_base",
    "description": "Search the project's curated, source-linked list of outreach organizations and programs.",
    "input_schema": {"type": "object", "properties": {"query": {"type": "string"},
                                                      "state": {"type": "string"}}, "required": ["query"]},
}
MAX_TURNS = 8

RESEARCH_SYSTEM = """You research organizations and communication channels that could reach a specific population of women in India, for an NGO planning outreach.

Rules:
- Only report organizations you found in web search results or in the knowledge base tool. Never rely on memory for facts.
- For each organization, note what its own website or a credible source says about who it serves, where, and how.
- Prefer official websites and government portals. Note when a source is secondary.
- Distinguish clearly between what a source states and your own judgement about relevance.
- Consider geography, target population, mission alignment, existing programs, channels and accessibility."""

EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {"organizations": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "type": {"type": "string"},
            "geography": {"type": "string"},
            "facts": {"type": "array", "items": {"type": "object", "properties": {
                "text": {"type": "string"}, "source_url": {"type": "string"}},
                "required": ["text", "source_url"], "additionalProperties": False}},
            "channels": {"type": "array", "items": {"type": "string"}},
            "relevance_reasoning": {"type": "string"},
            "caveats": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["name", "type", "geography", "facts", "channels", "relevance_reasoning", "caveats"],
        "additionalProperties": False}}},
    "required": ["organizations"], "additionalProperties": False,
}


def collect_urls(content_blocks, seen):
    """Record every URL that web search actually returned (and any citations)."""
    for block in content_blocks:
        block_type = getattr(block, "type", None)
        if block_type == "web_search_tool_result":
            results = getattr(block, "content", None)
            if isinstance(results, list):  # a list = success; an object = error
                for item in results:
                    url = getattr(item, "url", None)
                    if url:
                        seen[url] = getattr(item, "title", url)
        if block_type == "text":
            for citation in getattr(block, "citations", None) or []:
                url = getattr(citation, "url", None)
                if url:
                    seen[url] = getattr(citation, "title", url)


def research(profile, llm, trace):
    """Returns validated candidate organizations (same shape as knowledge_base.assess)."""
    seen_urls = {}
    brief = {
        "population": profile.description, "states": profile.states, "districts": profile.districts,
        "residence": profile.residence,
        "elevated_needs": [{"need": d["description"], "pct": d["pct"], "national_pct": d["national_pct"]}
                           for d in profile.elevated()],
        "channel_reach_from_data": [{"channel": r["description"], "pct": r["weighted_pct"]} for r in profile.reach],
    }
    messages = [{"role": "user", "content":
                 "Find NGOs, community organizations, public programs and communication channels that could "
                 f"plausibly reach this population:\n{json.dumps(brief, indent=2)}"}]
    notes = []
    for _ in range(MAX_TURNS):
        response = llm.create(system=RESEARCH_SYSTEM, messages=messages, tools=[WEB_SEARCH_TOOL, KB_TOOL],
                              purpose="outreach web research")
        collect_urls(response.content, seen_urls)
        notes.append(text_of(response))
        messages.append({"role": "assistant", "content": response.content})
        if response.stop_reason == "pause_turn":
            continue  # server-side search loop paused; re-send to let it resume
        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if response.stop_reason != "tool_use" or not tool_uses:
            break
        results = []
        for use in tool_uses:
            hits = search_knowledge_base(**use.input)
            for org in hits:
                for fact in org["facts"]:
                    seen_urls[fact["source_url"]] = org["name"]
            trace.step("Outreach Agent", "called tool", "search_outreach_knowledge_base",
                       detail=f"{len(hits)} organizations", inputs=use.input)
            results.append({"type": "tool_result", "tool_use_id": use.id, "content": tool_result_text(hits)})
        messages.append({"role": "user", "content": results})
    trace.step("Outreach Agent", "called tool", "web_search",
               detail=f"{len(seen_urls)} distinct URLs returned by search/knowledge base")

    extracted = llm.json(
        system="Extract organizations from research notes into JSON. Use only facts present in the notes, "
               "and only source URLs from the allowed list.",
        prompt=f"Allowed source URLs:\n{json.dumps(list(seen_urls), indent=1)}\n\nResearch notes:\n" + "\n\n".join(notes),
        schema=EXTRACT_SCHEMA, purpose="outreach extraction")

    candidates, dropped_facts, dropped_orgs = [], 0, 0
    today = date.today().isoformat()
    for org in extracted["organizations"]:
        facts = [f for f in org["facts"] if f["source_url"] in seen_urls]
        dropped_facts += len(org["facts"]) - len(facts)
        if not facts:
            dropped_orgs += 1
            continue
        for f in facts:
            trace.add_source(seen_urls[f["source_url"]], f["source_url"], "web search (Outreach Agent)", today)
        candidates.append({
            "id": org["name"].lower().replace(" ", "-"), "name": org["name"], "type": org["type"],
            "origin": "live web research", "geography": org["geography"],
            "facts": [{**f, "accessed": today} for f in facts],
            "score": None, "need_matches": [], "channel_matches": [],
            "inference": f"(model-generated) {org['relevance_reasoning']}",
            "caveats": org["caveats"],
        })
    if dropped_facts or dropped_orgs:
        trace.warn(f"Hallucination guard: dropped {dropped_facts} facts and {dropped_orgs} organizations whose "
                   "source URL was not returned by web search.")
    return candidates
