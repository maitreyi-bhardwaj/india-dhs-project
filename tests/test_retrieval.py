"""RAG retrieval quality on the real documentation index."""

import pytest

from tests.conftest import requires_real_data

pytestmark = [pytest.mark.integration, requires_real_data]


@pytest.fixture(scope="module")
def retriever():
    from src.rag.retriever import get_retriever
    return get_retriever("docs")


def titles(retriever, question, k=3):
    return [r.title for r in retriever.retrieve(question, k=k)]


def test_exact_variable_lookup(retriever):
    top = retriever.retrieve("What does v012 mean?", k=1)[0]
    assert top.match == "exact variable name"
    assert "respondent's current age" in top.text


@pytest.mark.parametrize("question, expected", [
    ("Which variable measures anemia or hemoglobin?", "v457: anemia level"),
    ("contact with ASHA or anganwadi worker", "s361:"),
    ("health insurance coverage", "v481: covered by health insurance"),
    ("caste or tribe", "s116:"),
    ("how are sampling weights used", "Sampling weights"),
    ("what does underserved mean in this project", "underserved"),
    ("number of children ever born", "v201:"),
    ("wealth quintile variable", "v190"),
])
def test_relevant_chunk_in_top_3(retriever, question, expected):
    assert any(expected in t for t in titles(retriever, question)), titles(retriever, question)


@pytest.mark.xfail(reason="Known weakness: generic words ('analysis') dilute the 'Limitations' headings.")
def test_limitations_question(retriever):
    assert any("Limitations" in t for t in titles(retriever, "what are the limitations of the analysis"))


def test_repeated_slots_are_merged(retriever):
    """b2_01 ... b2_20 (one per child) are one chunk, not 20."""
    ids = [c.id for c in retriever.store.chunks if c.id.startswith("codebook:b2_")]
    assert len(ids) == 1
