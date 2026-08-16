"""
Top-k retrieval over the KB vector store, plus the "retrieval confidence
floor" guardrail: if nothing retrieved is actually similar to the query, we
say so explicitly rather than handing the LLM weak context and letting it
hallucinate a confident-sounding answer anyway.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .chroma_client import get_chroma_client
from .config import CONFIG
from .embeddings import get_embedder


@dataclass
class RetrievedChunk:
    kb_id: str
    title: str
    text: str
    similarity: float  # 1.0 = identical, 0.0 = unrelated (cosine)


class Retriever:
    def __init__(self, config=CONFIG):
        self.config = config
        self.embedder = get_embedder(config)
        self.client = get_chroma_client(config.chroma_persist_dir)
        self.collection = self.client.get_collection("kb_articles")

    def retrieve(self, query: str, top_k: int | None = None) -> List[RetrievedChunk]:
        top_k = top_k or self.config.top_k
        query_embedding = self.embedder.embed([query])[0]
        results = self.collection.query(query_embeddings=[query_embedding], n_results=top_k)

        chunks: List[RetrievedChunk] = []
        for kb_id, doc, meta, distance in zip(
            results["ids"][0], results["documents"][0], results["metadatas"][0], results["distances"][0]
        ):
            # Chroma with hnsw:space="cosine" returns distance = 1 - cosine_similarity,
            # so similarity is just 1 - distance (verified empirically against sklearn's
            # cosine_similarity on the same vectors -- an earlier version of this divided
            # by 2 as if distance ranged [0, 2], which silently inflated every similarity
            # score and made the retrieval-confidence guardrail far too permissive).
            similarity = max(0.0, 1.0 - distance)
            chunks.append(RetrievedChunk(kb_id=kb_id, title=meta["title"], text=doc, similarity=similarity))
        return chunks

    def has_sufficient_grounding(self, chunks: List[RetrievedChunk]) -> bool:
        """The retrieval-confidence-floor guardrail: refuse to proceed to
        generation at all if the best match isn't actually relevant."""
        if not chunks:
            return False
        return chunks[0].similarity >= self.config.retrieval_confidence_floor
