# How the assistant works, from the ground up

This guide explains every part of the research and outreach assistant using
this project's own code. File references like `src/rag/index.py:31` point to
the exact line where something happens.

## The whole system in one picture

```
                              USER QUESTION
                                    │
                                    ▼
                   ┌──────────────────────────────────┐
                   │ ORCHESTRATOR                     │  src/agents/orchestrator.py
                   │ decides which agents are needed  │  (rules offline, Claude online)
                   └────────┬─────────────────┬───────┘
                            │                 │  population profile (numbers from SQL)
                            ▼                 ▼
          ┌──────────────────────┐   ┌──────────────────────────┐
          │ DATA AGENT           │   │ OUTREACH AGENT           │
          │ src/agents/          │   │ src/agents/              │
          │   data_agent.py      │   │   outreach_agent.py      │
          └──┬──────────┬────────┘   └──┬────────────┬──────────┘
             │          │               │            │
             ▼          ▼               ▼            ▼
      ┌──────────┐ ┌─────────────┐ ┌──────────┐ ┌──────────────┐
      │ DOC RAG  │ │ SQL + PYTHON│ │ KB RAG + │ │ WEB SEARCH   │
      │ codebook │ │ SQLite db   │ │ rubric   │ │ (LLM mode)   │
      └────┬─────┘ └──────┬──────┘ └────┬─────┘ └──────┬───────┘
           └───────┬──────┘             └──────┬───────┘
                   ▼                           ▼
            ┌───────────────────────────────────────────┐
            │ TRACE: every step, variable, SQL query,   │  src/agents/trace.py
            │ source and labelled statement             │
            └──────────────────────┬────────────────────┘
                                   ▼
                     ┌───────────────────────────┐
                     │ SYNTHESIS: final answer   │  src/agents/synthesis.py
                     └─────────────┬─────────────┘
                                   ▼
                     Streamlit UI (src/app/ui.py): answer + evidence tabs
```

## 1. What Python does here

Python is the glue and the calculator. It:

- reads the 5.2 GB Stata file in chunks (`src/data/loader.py`);
- cleans it and builds the database (`src/data/pipeline.py`);
- runs the retrieval math (`src/rag/`);
- combines SQL results into rankings and age-standardized rates (`src/analysis/stats.py`);
- runs the agents and serves the UI.

Example: age standardization is a weighted average of seven age-specific rates.
That is a few lines of Python (`src/analysis/stats.py:122`) on top of three
SQL queries.

## 2. What SQL does here

SQL answers structured questions: filter, group, sum. Every percentage in
the system comes from one query built in `src/analysis/queries.py:154`:

```sql
SELECT COUNT(y) AS n_valid,
       SUM(w * y) AS weighted_yes,
       SUM(CASE WHEN y IS NOT NULL THEN w END) AS weighted_valid  -- denominator
FROM (SELECT w, owns_mobile_phone AS y FROM women WHERE v012 BETWEEN ? AND ? AND v024 IN (?))
```

Python then divides the two sums (`src/analysis/queries.py:189`). Two details
matter:

- **The `?` placeholders.** Values like 18, 24 and 10 are passed separately from
  the SQL text, so a value like `"1 OR 1=1"` can never become SQL. This is
  tested in `tests/test_queries.py`.
- **The `CASE WHEN ... IS NOT NULL` denominator.** A plain `SUM(w)` would include
  women who were never asked the question. That mistake actually happened
  while building this project: it gave 3.76% employment instead of 25.23%.

## 3. What the database does

`data/processed/nfhs5_women.sqlite` is an analysis-ready copy of 36 curated
variables plus 18 derived indicators for all 724,115 women (132 MB, versus
5.2 GB for the original). It also stores:

| Table | What it holds |
|---|---|
| `variables`, `value_labels` | codebook metadata for the curated variables |
| `derived_indicators` | the rule for each indicator |
| `cleaning_log` | every value set to missing, and why |
| `validation_checks` | 13 verified relationships between variables |
| `build_info` | the source file's size and timestamp |

Why a database instead of re-reading the Stata file:

- A query takes milliseconds instead of a 12-second scan.
- SQL is a clear, checkable language for "who is counted".
- It's opened read-only (`src/analysis/database.py:25`), so no analysis can
  change it.

The original `.DTA` file is never written to. The pipeline checks its size and
timestamp before and after the build.

## 4. What embeddings are

An embedding is a list of numbers representing a piece of text, where texts
about similar things get similar numbers.

