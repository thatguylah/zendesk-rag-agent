"""
Single shared chromadb.PersistentClient per path, per process.

Chroma's own guidance is to avoid creating multiple PersistentClient instances
against the same path within one process -- a second instance can fail to see
a collection the first one just created/deleted ("Collection [uuid] does not
exist"), because each client caches its own view of the on-disk system db.
ingest.build_index() (writer) and retriever.Retriever (reader) previously each
constructed their own client, which is exactly that failure mode.
"""
from __future__ import annotations

from functools import lru_cache

import chromadb


@lru_cache(maxsize=None)
def get_chroma_client(path: str) -> chromadb.ClientAPI:
    return chromadb.PersistentClient(path=path)
