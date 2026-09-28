"""Turning text into vectors (embeddings).

An embedding is a list of numbers that represents a piece of text, such that
texts about similar things get similar vectors. Retrieval then becomes
"find the stored vectors closest to the question's vector".

This project uses a local, dependency-light embedding model, LSA (latent
semantic analysis):

    1. TF-IDF: represent each text as weighted (lightly stemmed) word counts (a sparse vector with
       one slot per word/phrase in the vocabulary, ~50,000 slots, mostly zeros).
    2. SVD: compress those to 256 dense numbers that capture which words tend
       to appear together (e.g. "anemia" and "hemoglobin").

Why not a neural embedding model? It would need PyTorch (~1-2 GB) or an API
key. LSA runs anywhere in milliseconds and is good enough for a
6,000-chunk codebook. The Embedder interface (fit / embed) is the only thing a
neural model would need to replace.
"""

import re

import joblib
import numpy as np
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
from sklearn.preprocessing import normalize

from src.config import EMBEDDING_DIMENSIONS

TOKEN = re.compile(r"(?u)\b\w+\b")
SUFFIXES = ("ations", "ation", "ings", "ing", "ies", "ied", "age", "ed", "es", "s")


def stem(word):
    """Very light stemming so "covered", "coverage" and "cover" match.
    Tokens containing digits (variable names like v012, b2_01) are left intact."""
    if any(ch.isdigit() for ch in word):
        return word
    for suffix in SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def tokenize(text):
    return [stem(token) for token in TOKEN.findall(text.lower())]


def stemmed_stop_words():
    """English stop words plus their stems (the vectorizer compares stop words
    against already-stemmed tokens, so both forms must be in the list)."""
    words = set()
    for word in ENGLISH_STOP_WORDS:
        while word not in words:
            words.add(word)
            word = stem(word)
    return sorted(words)


class LSAEmbedder:
    def __init__(self, dimensions=EMBEDDING_DIMENSIONS):
        self.dimensions = dimensions
        self.tfidf = TfidfVectorizer(tokenizer=tokenize, token_pattern=None, lowercase=False,
                                     sublinear_tf=True, ngram_range=(1, 2), max_features=50_000,
                                     stop_words=stemmed_stop_words())
        self.svd = None

    def fit(self, texts):
        """Learn the vocabulary and the compression from the corpus itself."""
        sparse = self.tfidf.fit_transform(texts)
        components = min(self.dimensions, sparse.shape[0] - 1, sparse.shape[1] - 1)
        self.svd = TruncatedSVD(n_components=max(components, 1), random_state=0)
        self.svd.fit(sparse)
        return self

    def sparse(self, texts):
        """TF-IDF vectors (L2-normalized), used for keyword-style matching."""
        return self.tfidf.transform(texts)

    def embed(self, texts):
        """Dense embeddings, L2-normalized so that dot product = cosine similarity."""
        dense = self.svd.transform(self.tfidf.transform(texts))
        return normalize(dense).astype(np.float32)

    def save(self, path):
        joblib.dump({"dimensions": self.dimensions, "tfidf": self.tfidf, "svd": self.svd}, path)

    @classmethod
    def load(cls, path):
        state = joblib.load(path)
        embedder = cls(state["dimensions"])
        embedder.tfidf, embedder.svd = state["tfidf"], state["svd"]
        return embedder