**Where it happens:** `src/rag/index.py:31` calls `embedder.embed(texts)`,
turning each of the 2,146 documentation chunks into 256 numbers.

**How** (`src/rag/embeddings.py`):

1. **TF-IDF:** count (lightly stemmed) words, weighting rare words higher.
   "covered" and "coverage" both become "cover".
2. **SVD** (singular value decomposition): compress roughly 50,000 word
   dimensions into 256, which groups words that appear together, such as
   "anemia" and "hemoglobin".

This technique is called LSA (latent semantic analysis). It was chosen over a
neural embedding model because it needs no PyTorch (1–2 GB) and no API key,
and it's good enough for a codebook. Swapping in a neural model would only
change `embeddings.py`.

## 5. What a vector database is

A vector database stores vectors with their text and metadata, and finds the
vectors nearest to a query vector.

**Here:** `src/rag/vector_store.py` keeps the vectors in a NumPy array
(`data/index/docs/dense.npy`) and the chunks in `chunks.jsonl`. Search is one
matrix multiplication (`self.dense @ query_vector`). Because the vectors are
normalized, that product is the cosine similarity.

Products like Chroma, pgvector or FAISS do the same thing at millions of
vectors, with approximate search and filtering. For 2,146 chunks, brute force
takes about a millisecond and every step is visible.

## 6. What RAG is

RAG (retrieval-augmented generation) means: retrieve relevant text first,
then answer using only that text. The model doesn't rely on its memory.

```
"What does v012 mean?"
   │
   ├─ exact lookup: "v012" is a codebook variable ─────► codebook:v012 (pinned first)
   ├─ dense:  embed question, cosine vs 2,146 chunks ─► ranked list A
   └─ sparse: TF-IDF keyword similarity ──────────────► ranked list B
                                  │
             Reciprocal Rank Fusion: 1/(60+rankA) + 1/(60+rankB)
                                  │
                         top chunks + scores
                                  │
             answer built only from them (template, or Claude)
```

**Where the RAG retrieves v012's definition:** `src/rag/retriever.py:94`, where
`exact_positions` finds the variable name in the question. Exact identifiers
are a dictionary lookup, not a similarity search.

**Why two similarity methods, fused by rank:**

- Dense vectors find chunks on the same topic even when they use different words.
- Sparse vectors reward shared rare words.
- The raw scores of the two methods live on different scales. Averaging them
  let the dense scores dominate, so "how are sampling weights used" matched
  "have used: pill". Fusing by *rank* fixed it. This is tested in
  `tests/test_retrieval.py`.

**What is deliberately not in the RAG:** the 724,115 rows. Numbers are never
retrieved as text; they are computed by SQL.

## 7. What an agent is

An agent is an LLM (or, offline, a rule set) that decides which tools to
use, calls them, looks at the results, and repeats until done. The tool-use
loop in `src/agents/data_agent.py:189`:

```
send question + tool descriptions to Claude
while Claude replies "tool_use":
    run the tool it asked for (src/agents/data_agent.py:219)
    send the result back
return Claude's final text
```

A tool is just a Python function with a description and a JSON schema
(`src/tools/registry.py`). The schema is how Claude knows what arguments to
write. The same functions run offline, called directly by the rule-based agent.

**Where Python calculated the percentage, even in LLM mode:** Claude only
*chooses* `weighted_percentage` and its arguments. Our code runs the SQL, and
the DATA FACT sentence is generated from the tool's output by
`src/agents/facts.py` (`src/agents/data_agent.py:222`), never from Claude's
text.

## 8. What an agentic RAG system is

Plain RAG always does "retrieve, then answer". Agentic RAG lets an agent decide:

- *whether* to retrieve at all;
- *what* to retrieve (codebook? methodology?);
- whether it also needs SQL, Python analysis or web research;
- in *what order*, feeding one tool's output into the next.

In this project:

| Question | What runs |
|---|---|
| "What does v012 mean?" | only `lookup_variable` |
| "How many respondents are aged 18–24?" | `lookup_variable` (for v012), then `count_respondents` |
| "Identify an underserved population and recommend outreach organizations" | documentation RAG (definition of underserved), codebook lookups (7 variables), 3 rankings, a population profile (36 SQL queries), knowledge-base RAG, the relevance rubric, then synthesis |

## 9. What the Outreach Agent does

It receives a **PopulationProfile** (`src/outreach/profile.py:62`). This is a
small, fully computed description of the target population: filters, states,
deprivations versus national, and channel reach, all from SQL. It never sees
raw data.

Then:

