"""Structured data queries: the "SQL tool".

Numbers are never produced by an LLM. They come from SQL queries built here
from a small, validated description of the question:

    outcome  : what we are measuring, e.g. {"indicator": "owns_mobile_phone"}
               or {"variable": "v106", "codes": [0]}
    filters  : who is included, e.g. [{"variable": "v024", "op": "in", "value": [10]}]
    group_by : optional columns to split by, e.g. ["v025"]

Every function returns a QueryResult that carries the exact SQL, its
parameters, the numerator/denominator definitions and the variables used,
so each number can be traced and re-run.
"""

import re
from dataclasses import dataclass, field

from src.analysis.database import allowed_columns, connect, label_for, value_labels
from src.config import FLAG_BELOW, SUPPRESS_BELOW
from src.data.variables import DERIVED_BY_NAME

OPERATORS = {"=": "=", "!=": "!=", ">": ">", ">=": ">=", "<": "<", "<=": "<=", "in": "IN",
             "not in": "NOT IN", "between": "BETWEEN"}


class QueryError(ValueError):
    """Raised when a query description is invalid (unknown column, bad operator...)."""


@dataclass
class QueryResult:
    title: str
    rows: list                      # list of dicts, one per group (or one row if no grouping)
    sql: str
    params: list
    variables: list                 # every column the query touched
    numerator: str = ""
    denominator: str = ""
    method: list = field(default_factory=list)
    population: str = "all women aged 15-49"

    def to_dict(self):
        return {"title": self.title, "rows": self.rows, "sql": self.sql, "params": self.params,
                "variables": self.variables, "numerator": self.numerator,
                "denominator": self.denominator, "method": self.method, "population": self.population}


def sample_flag(n):
    if n < SUPPRESS_BELOW:
        return "suppressed (n<25)"
    if n < FLAG_BELOW:
        return "unreliable (n 25-49)"
    return "ok"


def check_column(name):
    if name not in allowed_columns():
        raise QueryError(f"Unknown or disallowed column: {name!r}")
    return name


# ---------------------------------------------------------------------------
# Building SQL pieces
# ---------------------------------------------------------------------------
def outcome_expression(outcome):
    """SQL expression that is 1 (yes), 0 (no) or NULL (not asked / missing).

    Returns (expression, params, variables used, plain-language description).
    """
    if "indicator" in outcome:
        name = outcome["indicator"]
        if name not in DERIVED_BY_NAME:
            raise QueryError(f"Unknown indicator {name!r}. Known: {sorted(DERIVED_BY_NAME)}")
        info = DERIVED_BY_NAME[name]
        return name, [], [name, *info.sources], f"{info.description} ({info.rule})"
    if "variable" in outcome and "codes" in outcome:
        var = check_column(outcome["variable"])
        codes = [int(c) for c in outcome["codes"]]
        if not codes:
            raise QueryError("outcome.codes must not be empty")
        placeholders = ", ".join("?" for _ in codes)
        labels = ", ".join(str(label_for(var, c)) for c in codes)
        expression = f"CASE WHEN {var} IS NULL THEN NULL WHEN {var} IN ({placeholders}) THEN 1 ELSE 0 END"
        return expression, codes, [var], f"{var} in ({labels})"
    raise QueryError("outcome needs either 'indicator' or 'variable' + 'codes'")


