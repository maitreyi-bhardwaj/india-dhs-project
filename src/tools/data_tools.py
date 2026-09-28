"""Tools used by the Data Agent.

    Tool 1  Documentation RAG   search_documentation, lookup_variable
    Tool 2  SQL / data query    weighted_percentage, count_respondents, run_sql
    Tool 3  Python analysis     rank_underserved_groups, age_standardized_rates, channel_reach

Each function takes the Trace first, records what it did (variables,
definitions, SQL, retrieved chunks), and returns a compact JSON-able summary.
"""

from src.analysis import queries, stats
from src.analysis.database import variable_info
from src.data.variables import DEFAULT_UNDERSERVED_INDICATORS, DERIVED, GROUPING_COLUMNS
from src.rag.retriever import get_retriever
from src.tools.registry import Tool

MAX_ROWS_TO_LLM = 40


def record_query(trace, result, chart=None):
    trace.add_variables_from(result.variables, variable_info())
    trace.add_calculation(result.to_dict(), chart)


def compact_rows(rows, limit=MAX_ROWS_TO_LLM):
    return rows[:limit] + ([{"note": f"{len(rows) - limit} more rows omitted"}] if len(rows) > limit else [])


# ---------------------------------------------------------------------------
# Tool 1: documentation RAG
# ---------------------------------------------------------------------------
def search_documentation(trace, query, k=5):
    results = get_retriever("docs").retrieve(query, k=int(k))
    for r in results:
        trace.add_document(r)
        for name in r.metadata.get("variables", [])[:1]:
            if r.source == "codebook":
                trace.add_variable(name, r.metadata.get("label", ""), "codebook (Stata file metadata)")
    return {"results": [{"id": r.chunk_id, "source": r.source, "title": r.title, "match": r.match,
                         "score": r.score, "text": r.text[:1500]} for r in results]}


def lookup_variable(trace, name):
    """Exact definition of one variable: codebook entry (+ data dictionary if curated)."""
    retriever = get_retriever("docs")
    name = name.lower().strip()
    if name not in retriever.by_variable:
        return {"found": False, "message": f"{name!r} is not a variable in the codebook."}
    chunk = retriever.store.chunks[retriever.by_variable[name]]
    extra = [c for c in retriever.store.chunks
             if c.source == "data dictionary" and c.metadata.get("heading", "").split(":")[0] == name]
    for c in [chunk] + extra:
        trace.add_document(_as_retrieved(c))
    trace.add_variable(name, chunk.metadata.get("label", ""), "codebook (Stata file metadata)")
    return {"found": True, "variable": name, "codebook": chunk.text,
            "data_dictionary": extra[0].text if extra else "(not in the curated analysis database)"}


def _as_retrieved(chunk):
    from src.rag.retriever import Retrieved
    return Retrieved(chunk.id, chunk.title, chunk.source, chunk.text, 1.0, 0.0, 0.0,
                     "exact variable name", chunk.metadata)


# ---------------------------------------------------------------------------
# Tool 2: SQL / data queries
# ---------------------------------------------------------------------------
def weighted_percentage(trace, outcome, filters=None, group_by=None):
    result = queries.weighted_percentage(outcome, filters, group_by)
    chart = {"x": f"{group_by[0]}_label", "y": "weighted_pct"} if group_by else None
    record_query(trace, result, chart)
    return {"title": result.title, "population": result.population, "rows": compact_rows(result.rows),
            "sql": result.sql, "params": result.params}


def count_respondents(trace, filters=None, group_by=None):
    result = queries.count_respondents(filters, group_by)
    record_query(trace, result)
    return {"population": result.population, "rows": compact_rows(result.rows), "sql": result.sql,
            "params": result.params}


def run_sql(trace, query):
    result = queries.run_select(query)
    record_query(trace, result)
    return {"rows": compact_rows(result.rows), "sql": result.sql}


# ---------------------------------------------------------------------------
# Tool 3: Python analysis
# ---------------------------------------------------------------------------
def record_analysis(trace, result, chart=None):
    trace.add_variables_from(result.variables, variable_info())
    for q in result.queries:
        trace.add_variables_from(q["variables"], variable_info())
    trace.add_calculation(result.to_dict(), chart)


def rank_underserved_groups(trace, group_by=("v024", "v025"), indicators=None, filters=None,
                            min_n=200, top_k=10):
    result = stats.rank_underserved_groups(tuple(group_by), indicators, filters, int(min_n), int(top_k))
    record_analysis(trace, result, {"x": "group", "y": "deprivation_score"})
    return {"title": result.title, "rows": compact_rows(result.rows, limit=max(MAX_ROWS_TO_LLM, int(top_k))),
            "method": result.method, "notes": result.notes, **result.summary}


def age_standardized_rates(trace, outcome, group_by, filters=None):
    result = stats.age_standardized_rates(outcome, group_by, filters)
    record_analysis(trace, result, {"x": "group", "y": "age_standardized_pct"})
    return {"title": result.title, "rows": compact_rows(result.rows), "method": result.method}


