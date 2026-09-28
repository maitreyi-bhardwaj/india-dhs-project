"""The SQL tool: weighted percentages, NULL handling, safety checks."""

import sqlite3

import pytest

from src.analysis import queries
from src.analysis.database import connect


def test_weighted_percentage_matches_hand_calculation(mini_db):
    result = queries.weighted_percentage({"indicator": "owns_mobile_phone"})
    row = result.rows[0]
    assert row["n_valid"] == 5                     # woman 4 has no answer
    assert row["weighted_numerator"] == 4.0        # 1 + 2 + 1
    assert row["weighted_denominator"] == 9.0      # excludes woman 4's weight
    assert row["weighted_pct"] is None             # n = 5 < 25 -> suppressed (DHS rule)
    assert row["reliability"] == "suppressed (n<25)"


def test_denominator_excludes_missing_answers(mini_db):
    """The classic bug: SUM(w) over everyone would give 4 / 10 instead of 4 / 9."""
    result = queries.weighted_percentage({"indicator": "owns_mobile_phone"})
    assert result.rows[0]["weighted_denominator"] != 10.0
    assert "CASE WHEN y IS NOT NULL THEN w END" in result.sql


def test_filters_and_grouping(mini_db):
    result = queries.weighted_percentage({"indicator": "currently_working"},
                                         filters=[{"variable": "v024", "op": "=", "value": 9}],
                                         group_by=["v025"])
    by_residence = {r["v025_label"]: r for r in result.rows}
    assert by_residence["urban"]["weighted_numerator"] == 1.0   # woman 5
    assert by_residence["urban"]["weighted_denominator"] == 3.0  # women 5 and 6
    assert by_residence["rural"]["n_valid"] == 0                 # woman 4 not asked
    assert "v024 = ?" in result.sql and result.params == [9]     # value passed as a parameter


def test_variable_and_codes_outcome(mini_db):
    result = queries.weighted_percentage({"variable": "v169a", "codes": [1]})
    assert result.rows[0]["weighted_numerator"] == 4.0


def test_count_respondents(mini_db):
    result = queries.count_respondents([{"variable": "v012", "op": "between", "value": [18, 24]}])
    assert result.rows[0]["n_unweighted"] == 3                   # women 1, 3, 5
    assert result.rows[0]["weighted_pct_of_all_women"] == 40.0   # (1 + 2 + 1) / 10


def test_unknown_column_is_rejected(mini_db):
    with pytest.raises(queries.QueryError):
        queries.weighted_percentage({"indicator": "owns_mobile_phone"},
                                    filters=[{"variable": "v024; DROP TABLE women", "op": "=", "value": 1}])


def test_injection_in_values_is_harmless(mini_db):
    result = queries.count_respondents([{"variable": "v024", "op": "=", "value": "1 OR 1=1"}])
    assert result.rows[0]["n_unweighted"] == 0   # treated as a literal value, not SQL


@pytest.mark.parametrize("sql", ["DELETE FROM women", "SELECT 1; DROP TABLE women", "PRAGMA table_info(women)",
                                 "UPDATE women SET w = 0"])
def test_run_select_blocks_writes(mini_db, sql):
    with pytest.raises(queries.QueryError):
        queries.run_select(sql)


def test_connection_is_read_only(mini_db):
    with connect() as connection, pytest.raises(sqlite3.OperationalError):
        connection.execute("DELETE FROM women")


def test_run_select_returns_rows(mini_db):
    result = queries.run_select("SELECT v024, COUNT(*) AS n FROM women GROUP BY v024 ORDER BY v024")
    assert result.rows == [{"v024": 9, "n": 3}, {"v024": 10, "n": 3}]
