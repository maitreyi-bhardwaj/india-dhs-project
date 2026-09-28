"""Streamlit interface. Run with:  streamlit run app.py

Layout:
    sidebar  - system status, mode, example questions, follow-up context
    main     - question box, answer, then tabs showing exactly how the answer
               was produced (evidence, calculations, documentation, sources, trace)
"""

import pandas as pd
import streamlit as st

from src.agents.orchestrator import answer_question
from src.agents.trace import CAVEAT, DATA_FACT, DOC_FACT, INFERENCE, SOURCE_FACT
from src.config import DATABASE_PATH, INDEX_DIR, LLM_MODEL, llm_available

EXAMPLES = [
    "What does v012 mean?",
    "What categories does s116 contain?",
    "What variables are relevant to women's employment?",
    "How many respondents are aged 18-24?",
    "What percentage of women aged 18-24 in Bihar own a mobile phone?",
    "What percentage of rural women do not have health insurance?",
    "What percentage of women are currently working, by state?",
    "What population appears most underserved according to this dataset?",
    "Which NGOs or outreach channels could potentially reach this population?",
    "Identify an underserved population and recommend potentially relevant outreach organizations and channels.",
]

KIND_STYLE = {DATA_FACT: ":blue", DOC_FACT: ":violet", SOURCE_FACT: ":green", INFERENCE: ":orange", CAVEAT: ":red"}


def sidebar():
    st.sidebar.header("System status")
    ready = True
    for label, ok, fix in [
        ("Analysis database", DATABASE_PATH.exists(), "python -m src.data.pipeline"),
        ("RAG indexes", (INDEX_DIR / "docs" / "dense.npy").exists(), "python -m src.rag.index"),
    ]:
        st.sidebar.write(("✅ " if ok else "❌ ") + label)
        if not ok:
            st.sidebar.code(fix)
            ready = False
    use_llm = False
    if llm_available():
        use_llm = st.sidebar.toggle(f"Use LLM ({LLM_MODEL})", value=True)
    else:
        st.sidebar.info("Offline mode: rule-based routing and template answers. "
                        "Set ANTHROPIC_API_KEY in .env for LLM routing, tool selection and live web research.")
    st.sidebar.header("Examples")
    for example in EXAMPLES:
        if st.sidebar.button(example, use_container_width=True):
            st.session_state.question = example
    population = st.session_state.get("population")
    if population:
        st.sidebar.header("Follow-up context")
        st.sidebar.write(f"Population from the last answer: **{population['description']}**")
        if st.sidebar.button("Clear context"):
            st.session_state.population = None
    return ready, use_llm


def show_evidence(trace):
    st.caption("Every statement is labelled. FACT (dataset) = computed by SQL/Python; FACT (documentation) = "
               "codebook or project docs; FACT (external source) = stated by the linked source; "
               "INFERENCE = an interpretation (rule-based or model-generated), not a fact.")
    for kind in (DATA_FACT, DOC_FACT, SOURCE_FACT, INFERENCE, CAVEAT):
        items = [s for s in trace.statements if s.kind == kind]
        if not items:
            continue
        st.markdown(f"**{KIND_STYLE[kind]}[{kind}]** ({len(items)})")
        for s in items:
            st.markdown(f"- {s.text}")
            if s.evidence:
                st.caption("evidence: " + ", ".join(s.evidence[:4]))


def show_calculations(trace):
    if not trace.calculations:
        st.write("No calculations were needed for this question.")
    for number, calc in enumerate(trace.calculations, start=1):
        with st.expander(f"{number}. {calc['title']}", expanded=number <= 2):
            if calc.get("population"):
                st.markdown(f"**Population:** {calc['population']}")
            if calc.get("numerator"):
                st.markdown(f"**Numerator:** {calc['numerator']}  \n**Denominator:** {calc['denominator']}")
            if calc.get("method"):
                st.markdown("**Method:**\n" + "\n".join(f"- {m}" for m in calc["method"]))
            st.markdown("**Variables:** " + ", ".join(f"`{v}`" for v in calc.get("variables", [])))
            for sql_source in ([calc] if "sql" in calc else calc.get("queries", [])[:3]):
                st.code(sql_source["sql"], language="sql")
                if sql_source.get("params"):
                    st.caption(f"parameters: {sql_source['params']}")
            if calc.get("rows"):
                st.dataframe(pd.DataFrame(calc["rows"]), use_container_width=True, hide_index=True)


