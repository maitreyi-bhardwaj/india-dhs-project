"""Shared test fixtures.

- Tests never call the real Claude API (DISABLE_LLM=1); LLM-mode logic is
  tested with a fake client in test_llm_mode.py.
- `mini_db` builds a tiny SQLite database whose correct answers can be
  worked out by hand, so the SQL logic is tested without the 5 GB dataset.
- Integration tests use the real database and are skipped if it isn't built.
"""

import os
import sqlite3

import pandas as pd
import pytest

os.environ["DISABLE_LLM"] = "1"

from src.analysis import database  # noqa: E402
from src.config import DATABASE_PATH, INDEX_DIR  # noqa: E402

REAL_DATA_READY = DATABASE_PATH.exists() and (INDEX_DIR / "docs" / "dense.npy").exists()
requires_real_data = pytest.mark.skipif(not REAL_DATA_READY, reason="run the pipeline and index build first")


@pytest.fixture
def mini_db(tmp_path, monkeypatch):
    """Six women with known weights:

        woman  state  residence  weight w  phone (v169a)  working
        1      10     rural      1.0       1              1
        2      10     rural      3.0       0              0
        3      10     urban      2.0       1              NULL  (not asked)
        4      9      rural      1.0       NULL           NULL
        5      9      urban      1.0       1              1
        6      9      urban      2.0       0              0

    Weighted % owning a phone among women with an answer, all women:
        numerator = 1 + 2 + 1 = 4 ; denominator = 1 + 3 + 2 + 1 + 2 = 9 -> 44.44%
    """
    path = tmp_path / "mini.sqlite"
    women = pd.DataFrame({
        "caseid": ["1", "2", "3", "4", "5", "6"],
        "v024": [10, 10, 10, 9, 9, 9], "v025": [2, 2, 1, 2, 1, 1],
        "v012": [18, 30, 24, 40, 20, 45], "v013": [1, 4, 2, 6, 2, 7],
        "w": [1.0, 3.0, 2.0, 1.0, 1.0, 2.0],
        "v169a": [1, 0, 1, None, 1, 0],
        "owns_mobile_phone": [1, 0, 1, None, 1, 0],
        "currently_working": [1, 0, None, None, 1, 0],
    })
    connection = sqlite3.connect(path)
    women.to_sql("women", connection, index=False)
    pd.DataFrame([
        {"variable": "v024", "code": 9, "label": "uttar pradesh"}, {"variable": "v024", "code": 10, "label": "bihar"},
        {"variable": "v025", "code": 1, "label": "urban"}, {"variable": "v025", "code": 2, "label": "rural"},
    ]).to_sql("value_labels", connection, index=False)
    pd.DataFrame([{"name": "v024", "label": "state"}, {"name": "v025", "label": "type of place of residence"},
                  {"name": "v012", "label": "respondent's current age"},
                  {"name": "v169a", "label": "owns a mobile telephone"}]).to_sql("variables", connection, index=False)
    connection.commit()
    connection.close()
    monkeypatch.setattr(database, "DATABASE_PATH", path)
    return path
