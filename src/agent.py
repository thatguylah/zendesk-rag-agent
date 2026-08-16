"""
Orchestrates one ticket end-to-end: retrieve -> (guardrail) -> generate ->
(guardrail) -> gate decision. This is the file that reads like the actual
"agent" -- everything above it is a building block, everything below
(run_demo.py, app.py) is a presentation layer over this.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .config import CONFIG
from .guardrails import Gate, decide_gate, groundedness_score, redact_secrets
from .llm_providers import LLMProvider, get_llm_provider, parse_citations, strip_citation_line
from .prompts import SYSTEM_PROMPT, build_user_prompt
from .retriever import Retriever, RetrievedChunk
from .zendesk_client import Ticket


@dataclass
class AgentResult:
    ticket_id: int
    retrieved_chunks: List[RetrievedChunk]
    retrieval_sufficient: bool
    raw_llm_response: str
    draft_reply: str
    cited_kb_ids: List[str]
    groundedness: float
    unsupported_sentences: List[str]
    gate: Gate
    input_had_secret: bool = False
    output_had_secret: bool = False
    notes: List[str] = field(default_factory=list)


class TicketResolutionAgent:
    def __init__(self, retriever: Retriever | None = None, llm: LLMProvider | None = None, config=CONFIG):
        self.config = config
        self.retriever = retriever or Retriever(config)
        self.llm = llm or get_llm_provider(config)

    def resolve(self, ticket: Ticket) -> AgentResult:
        notes: List[str] = []

        # Guardrail 0: never let a pasted credential reach the LLM prompt in the
        # first place -- redact before retrieval/generation, not just after.
        # Check the subject too: customers paste secrets into either field.
        safe_subject, subject_had_secret = redact_secrets(ticket.subject)
        safe_description, description_had_secret = redact_secrets(ticket.description)
        input_had_secret = subject_had_secret or description_had_secret
        if input_had_secret:
            notes.append("Customer's message contained what looks like a live credential; "
                         "redacted before processing and before sending to the LLM.")

        # 1. Retrieve
        query = f"{safe_subject}\n{safe_description}"
        chunks = self.retriever.retrieve(query, top_k=self.config.top_k)
        retrieval_sufficient = self.retriever.has_sufficient_grounding(chunks)

        if not retrieval_sufficient:
            notes.append("No KB article cleared the retrieval-confidence floor "
                         f"(top similarity {chunks[0].similarity:.2f} < {self.config.retrieval_confidence_floor} "
                         "-- refusing to generate a draft rather than risk a hallucinated one.")
            return AgentResult(
                ticket_id=ticket.id, retrieved_chunks=chunks, retrieval_sufficient=False,
                raw_llm_response="", draft_reply="", cited_kb_ids=[], groundedness=0.0,
                unsupported_sentences=[], gate=Gate.ESCALATE_NO_KB_MATCH,
                input_had_secret=input_had_secret, notes=notes,
            )

        # 2. Generate (only reachable with sufficient grounding)
        user_prompt = build_user_prompt(safe_subject, safe_description, chunks)
        raw_response = self.llm.generate(SYSTEM_PROMPT, user_prompt)

        cited_ids = parse_citations(raw_response)
        draft = strip_citation_line(raw_response)

        # Guardrail: redact the OUTPUT too, in case the model echoed something
        # from context or hallucinated something that looks like a credential.
        draft, output_had_secret = redact_secrets(draft)
        if output_had_secret:
            notes.append("Draft reply contained something that looked like a credential; redacted.")

        # 3. Score faithfulness independently of the model's own claims
        result = groundedness_score(draft, chunks, self.retriever.embedder)
        gate = decide_gate(retrieval_sufficient, result.score, self.config)

        return AgentResult(
            ticket_id=ticket.id, retrieved_chunks=chunks, retrieval_sufficient=True,
            raw_llm_response=raw_response, draft_reply=draft, cited_kb_ids=cited_ids,
            groundedness=result.score, unsupported_sentences=result.unsupported_sentences,
            gate=gate, input_had_secret=input_had_secret, output_had_secret=output_had_secret,
            notes=notes,
        )
