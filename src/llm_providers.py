"""
LLM provider abstraction. Every provider implements the same generate(system,
user) -> str interface, so agent.py is written once and never branches on
which provider is active -- swapping LLM_PROVIDER in .env is the whole
migration.

  - OllamaProvider:   local, free, default. Talks to a locally running
                       `ollama serve` over its REST API. No API key needed.
  - AnthropicProvider: hosted Claude, for when local quality isn't enough --
                       one env var away, same interface, same guardrails.
  - MockProvider:      deterministic, offline, no model at all. Used by the
                       test suite and by this sandbox environment (which has
                       no route to Ollama or the Anthropic API) to prove the
                       retrieval -> generation -> guardrail pipeline is wired
                       correctly end-to-end without depending on a live model.
"""
from __future__ import annotations

import re
from typing import List, Protocol

import requests

from .config import CONFIG
from .retriever import RetrievedChunk


class LLMProvider(Protocol):
    def generate(self, system_prompt: str, user_prompt: str) -> str: ...


class OllamaProvider:
    def __init__(self, model: str, host: str):
        self.model = model
        self.host = host.rstrip("/")

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        resp = requests.post(
            f"{self.host}/api/chat",
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
                "options": {"temperature": 0.2},
            },
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]


class AnthropicProvider:
    def __init__(self, model: str, api_key: str):
        import anthropic  # lazy import so it's not a hard dependency for the ollama/mock paths

        self._client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=400,
            temperature=0.2,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return "".join(block.text for block in resp.content if block.type == "text")


class MockProvider:
    """Deterministic, extractive 'generator' -- no model weights, no network.

    It builds an answer directly from the retrieved chunks (or refuses, per
    the same rule real providers are instructed to follow, when no chunks
    clear the retrieval-confidence floor). This exists to validate the
    pipeline's wiring and guardrail logic in environments with no route to a
    real LLM -- it is explicitly NOT a stand-in for real model quality, and
    the README is upfront about that distinction.
    """

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        context_match = re.search(r"KB CONTEXT:\n(.*?)\n\n---", user_prompt, re.S)
        context = context_match.group(1).strip() if context_match else ""

        if not context or "no relevant KB articles" in context:
            return (
                "I don't have enough information in the knowledge base to answer this confidently. "
                "This looks like it needs a human agent to investigate further.\n"
                "CITED_ARTICLES: NONE"
            )

        ids = re.findall(r"\[(kb_\d+)\]", context)
        first_id = ids[0] if ids else "kb_000"
        # Pull the first two sentences of the top article as an extractive summary.
        first_article_text = context.split("\n", 1)[1].split("\n\n")[0] if "\n" in context else context
        sentences = re.split(r"(?<=[.!?])\s+", first_article_text.strip())
        summary = " ".join(sentences[:2])

        secret_pattern = re.compile(r"sk_live_[A-Za-z0-9]+|password\s*[:=]\s*\S+", re.I)
        summary = secret_pattern.sub("[redacted credential]", summary)

        return (
            f"Thanks for reaching out. {summary} Let us know if that resolves it or if you need "
            f"anything else.\nCITED_ARTICLES: {', '.join(dict.fromkeys(ids))}"
        )


def get_llm_provider(config=CONFIG) -> LLMProvider:
    if config.llm_provider == "ollama":
        return OllamaProvider(config.ollama_model, config.ollama_host)
    if config.llm_provider == "anthropic":
        return AnthropicProvider(config.anthropic_model, config.anthropic_api_key)
    if config.llm_provider == "mock":
        return MockProvider()
    raise ValueError(f"Unknown LLM_PROVIDER: {config.llm_provider}")


def parse_citations(raw_response: str) -> List[str]:
    match = re.search(r"CITED_ARTICLES:\s*(.+)", raw_response)
    if not match:
        return []
    ids = [x.strip() for x in match.group(1).split(",")]
    return [i for i in ids if i and i.upper() != "NONE"]


def strip_citation_line(raw_response: str) -> str:
    return re.sub(r"\n?CITED_ARTICLES:.*", "", raw_response).strip()
