"""A minimal vector store: vectors in a NumPy array, chunks in a JSON-lines file.

A "vector database" does three things: store vectors with their text and
metadata, persist them to disk, and find the nearest vectors to a query.
Products like Chroma, pgvector, Pinecone or FAISS add scale (millions of
vectors), approximate search, filtering and concurrency. For ~6,000 chunks, a
brute-force NumPy dot product takes about a millisecond, and every step is
visible in ~50 lines.
"""

import json

import numpy as np
from scipy import sparse as sp

from src.rag.documents import Chunk


class VectorStore:
    def __init__(self, chunks, dense_vectors, sparse_vectors):
        self.chunks = chunks
        self.dense = dense_vectors        # shape (n_chunks, dimensions), rows normalized
        self.sparse = sparse_vectors      # TF-IDF matrix, rows normalized

    # --- persistence -------------------------------------------------------
    def save(self, directory):
        directory.mkdir(parents=True, exist_ok=True)
        np.save(directory / "dense.npy", self.dense)
        sp.save_npz(directory / "sparse.npz", self.sparse.tocsr())
        with open(directory / "chunks.jsonl", "w") as f:
            for chunk in self.chunks:
                f.write(json.dumps(chunk.to_dict()) + "\n")

    @classmethod
    def load(cls, directory):
        with open(directory / "chunks.jsonl") as f:
            chunks = [Chunk(**json.loads(line)) for line in f]
        return cls(chunks, np.load(directory / "dense.npy"), sp.load_npz(directory / "sparse.npz"))

    # --- search ------------------------------------------------------------
    def dense_scores(self, query_vector):
        """Cosine similarity of the query with every chunk (vectors are normalized)."""
        return self.dense @ query_vector.ravel()

    def sparse_scores(self, query_sparse):
        return np.asarray((self.sparse @ query_sparse.T).todense()).ravel()

    def __len__(self):
        return len(self.chunks)
