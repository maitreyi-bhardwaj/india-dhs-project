"""Build the retrieval indexes (run after the documents change).

    python -m src.rag.index

Creates two collections under data/index/:
    docs      - codebook + data dictionary + methodology + research notes
    outreach  - the curated outreach organizations
Each collection gets its own embedder, fitted on that collection's text.
"""

import time

from src.config import INDEX_DIR
from src.rag.documents import documentation_chunks, outreach_chunks
from src.rag.embeddings import LSAEmbedder
from src.rag.vector_store import VectorStore

COLLECTIONS = {"docs": documentation_chunks, "outreach": outreach_chunks}


def text_to_embed(chunk):
    """Title boosting: a chunk's title (variable label or section heading)
    carries most of its meaning, so it is repeated before the body text."""
    return f"{chunk.title}. {chunk.title}. {chunk.text}"


def build_collection(name):
    chunks = COLLECTIONS[name]()
    texts = [text_to_embed(c) for c in chunks]
    embedder = LSAEmbedder().fit(texts)                    # 1. learn the embedding model
    store = VectorStore(chunks, embedder.embed(texts),     # 2. embed every chunk
                        embedder.sparse(texts))
    directory = INDEX_DIR / name
    store.save(directory)                                  # 3. store vectors + chunks
    embedder.save(directory / "embedder.joblib")
    return len(chunks), embedder.svd.n_components


def main():
    for name in COLLECTIONS:
        start = time.time()
        count, dims = build_collection(name)
        print(f"  {name}: {count:,} chunks, {dims}-dimensional embeddings, {time.time() - start:.1f}s")


if __name__ == "__main__":
    main()