def where_clause(filters):
    """Parameterized WHERE clause. Values are passed as parameters (never
    pasted into the SQL text), which prevents SQL injection."""
    parts, params, variables, descriptions = [], [], [], []
    for f in filters or []:
        var = check_column(f["variable"])
        op = f.get("op", "=").lower()
        if op not in OPERATORS:
            raise QueryError(f"Unsupported operator {op!r}")
        value = f["value"]
        if op in ("in", "not in"):
            values = list(value) if isinstance(value, (list, tuple)) else [value]
            parts.append(f"{var} {OPERATORS[op]} ({', '.join('?' for _ in values)})")
            params += values
            shown = ", ".join(str(label_for(var, v)) for v in values)
        elif op == "between":
            low, high = value
            parts.append(f"{var} BETWEEN ? AND ?")
            params += [low, high]
            shown = f"{low} to {high}"
        else:
            parts.append(f"{var} {OPERATORS[op]} ?")
            params.append(value)
            shown = str(label_for(var, value)) if op in ("=", "!=") else str(value)
        variables.append(var)
        descriptions.append(describe_filter(var, op, shown))
    sql = " AND ".join(parts) if parts else "1 = 1"
    return sql, params, variables, descriptions


def describe_filter(var, op, shown):
    """E.g. 'respondent's current age (v012) from 18 to 24', 'state (v024) is bihar'."""
    from src.analysis.database import variable_info
    info = variable_info().get(var)
    if info:
        label = info["label"]
    elif var in DERIVED_BY_NAME:
        label = DERIVED_BY_NAME[var].description
    else:
        label = var
    words = {"=": "is", "in": "is", "!=": "is not", "not in": "is not", "between": "from", ">": ">", ">=": ">=",
             "<": "<", "<=": "<="}[op]
    return f"{label} ({var}) {words} {shown}"


def describe_population(filters):
    _, _, _, descriptions = where_clause(filters)
    return "women aged 15-49" + (" with " + " and ".join(descriptions) if descriptions else "")


def group_columns(group_by):
    return [check_column(g) for g in (group_by or [])]


def with_labels(row, group_by):
    labelled = {}
    for column in group_by:
        labelled[column] = row[column]
        labelled[f"{column}_label"] = label_for(column, row[column])
    return labelled


# ---------------------------------------------------------------------------
# Public query functions
# ---------------------------------------------------------------------------
def weighted_percentage(outcome, filters=None, group_by=None):
    """Weighted % of women with the outcome, among women with a valid answer.

        % = 100 * SUM(w * outcome) / SUM(w for women whose outcome is not NULL)

    The denominator must exclude NULLs explicitly: SUM(w) alone would count
    women who were never asked the question and give a wrong, much smaller %.
    """
    expression, outcome_params, outcome_vars, outcome_text = outcome_expression(outcome)
    where, where_params, filter_vars, _ = where_clause(filters)
    groups = group_columns(group_by)
    select_groups = "".join(f"{g}, " for g in groups)
    group_sql = f"GROUP BY {', '.join(groups)} ORDER BY {', '.join(groups)}" if groups else ""
    sql = (
        f"SELECT {select_groups}\n"
        f"       COUNT(y) AS n_valid,\n"
        f"       SUM(y) AS n_yes_unweighted,\n"
        f"       SUM(w * y) AS weighted_yes,\n"
        f"       SUM(CASE WHEN y IS NOT NULL THEN w END) AS weighted_valid,  -- denominator: valid answers only\n"
        f"       COUNT(*) AS n_in_population\n"
        f"FROM (SELECT {select_groups}w, {expression} AS y\n"
        f"      FROM women\n"
        f"      WHERE {where})\n"
        f"{group_sql}"
    )
    params = outcome_params + where_params
    with connect() as connection:
        raw_rows = connection.execute(sql, params).fetchall()

    rows = []
    for row in raw_rows:
        n = row["n_valid"] or 0
        flag = sample_flag(n)
        pct = None
        if n and not flag.startswith("suppressed"):
            pct = round(100 * row["weighted_yes"] / row["weighted_valid"], 2)
        rows.append({
            **with_labels(row, groups),
            "n_valid": n,
            "n_yes_unweighted": row["n_yes_unweighted"] or 0,
            "n_in_population": row["n_in_population"],
            "weighted_numerator": round(row["weighted_yes"] or 0, 3),
            "weighted_denominator": round(row["weighted_valid"] or 0, 3),
            "weighted_pct": pct,
            "reliability": flag,
        })
    return QueryResult(
        title=f"Weighted % with: {outcome_text}",
        rows=rows, sql=sql, params=params,
        variables=sorted(set(outcome_vars + filter_vars + groups + ["w (= v005 / 1,000,000)"])),
        numerator=f"sum of weights of women with: {outcome_text}",
        denominator="sum of weights of women in the population with a valid (non-missing) answer",
        method=[
            "Weight each woman by w = v005 / 1,000,000.",
            "Exclude women whose outcome is missing (e.g. not asked) from the denominator.",
            f"Suppress results based on fewer than {SUPPRESS_BELOW} women; flag {SUPPRESS_BELOW}-{FLAG_BELOW - 1}.",
        ],
        population=describe_population(filters),
    )