1. **Retrieve** candidates from the outreach knowledge base index (a second RAG
   collection).
2. **Score** them with a transparent rubric (`src/outreach/knowledge_base.py:37`):
   - geography;
   - whether the organization's stated work matches needs that are elevated
     in this population;
   - whether its channels already reach at least 25% of the population.
3. **(LLM mode)** web search, followed by a hallucination guard
   (`src/outreach/web_research.py:127`): a fact is kept only if its URL was
   actually returned by the search tool.
4. **Label** each part of the output:
   - FACT (external source), with a URL: "The organization states X."
   - INFERENCE: "It *may* be a relevant partner because ...".
   - CAVEAT: "The homepage does not name Bihar."

## 10. What the Orchestrator does

It reads the question, decides which agents are needed, runs them in order
and passes the Data Agent's population to the Outreach Agent.

**Where the decision to call the outreach agent happens:**

- **Offline:** `src/agents/router.py:96` (does the question ask about
  organizations or channels?) and `src/agents/router.py:162`.
- **LLM mode:** `route_with_llm` (`src/agents/orchestrator.py:60`) asks Claude
  for a structured JSON decision.
- **Either way:** the call itself is at `src/agents/orchestrator.py:110`.

The orchestrator never touches data or the web itself. It only decides and
delegates, which keeps each agent small and testable.

## 11. How information moves through the system

Worked example: *"Identify an underserved population and recommend outreach
organizations."*

```
1. Orchestrator: intent = underserved, outreach needed        (router.py)
2. Data Agent:   search_documentation("what underserved means")  → methodology.md
3. Data Agent:   lookup_variable × 7 (v106, v155, v157-9, v481, s361) → codebook definitions
4. Data Agent:   rank_underserved_groups(state × residence)    → rural Bihar, score 61.13
                 rank_underserved_groups(district)             → Kishanganj, Saharsa, ...
                 rank_underserved_groups(access indicators)    → rural Bihar is #8 of 71 (sensitivity)
5. Data Agent:   build_profile(rural Bihar)                    → 36 SQL queries: needs vs national,
                                                                 channel reach (TV 40.76%, phone 49.26%, ...)
6. Outreach:     KB retrieval + rubric                         → 8 organizations with sourced facts
7. Synthesis:    answer from the labelled statements
8. UI:           answer + tabs for evidence, SQL, charts, documentation, sources, trace
```

Every arrow writes into the Trace (`src/agents/trace.py`). That's what lets
the UI answer the seven traceability questions: data used, variables,
definitions, calculations, sources, facts, and interpretations.

## 12. Why each technology was chosen

| Need | Choice | Why | Alternative |
|---|---|---|---|
| Read 5.2 GB Stata file | pandas `StataReader`, chunked, `columns=` | reads only the needed columns; under 1 GB of memory | pyreadstat |
| Analysis-ready data | SQLite | built into Python, no server, fast enough for 724k rows | DuckDB (faster, one more dependency), Postgres |
| Numbers | SQL + Python, never the LLM | exact and reproducible; tested against Analyses 1–6 | letting the LLM compute (unreliable) |
| Embeddings | LSA (scikit-learn) | local, small, no key; good enough for a codebook | neural embeddings (Voyage API, sentence-transformers) |
| Vector store | NumPy + JSON lines | about 50 lines, fully visible, fast at this size | Chroma, FAISS, pgvector |
| Retrieval | exact lookup + dense + sparse, RRF | identifiers need exact match; topics need similarity | dense only (failed on variable names) |
| LLM | Claude (`claude-opus-5`) via the Anthropic SDK, manual tool loop | tool use, structured outputs, server-side web search | an agent framework (hides the loop you're learning) |
| Agent framework | none | the loop is about 30 lines; a framework would hide it | LangChain, LlamaIndex |
| UI | Streamlit | a Python-only web app in one file | Gradio, a React front end |

**What was not made an agent:**
- data cleaning, SQL building, the relevance rubric and the fact sentences are
  deterministic functions;
- agents are used only where a *decision* is genuinely needed: which tools,
  which order, which search queries.

## What is not built yet

- LLM mode hasn't been run against the live API (no key was available when it
  was built). Its logic is tested with a fake client (`tests/test_llm_mode.py`).
- No survey-design confidence intervals (needs `v021`/`v022` in the queries).
- The outreach knowledge base has 9 organizations. State- and district-level
  NGOs need live web research (LLM mode) or manual curation.
- Retrieval is weak on generic questions like "what are the limitations"
  (a known, tested gap).
