"""The Outreach Research Agent: finds organizations and channels that could
plausibly reach a population identified by the Data Agent.

Input:  a PopulationProfile (computed from data, see outreach/profile.py)
Output: candidate organizations, each with
          FACTS      - what a source says, with its URL
          INFERENCE  - why it *may* be relevant (our rubric or the model's reasoning)
          CAVEATS    - what we could not verify
        plus data-grounded channel findings (which channels reach this population).

Offline it uses the curated knowledge base (retrieved with the outreach RAG
index, scored with a transparent rubric). With an LLM it also runs live web
research, and every web fact is checked against the URLs search really returned.
"""

from dataclasses import dataclass, field

from src.agents.trace import CAVEAT, DATA_FACT, INFERENCE, SOURCE_FACT
from src.outreach.knowledge_base import rank_organizations
from src.outreach.web_research import research
from src.rag.retriever import get_retriever

AGENT = "Outreach Agent"
MAX_CANDIDATES = 10   # the curated list is small, so every relevant entry is shown


@dataclass
class OutreachReport:
    candidates: list = field(default_factory=list)
    mode: str = "curated knowledge base"


def normalized(name):
    return "".join(ch for ch in name.lower() if ch.isalnum())


def run(profile, trace, llm=None):
    trace.step(AGENT, "received population", detail=profile.description,
               inputs={"filters": profile.filters, "states": profile.states})

    # 1. Retrieve from the outreach knowledge base (the outreach RAG index).
    query = profile.description + " " + " ".join(d["description"] for d in profile.elevated())
    hits = get_retriever("outreach").retrieve(query, k=9)
    for hit in hits:
        trace.add_document(hit)
    trace.step(AGENT, "retrieved", "outreach knowledge base (RAG)",
               detail=f"{len(hits)} organizations retrieved for: {query[:120]}")

    # 2. Score them with the transparent rubric.
    candidates = [c for c in rank_organizations(profile) if c["score"]["total"] > 0]
    trace.step(AGENT, "scored", "relevance rubric",
               detail="; ".join(f"{c['name']}: {c['score']['total']}" for c in candidates))

    # 3. Live web research (LLM mode only).
    report = OutreachReport()
    if llm is not None:
        web = research(profile, llm, trace)
        known = {normalized(c["name"]) for c in candidates}
        candidates = candidates + [w for w in web if normalized(w["name"]) not in known]
        report.mode = "curated knowledge base + live web research"
    else:
        trace.say(CAVEAT, "Offline mode: organizations come only from the curated knowledge base "
                          "(9 organizations, verified on their websites on 2026-09-27). Live web research "
                          "needs ANTHROPIC_API_KEY. State- or district-specific NGOs are likely missing.")
    report.candidates = candidates[:MAX_CANDIDATES]

    # 4. Statements: facts (with sources) kept separate from inferences.
    for c in report.candidates:
        for fact in c["facts"]:
            trace.say(SOURCE_FACT, f"{c['name']}: {fact['text']}", [fact["source_url"]])
            trace.add_source(c["name"], fact["source_url"], c["origin"], fact.get("accessed"))
        trace.say(INFERENCE, c["inference"], sorted({f["source_url"] for f in c["facts"]}))
        for caveat in c["caveats"]:
            trace.say(CAVEAT, f"{c['name']}: {caveat}")

    channel_findings(profile, trace)
    return report


def channel_findings(profile, trace):
    usable = [r for r in profile.reach if r["weighted_pct"] is not None]
    if not usable:
        return
    trace.say(DATA_FACT, f"In {profile.description}: " + "; ".join(
        f"{r['description'].lower()}: {r['weighted_pct']}% (n={r['n_valid']:,})" for r in usable) + ".",
        ["channel_reach"])
    widest = [r for r in usable if r["weighted_pct"] >= 25]
    narrow = [r for r in usable if r["weighted_pct"] < 25]
    if widest:
        trace.say(INFERENCE, "Channels that already reach at least a quarter of this population in the data ("
                  + ", ".join(f"{r['description'].lower()} {r['weighted_pct']}%" for r in widest)
                  + ") are more plausible routes for outreach than channels reaching fewer women ("
                  + ", ".join(f"{r['description'].lower()} {r['weighted_pct']}%" for r in narrow)
                  + "). Reach is not the same as effectiveness, which the data does not measure.")
