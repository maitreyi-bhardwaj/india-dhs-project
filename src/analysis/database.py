"""Read-only access to the analysis database.

Why SQLite: it ships with Python (no server to install), handles 724k rows
easily, and lets us express "weighted percentage by group" as one readable
SQL query. The database is a *derived* copy of the Stata file; it is always
opened read-only here, so no analysis can change it.
"""

import sqlite3
from functools import lru_cache

from src.config import DATABASE_PATH
from src.data.variables import DERIVED_BY_NAME, VARIABLES_BY_NAME


class DatabaseMissingError(RuntimeError):
    pass


def current_path():
    """The database in use. Tests replace DATABASE_PATH in this module with a tiny fixture."""
    return DATABASE_PATH


def connect(path=None):
    """Open the database read-only ("mode=ro"): any write raises an error."""
    path = path or current_path()
    if not path.exists():
        raise DatabaseMissingError(
            f"{path} not found. Build it first with: python -m src.data.pipeline")
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    return connection


# Columns a query is allowed to reference. Anything else is rejected, so a
# query can't touch columns we haven't documented.
def allowed_columns():
    return set(VARIABLES_BY_NAME) | set(DERIVED_BY_NAME)


def value_labels():
    """{variable: {code: label}} for every labelled variable in the database."""
    return _value_labels(current_path())


@lru_cache(maxsize=4)
def _value_labels(path):
    with connect(path) as connection:
        rows = connection.execute("SELECT variable, code, label FROM value_labels").fetchall()
    labels = {}
    for row in rows:
        labels.setdefault(row["variable"], {})[int(row["code"])] = row["label"]
    return labels


def variable_info():
    """{variable: {label, stata_type, kind, topic, note}} for the curated variables."""
    return _variable_info(current_path())


@lru_cache(maxsize=4)
def _variable_info(path):
    with connect(path) as connection:
        rows = connection.execute("SELECT * FROM variables").fetchall()
    return {row["name"]: dict(row) for row in rows}


def label_for(variable, code):
    if code is None:
        return None
    try:
        return value_labels().get(variable, {}).get(int(code), str(code))
    except (TypeError, ValueError):   # not a numeric code; show it as given
        return str(code)
