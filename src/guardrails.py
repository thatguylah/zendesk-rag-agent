"""
Guardrails: the part of a RAG system that decides whether to trust its own
output. Three independent checks, deliberately kept separate so each can be
explained and tuned on its own:

  1. retrieval confidence  -- did we find anything relevant at all?
     (retriever.Retriever.has_sufficient_grounding, checked BEFORE generation)
  2. secret/PII redaction  -- never echo a credential back, in or out
  3. groundedness / faithfulness -- does the generated answer's content
     actually trace back to the retrieved context, sentence by sentence?

Faithfulness is computed programmatically via embedding similarity against
the retrieved chunks, NOT by asking the LLM to self-report confidence.
Research and practice both show LLM self-reported confidence is poorly
calibrated -- a model that hallucinates is often just as "confident" as one
that doesn't. An independent, external check is the whole point of a
guardrail: it has to not trust the thing it's checking.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import List

import numpy as np

from .config import CONFIG
from .embeddings import Embedder
from .retriever import RetrievedChunk

# --- 1. Secret / credential redaction --------------------------------------

_SECRET_PATTERNS = [
    re.compile(r"sk_live_[A-Za-z0-9]{10,}", re.I),           # API-style live tokens
    re.compile(r"sk_test_[A-Za-z0-9]{10,}", re.I),
    re.compile(r"\b(?:\d[ -]*?){13,19}\b"),                    # credit-card-like digit runs
    re.compile(r"password\s*[:=]\s*\S+", re.I),
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),                      # SSN-like
]


def redact_secrets(text: str) -> tuple[str, bool]:
    """Returns (redacted_text, was_anything_redacted)."""
    redacted = text
    found = False
    for pattern in _SECRET_PATTERNS:
        if pattern.search(redacted):
            found = True
            redacted = pattern.sub("[redacted credential]", redacted)
    return redacted, found


# --- 2. Groundedness / faithfulness -----------------------------------------

def _cosine(a: List[float], b: List[float]) -> float:
    a, b = np.array(a), np.array(b)
    denom = (np.linalg.norm(a) * np.linalg.norm(b)) or 1e-9
    return float(np.dot(a, b) / denom)


# Conversational boilerplate (greetings, sign-offs) carries no factual claim,
# so it shouldn't be graded against KB context -- doing so just adds noise
# that makes correct, fully-grounded answers look artificially unfaithful.
# Anchored to the START of the sentence deliberately: a sentence like "X enforces
# rate limits: let us know if that helps" has real content before the closer, so
# it must NOT be discarded wholesale just because a closing phrase appears in it
# somewhere -- only sentences that ARE (start as) pure boilerplate are dropped.
_BOILERPLATE_PATTERNS = [
    re.compile(r"^(hi|hello|hey|thanks?( you)?)\b", re.I),
    re.compile(r"^(let (us|me) know|feel free|please (let|reach)|happy to help|reach out)\b", re.I),
]


def _is_boilerplate(sentence: str) -> bool:
    return any(p.match(sentence.strip()) for p in _BOILERPLATE_PATTERNS)


def _split_sentences(text: str) -> List[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return [s for s in sentences if len(s.split()) >= 3 and not _is_boilerplate(s)]


@dataclass
class GroundednessResult:
    score: float                 # fraction of answer sentences supported by retrieved context, 0-1
    unsupported_sentences: List[str]


def groundedness_score(
    answer_text: str,
    chunks: List[RetrievedChunk],
    embedder: Embedder,
    sentence_threshold: float = 0.32,
) -> GroundednessResult:
    sentences = _split_sentences(answer_text)
    if not sentences:
        return GroundednessResult(score=0.0, unsupported_sentences=[])
    if not chunks:
        return GroundednessResult(score=0.0, unsupported_sentences=sentences)

    chunk_embeddings = embedder.embed([c.text for c in chunks])
    sentence_embeddings = embedder.embed(sentences)

    unsupported = []
    supported_count = 0
    for sentence, s_emb in zip(sentences, sentence_embeddings):
        best = max(_cosine(s_emb, c_emb) for c_emb in chunk_embeddings)
        if best >= sentence_threshold:
            supported_count += 1
        else:
            unsupported.append(sentence)

    return GroundednessResult(score=supported_count / len(sentences), unsupported_sentences=unsupported)


# --- 3. The gate: turn checks into a routing decision -----------------------

class Gate(str, Enum):
    AUTO_SUGGEST = "AUTO_SUGGEST"                    # ready for agent to review & send
    NEEDS_REVIEW = "NEEDS_REVIEW"                     # partially grounded, agent must verify
    ESCALATE_LOW_GROUNDEDNESS = "ESCALATE_LOW_GROUNDEDNESS"  # had context, answer still drifted
    ESCALATE_NO_KB_MATCH = "ESCALATE_NO_KB_MATCH"      # retrieval never cleared the confidence floor


def decide_gate(retrieval_sufficient: bool, groundedness: float, config=CONFIG) -> Gate:
    if not retrieval_sufficient:
        return Gate.ESCALATE_NO_KB_MATCH
    if groundedness >= config.groundedness_auto_suggest:
        return Gate.AUTO_SUGGEST
    if groundedness >= config.groundedness_needs_review:
        return Gate.NEEDS_REVIEW
    return Gate.ESCALATE_LOW_GROUNDEDNESS
