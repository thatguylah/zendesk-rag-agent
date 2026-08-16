"""
Pluggable embedding backends behind one interface, so the rest of the pipeline
(ingest.py, retriever.py) never knows which one is active.

Two backends:
  - SentenceTransformerEmbedder: production default. Dense semantic embeddings
    (all-MiniLM-L6-v2, 384-dim). Needs a one-time model download from
    Hugging Face on first run.
  - TfidfEmbedder: a fully offline fallback with zero downloads. Used
    automatically by the test suite and in network-restricted environments.
    It is a much weaker retriever (lexical overlap, not semantic similarity)
    -- it exists so the pipeline is provably correct end-to-end even with no
    internet access, not as a production substitute.

This split is itself a guardrail-adjacent design decision worth mentioning in
an interview: a RAG system that silently can't start because a model download
failed is worse than one that degrades to a weaker-but-working retriever.
"""
from __future__ import annotations

import pickle
from pathlib import Path
from typing import List, Protocol


class Embedder(Protocol):
    dim: int

    def embed(self, texts: List[str]) -> List[List[float]]: ...


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer  # lazy import

        self._model = SentenceTransformer(model_name)
        self.dim = self._model.get_sentence_embedding_dimension()

    def embed(self, texts: List[str]) -> List[List[float]]:
        return self._model.encode(list(texts), normalize_embeddings=True).tolist()


class TfidfEmbedder:
    """Offline fallback. Must be fit once on the KB corpus (ingest time), then
    the same fitted vectorizer is reused for queries -- persisted to disk so
    retriever.py doesn't need to re-fit."""

    def __init__(self, persist_path: str):
        self._path = Path(persist_path) / "tfidf_vectorizer.pkl"
        self._vectorizer = None
        self.dim = None
        if self._path.exists():
            with open(self._path, "rb") as f:
                self._vectorizer = pickle.load(f)
            self.dim = len(self._vectorizer.get_feature_names_out())

    def fit(self, corpus: List[str]) -> None:
        from sklearn.feature_extraction.text import TfidfVectorizer

        self._vectorizer = TfidfVectorizer(max_features=2000, stop_words="english")
        self._vectorizer.fit(corpus)
        self.dim = len(self._vectorizer.get_feature_names_out())
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "wb") as f:
            pickle.dump(self._vectorizer, f)

    def embed(self, texts: List[str]) -> List[List[float]]:
        if self._vectorizer is None:
            raise RuntimeError("TfidfEmbedder must be fit() (during ingest) before embed()")
        return self._vectorizer.transform(list(texts)).toarray().tolist()


def get_embedder(config) -> Embedder:
    if config.embedding_backend == "tfidf":
        return TfidfEmbedder(config.chroma_persist_dir)
    if config.embedding_backend == "sentence-transformers":
        return SentenceTransformerEmbedder(config.embedding_model)
    raise ValueError(f"Unknown embedding backend: {config.embedding_backend}")