def channel_reach(trace, filters=None):
    result = stats.channel_reach(filters)
    record_analysis(trace, result, {"x": "description", "y": "weighted_pct"})
    return {"population": queries.describe_population(filters), "rows": result.rows, "notes": result.notes}


# ---------------------------------------------------------------------------
# JSON schemas (what the LLM sees)
# ---------------------------------------------------------------------------
INDICATOR_NAMES = [d.name for d in DERIVED]
OUTCOME_SCHEMA = {
    "type": "object",
    "description": "What to measure: either a derived indicator name, or a variable plus the codes that count as 'yes'.",
    "properties": {
        "indicator": {"type": "string", "enum": INDICATOR_NAMES},
        "variable": {"type": "string"},
        "codes": {"type": "array", "items": {"type": "integer"}},
    },
}
FILTERS_SCHEMA = {
    "type": "array",
    "description": "Who is included. Example: [{\"variable\": \"v024\", \"op\": \"=\", \"value\": 10}, "
                   "{\"variable\": \"v012\", \"op\": \"between\", \"value\": [18, 24]}]. Use numeric codes.",
    "items": {"type": "object", "properties": {
        "variable": {"type": "string"},
        "op": {"type": "string", "enum": list(queries.OPERATORS)},
        "value": {"description": "a number, or a list of numbers for 'in' / 'between'"},
    }, "required": ["variable", "op", "value"]},
}
GROUP_BY_SCHEMA = {"type": "array", "items": {"type": "string"},
                   "description": f"Columns to split by, e.g. {sorted(GROUPING_COLUMNS.values())}"}

DATA_TOOLS = [
    Tool("search_documentation",
         "Search the codebook, data dictionary, methodology notes and research notes. Use for questions "
         "about what variables mean, which variables are relevant to a topic, how things were measured, "
         "and limitations. Returns text chunks with ids to cite.",
         {"type": "object", "properties": {"query": {"type": "string"}, "k": {"type": "integer"}},
          "required": ["query"]},
         search_documentation, "Data Agent"),
    Tool("lookup_variable",
         "Exact codebook definition and value labels of one variable by name (e.g. 'v012').",
         {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
         lookup_variable, "Data Agent"),
    Tool("weighted_percentage",
         "Weighted percentage of women with an outcome, optionally filtered and grouped. Always use this "
         "(never mental arithmetic) for any percentage. Returns unweighted n, weighted numerator and "
         "denominator, reliability flags, and the SQL used.",
         {"type": "object", "properties": {"outcome": OUTCOME_SCHEMA, "filters": FILTERS_SCHEMA,
                                           "group_by": GROUP_BY_SCHEMA}, "required": ["outcome"]},
         weighted_percentage, "Data Agent"),
    Tool("count_respondents",
         "Number of respondents (unweighted) matching filters, and their weighted share of all women.",
         {"type": "object", "properties": {"filters": FILTERS_SCHEMA, "group_by": GROUP_BY_SCHEMA}},
         count_respondents, "Data Agent"),
    Tool("run_sql",
         "Run one read-only SELECT on the SQLite table 'women' (one row per woman; weight column 'w'; "
         "value labels in table 'value_labels(variable, code, label)'). Remember: weighted % denominators "
         "must exclude NULLs: SUM(CASE WHEN x IS NOT NULL THEN w END). Prefer weighted_percentage.",
         {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
         run_sql, "Data Agent"),
    Tool("rank_underserved_groups",
         "Rank population groups by a transparent deprivation score (average weighted % lacking "
         f"education, literacy, media exposure, health insurance and frontline-worker contact by default: "
         f"{DEFAULT_UNDERSERVED_INDICATORS}). Groups below min_n women are not ranked.",
         {"type": "object", "properties": {
             "group_by": GROUP_BY_SCHEMA,
             "indicators": {"type": "array", "items": {"type": "string", "enum": [
                 d.name for d in DERIVED if d.kind == "deprivation"]}},
             "filters": FILTERS_SCHEMA, "min_n": {"type": "integer"}, "top_k": {"type": "integer"}}},
         rank_underserved_groups, "Data Agent"),
    Tool("age_standardized_rates",
         "Crude and age-standardized weighted % of an outcome by group, to check whether differences "
         "between groups are explained by their age mix.",
         {"type": "object", "properties": {"outcome": OUTCOME_SCHEMA, "group_by": GROUP_BY_SCHEMA,
                                           "filters": FILTERS_SCHEMA}, "required": ["outcome", "group_by"]},
         age_standardized_rates, "Data Agent"),
    Tool("channel_reach",
         "For a population (filters), the weighted % reached by each communication channel in the data: "
         "newspaper, radio, TV, mobile phone, internet, frontline health workers, bank accounts.",
         {"type": "object", "properties": {"filters": FILTERS_SCHEMA}},
         channel_reach, "Data Agent"),
]
DATA_TOOLS_BY_NAME = {t.name: t for t in DATA_TOOLS}
