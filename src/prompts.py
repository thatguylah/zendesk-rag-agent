"""
Prompt engineering lives here, in one place, versioned like code -- not
scattered as f-strings through the codebase.

Design decisions worth being able to explain out loud:
  1. The system prompt explicitly forbids answering from general knowledge --
     only from the retrieved KB context. This is the single highest-leverage
     line against hallucination.
  2. The model is required to emit a machine-parseable citation line. We do
     NOT ask the model to self-report a confidence score -- LLMs are known to
     be poorly calibrated about their own uncertainty, so guardrails.py
     computes groundedness independently instead of trusting the model's word
     for it.
  3. The prompt gives the model an explicit, named escape hatch ("insufficient
     information") so refusing is a first-class, easy output rather than
     something it has to fight the instruction-tuning to do.
"""
from __future__ import annotations

from typing import List

from .retriever import RetrievedChunk

SYSTEM_PROMPT = """You are a support-ticket drafting assistant for Northwind Cloud, a project \
management SaaS product. You draft an internal-note reply for a human support agent to review \
-- you never send anything to the customer directly.

Rules, in priority order:
1. Answer ONLY using the "KB CONTEXT" provided below. Do not use outside/general knowledge about \
   Northwind Cloud or any other product, even if you believe you know the answer.
2. If the KB CONTEXT does not contain enough information to answer the ticket, say exactly: \
   "I don't have enough information in the knowledge base to answer this confidently," and \
   suggest what information or article is missing. Do not guess.
3. Never include a password, API token, secret key, or credit card number in your draft, even if \
   the customer included one in their ticket. If the customer pasted a credential, tell the human \
   agent to advise the customer to rotate it -- do not repeat the credential back.
4. Be concise: 2-5 sentences, written for a customer to eventually read, professional and warm.
5. End your response with one line in exactly this format, listing the KB article ids you actually \
   drew from (or NONE): CITED_ARTICLES: kb_001, kb_003
"""


def build_user_prompt(ticket_subject: str, ticket_description: str, chunks: List[RetrievedChunk]) -> str:
    if chunks:
        context_block = "\n\n".join(
            f"[{c.kb_id}] {c.title}\n{c.text}" for c in chunks
        )
    else:
        context_block = "(no relevant KB articles were retrieved)"

    return f"""KB CONTEXT:
{context_block}

---

CUSTOMER TICKET:
Subject: {ticket_subject}
Description: {ticket_description}

Draft the internal-note reply now, following all rules in the system prompt."""