def show_charts(trace):
    shown = 0
    for table in trace.tables:
        chart, rows = table.get("chart"), table["rows"]
        if not chart or len(rows) < 2:
            continue
        frame = pd.DataFrame(rows)
        if chart["x"] in frame and chart["y"] in frame:
            st.markdown(f"**{table['title']}**")
            st.bar_chart(frame.set_index(chart["x"])[chart["y"]].dropna())
            shown += 1
    if not shown:
        st.write("No chart for this answer.")


def show_documents(trace):
    if not trace.documents:
        st.write("No documentation was retrieved.")
    for doc in trace.documents:
        with st.expander(f"{doc['title']}  ·  {doc['source']}  ·  {doc['match']}  ·  score {doc['score']}"):
            st.text(doc["text"])
            st.caption(f"chunk id: {doc['chunk_id']}  ·  dense similarity {doc['dense_score']}  ·  "
                       f"keyword similarity {doc['sparse_score']}")


def show_sources(trace):
    if not trace.external_sources:
        st.write("No external sources were used.")
    for s in trace.external_sources:
        st.markdown(f"- [{s['title']}]({s['url']}): via {s['via']}, accessed {s['accessed']}")
    if trace.variables:
        st.markdown("**Variables and their definitions**")
        st.dataframe(pd.DataFrame([{"variable": k, **v} for k, v in trace.variables.items()]),
                     use_container_width=True, hide_index=True)


def show_trace(trace):
    st.markdown(f"**Agents:** {' → '.join(trace.agents_used())}  \n**Tools:** {', '.join(trace.tools_used())}")
    st.dataframe(pd.DataFrame([{"agent": s.agent, "action": s.action, "tool": s.tool, "detail": s.detail,
                                "seconds": s.seconds} for s in trace.steps]),
                 use_container_width=True, hide_index=True)
    if trace.llm_calls:
        st.markdown("**LLM calls**")
        st.dataframe(pd.DataFrame(trace.llm_calls), use_container_width=True, hide_index=True)


def main():
    st.set_page_config(page_title="NFHS-5 Research & Outreach Assistant", layout="wide")
    st.title("NFHS-5 Research & Outreach Assistant")
    st.caption("Ask about the India DHS 2019-21 (NFHS-5) women's survey. Numbers come from SQL on the data, "
               "definitions from the codebook, organizations from sourced research.")
    ready, use_llm = sidebar()
    if not ready:
        st.error("Build the database and indexes first (see the sidebar).")
        return

    question = st.text_input("Your question", key="question",
                             placeholder="e.g. What percentage of rural women in Bihar own a mobile phone?")
    if not st.button("Ask", type="primary") or not question:
        return

    with st.spinner("Routing, retrieving, querying..."):
        answer = answer_question(question, context_population=st.session_state.get("population"),
                                 llm="auto" if use_llm else None)
    if answer.population:
        st.session_state.population = answer.population
    trace = answer.trace

    st.markdown(answer.markdown)
    left, middle, right = st.columns(3)
    left.metric("Mode", "LLM" if use_llm else "Offline")
    middle.metric("Seconds", trace.to_dict()["seconds"])
    right.metric("Tool calls", sum(1 for s in trace.steps if s.action == "called tool"))
    for warning in trace.warnings:
        st.warning(warning)

    tabs = st.tabs(["Evidence", "Analysis & SQL", "Charts", "Documentation (RAG)", "Sources & variables",
                    "Agents & tools"])
    with tabs[0]:
        show_evidence(trace)
    with tabs[1]:
        show_calculations(trace)
    with tabs[2]:
        show_charts(trace)
    with tabs[3]:
        show_documents(trace)
    with tabs[4]:
        show_sources(trace)
    with tabs[5]:
        show_trace(trace)
