"""Retrieve the chunks most relevant to a question.

Three signals, combined:

1. Exact lookup: if the question names a variable (e.g. "v012"), the codebook
   chunk for that variable is returned first. Exact identifiers are a
   dictionary lookup, not a similarity search, and embeddings are bad at them.
2. Dense (embedding) similarity: finds chunks about the same *topic* even
   with different words ("anemia" vs "hemoglobin level").
3. Sparse (TF-IDF keyword) similarity: rewards chunks sharing rare words.

The two similarity lists are combined with Reciprocal Rank Fusion (RRF):

    score = 1 / (60 + rank in dense list) + 1 / (60 + rank in sparse list)

RRF uses ranks, not raw scores, because the two scores live on different
scales (dense cosines for short codebook entries are much larger than TF-IDF
cosines), so averaging raw scores would let one method silently dominate.
Exact matches are pinned to the top.
"""

import re
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from src.config import INDEX_DIR
from src.rag.embeddings import LSAEmbedder
from src.rag.vector_store import VectorStore

RRF_K = 60   # standard constant from the RRF paper (Cormack et al., 2009)
VARIABLE_PATTERN = re.compile(r"\b([a-z]{1,5}\d{1,4}[a-z]?(?:_\d{1,2})?|caseid|ssmod|sweight|sdist)\b", re.I)


def rank_positions(scores):
    """Rank of every chunk (1 = best) for one list of scores."""
    order = np.argsort(-scores)
    ranks = np.empty_like(order)
    ranks[order] = np.arange(1, len(scores) + 1)
    return ranks


class IndexMissingError(RuntimeError):
    pass


@dataclass
class Retrieved:
    chunk_id: str
    title: str
    source: str
    text: str
    score: float             # RRF score (1.0 for exact matches)
    dense_score: float
    sparse_score: float
    match: str               # "exact variable name" or "similarity"
    metadata: dict

    def citation(self):
        where = self.metadata.get("file", "")
        return f"{self.source}: {self.title}" + (f" ({where})" if where else "")


class Retriever:
    def __init__(self, collection="docs"):
        directory = INDEX_DIR / collection
        if not (directory / "dense.npy").exists():
            raise IndexMissingError(f"Index '{collection}' not found. Build it with: python -m src.rag.index")
        self.collection = collection
        self.store = VectorStore.load(directory)
        self.embedder = LSAEmbedder.load(directory / "embedder.joblib")
        self.by_variable = {}
        for position, chunk in enumerate(self.store.chunks):
            if chunk.source == "codebook":
                for name in chunk.metadata.get("variables", []):
                    self.by_variable.setdefault(name.lower(), position)

    def variables_in(self, text):
        """Variable names mentioned in the text that exist in the codebook."""
        found = []
        for token in VARIABLE_PATTERN.findall(text):
            if token.lower() in self.by_variable and token.lower() not in found:
                found.append(token.lower())
        return found

    def retrieve(self, question, k=5, sources=None):
        dense = self.store.dense_scores(self.embedder.embed([question]))
        sparse = self.store.sparse_scores(self.embedder.sparse([question]))
        dense_rank = rank_positions(dense)
        sparse_rank = rank_positions(sparse)
        combined = 1 / (RRF_K + dense_rank) + 1 / (RRF_K + sparse_rank)

        exact_positions = [self.by_variable[v] for v in self.variables_in(question)]
        ranked = exact_positions + [int(i) for i in combined.argsort()[::-1] if int(i) not in exact_positions]

        results = []
        for position in ranked:
            chunk = self.store.chunks[position]
            if sources and chunk.source not in sources:
                continue
            is_exact = position in exact_positions
            results.append(Retrieved(
                chunk_id=chunk.id, title=chunk.title, source=chunk.source, text=chunk.text,
                score=1.0 if is_exact else round(float(combined[position]), 4),
                dense_score=round(float(dense[position]), 4), sparse_score=round(float(sparse[position]), 4),
                match="exact variable name" if is_exact else "similarity", metadata=chunk.metadata,
            ))
            if len(results) >= k:
                break
        return results


@lru_cache(maxsize=2)
def get_retriever(collection="docs"):
    """Load each index once per process."""
    return Retriever(collection)
