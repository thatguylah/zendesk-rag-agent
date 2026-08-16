"""
Central configuration, loaded from environment variables (see .env.example).

Design note: every external dependency (LLM provider, embedding backend, Zendesk
credentials) is read here and nowhere else, so swapping providers is a one-line
env var change rather than a code change anywhere in the pipeline.
"""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    # --- LLM provider ---
    # "ollama" (local, default) | "anthropic" | "mock" (offline/deterministic, for tests & CI)
    llm_provider: str = os.getenv("LLM_PROVIDER", "ollama")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3.2")
    ollama_host: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")

    # --- Embedding / vector store backend ---
    # "sentence-transformers" (default, production) | "tfidf" (offline fallback, no downloads)
    embedding_backend: str = os.getenv("EMBEDDING_BACKEND", "sentence-transformers")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    chroma_persist_dir: str = os.getenv("CHROMA_PERSIST_DIR", ".chroma")

    # --- Zendesk API ---
    zendesk_subdomain: str = os.getenv("ZENDESK_SUBDOMAIN", "")
    zendesk_email: str = os.getenv("ZENDESK_EMAIL", "")
    zendesk_api_token: str = os.getenv("ZENDESK_API_TOKEN", "")
    # If any Zendesk credential is missing, the client transparently falls back
    # to data/sample_tickets.json so the demo always runs, live account or not.
    use_live_zendesk: bool = bool(
        os.getenv("ZENDESK_SUBDOMAIN") and os.getenv("ZENDESK_EMAIL") and os.getenv("ZENDESK_API_TOKEN")
    )

    # --- Retrieval & guardrail thresholds ---
    top_k: int = int(os.getenv("TOP_K", "3"))
    retrieval_confidence_floor: float = float(os.getenv("RETRIEVAL_CONFIDENCE_FLOOR", "0.28"))
    groundedness_auto_suggest: float = float(os.getenv("GROUNDEDNESS_AUTO_SUGGEST", "0.70"))
    groundedness_needs_review: float = float(os.getenv("GROUNDEDNESS_NEEDS_REVIEW", "0.40"))


CONFIG = Config()