def count_respondents(filters=None, group_by=None):
    """Unweighted number of respondents, plus their weighted share of all women.

    Because v005 is normalized so that weights average 1, a weighted share is
    the meaningful population figure; the survey does not give absolute
    population counts.
    """
    where, params, filter_vars, _ = where_clause(filters)
    groups = group_columns(group_by)
    select_groups = "".join(f"{g}, " for g in groups)
    group_sql = f"GROUP BY {', '.join(groups)} ORDER BY {', '.join(groups)}" if groups else ""
    sql = (f"SELECT {select_groups}COUNT(*) AS n_unweighted,\n"
           f"       SUM(w) AS weighted_n,\n"
           f"       (SELECT SUM(w) FROM women) AS weighted_total\n"
           f"FROM women\nWHERE {where}\n{group_sql}")
    with connect() as connection:
        raw_rows = connection.execute(sql, params).fetchall()
    rows = [{
        **with_labels(r, groups),
        "n_unweighted": r["n_unweighted"],
        "weighted_pct_of_all_women": round(100 * (r["weighted_n"] or 0) / r["weighted_total"], 2),
    } for r in raw_rows]
    return QueryResult(
        title="Number of respondents", rows=rows, sql=sql, params=params,
        variables=sorted(set(filter_vars + groups + ["w (= v005 / 1,000,000)"])),
        numerator="respondents matching the filters (unweighted count); weighted share uses sum of w",
        denominator="all 724,115 women (for the weighted share)",
        method=["Count rows (one row = one interviewed woman).",
                "Weighted share = sum of w in the group / sum of w for all women."],
        population=describe_population(filters),
    )


# ---------------------------------------------------------------------------
# Raw read-only SQL (for the LLM agent and for learning)
# ---------------------------------------------------------------------------
FORBIDDEN = re.compile(r"\b(insert|update|delete|drop|alter|create|attach|detach|pragma|replace|vacuum)\b", re.I)
MAX_ROWS = 200


def run_select(sql, params=None):
    """Run one read-only SELECT and return at most MAX_ROWS rows.

    Three layers of protection:
      1. the text must be a single SELECT/WITH statement with no write keywords;
      2. the database connection itself is read-only (mode=ro);
      3. only MAX_ROWS rows are returned, so a runaway query can't flood the LLM.
    """
    text = sql.strip().rstrip(";")
    if ";" in text:
        raise QueryError("Only a single statement is allowed.")
    if not re.match(r"^(select|with)\b", text, re.I):
        raise QueryError("Only SELECT (or WITH ... SELECT) queries are allowed.")
    if FORBIDDEN.search(text):
        raise QueryError("Query contains a forbidden keyword.")
    with connect() as connection:
        cursor = connection.execute(text, params or [])
        columns = [c[0] for c in cursor.description]
        rows = [dict(zip(columns, r)) for r in cursor.fetchmany(MAX_ROWS)]
    return QueryResult(title="Custom SQL query", rows=rows, sql=text, params=list(params or []),
                       variables=[c for c in allowed_columns() if re.search(rf"\b{c}\b", text)],
                       method=[f"Read-only query; at most {MAX_ROWS} rows returned."])


def labels_for(variable):
    return value_labels().get(variable, {})
