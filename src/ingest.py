"""
Loads the KB markdown articles, chunks them, embeds them, and writes them into
a persistent local Chroma vector store.

Chunking strategy: each KB article here is short (one topic each, as is typical
for well-maintained support KBs), so we index at the article level rather than
splitting into paragraphs. For a real Zendesk KB with long articles, you'd add
a sliding-window chunker before this step -- noted in the README as a "next
step for production," not silently pretended-away.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, TypedDict

import chromadb

from .chroma_client import get_chroma_client
from .config import CONFIG
from .embeddings import TfidfEmbedder, get_embedder

KB_DIR = Path(__file__).resolve().parent.parent / "data" / "kb_articles"


class KbArticle(TypedDict):
    id: str
    title: str
    category: str
    text: str


def _parse_article(path: Path) -> KbArticle:
    raw = path.read_text(encoding="utf-8")
    front_matter = {}
    body = raw
    if raw.startswith("---"):
        _, fm_block, body = raw.split("---", 2)
        for line in fm_block.strip().splitlines():
            key, _, val = line.partition(":")
            front_matter[key.strip()] = val.strip()
    return KbArticle(
        id=front_matter.get("id", path.stem),
        title=front_matter.get("title", path.stem),
        category=front_matter.get("category", "General"),
        text=body.strip(),
    )


def load_kb_articles() -> List[KbArticle]:
    return [_parse_article(p) for p in sorted(KB_DIR.glob("*.md"))]


def build_index(config=CONFIG) -> chromadb.Collection:
    """(Re)builds the Chroma collection from the KB articles on disk. Idempotent
    -- safe to call every time the demo starts."""
    articles = load_kb_articles()

    embedder = get_embedder(config)
    if isinstance(embedder, TfidfEmbedder):
        embedder.fit([a["text"] for a in articles])

    client = get_chroma_client(config.chroma_persist_dir)
    client.delete_collection("kb_articles") if _collection_exists(client, "kb_articles") else None
    collection = client.create_collection(name="kb_articles", metadata={"hnsw:space": "cosine"})

    embeddings = embedder.embed([f"{a['title']}\n\n{a['text']}" for a in articles])

    collection.add(
        ids=[a["id"] for a in articles],
        embeddings=embeddings,
        documents=[a["text"] for a in articles],
        metadatas=[{"title": a["title"], "category": a["category"]} for a in articles],
    )
    return collection


def _collection_exists(client: chromadb.ClientAPI, name: str) -> bool:
    return name in [c.name for c in client.list_collections()]


if __name__ == "__main__":
    coll = build_index()
    print(f"Indexed {coll.count()} KB articles into Chroma at {CONFIG.chroma_persist_dir} "
          f"using '{CONFIG.embedding_backend}' embeddings.")
