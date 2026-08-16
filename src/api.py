"""
HTTP wrapper around TicketResolutionAgent, for the ZAF sidebar app (assets/main.js)
to call from inside the Zendesk agent workspace. Everything downstream of this file
(retrieval, guardrails, gating) is unchanged from app.py's Streamlit path -- this is
just a second, thin presentation layer over the same agent.

Run with: uvicorn src.api:app --reload --port 8000
"""
from __future__ import annotations

from dataclasses import asdict
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .agent import AgentResult, TicketResolutionAgent
from .config import CONFIG
from .ingest import build_index
from .zendesk_client import Ticket, ZendeskClient

app = FastAPI(title="Northwind Cloud Ticket Resolution API")

# The ZAF app iframe is served by `zcli apps:server` from a different origin
# (localhost:4567 in dev, the Zendesk CDN once uploaded) than this API, so it
# needs CORS. Locked to local dev origins -- widen this only if the app is
# actually deployed somewhere other than zcli's local server.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4567", "https://localhost:4567"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

build_index()
_agent = TicketResolutionAgent()
_zendesk = ZendeskClient()


class ResolveRequest(BaseModel):
    id: int
    subject: str = ""
    description: str = ""
    requester: str = ""
    priority: str = "normal"
    status: str = "open"
    tags: List[str] = []


class ChunkOut(BaseModel):
    kb_id: str
    title: str
    text: str
    similarity: float


class ResolveResponse(BaseModel):
    ticket_id: int
    gate: str
    retrieval_sufficient: bool
    draft_reply: str
    cited_kb_ids: List[str]
    groundedness: float
    unsupported_sentences: List[str]
    retrieved_chunks: List[ChunkOut]
    notes: List[str]
    input_had_secret: bool
    output_had_secret: bool


def _to_response(result: AgentResult) -> ResolveResponse:
    return ResolveResponse(
        ticket_id=result.ticket_id,
        gate=result.gate.value,
        retrieval_sufficient=result.retrieval_sufficient,
        draft_reply=result.draft_reply,
        cited_kb_ids=result.cited_kb_ids,
        groundedness=result.groundedness,
        unsupported_sentences=result.unsupported_sentences,
        retrieved_chunks=[
            ChunkOut(kb_id=c.kb_id, title=c.title, text=c.text, similarity=c.similarity)
            for c in result.retrieved_chunks
        ],
        notes=result.notes,
        input_had_secret=result.input_had_secret,
        output_had_secret=result.output_had_secret,
    )


@app.get("/health")
def health():
    return {
        "status": "ok",
        "llm_provider": CONFIG.llm_provider,
        "embedding_backend": CONFIG.embedding_backend,
        "zendesk_live": _zendesk.is_live,
    }


@app.get("/tickets")
def list_tickets():
    """Debug/CLI convenience -- the ZAF app itself gets ticket data straight
    from client.get('ticket') in the browser, not from this endpoint."""
    return [asdict(t) for t in _zendesk.list_tickets()]


@app.post("/resolve", response_model=ResolveResponse)
def resolve(req: ResolveRequest):
    """Runs the RAG pipeline on ticket data the ZAF app already has from the
    Zendesk agent workspace (client.get('ticket')) -- no Zendesk API round
    trip needed here, so this endpoint carries no Zendesk credentials at all."""
    if not req.subject and not req.description:
        raise HTTPException(400, "Ticket has no subject or description to resolve.")

    ticket = Ticket(
        id=req.id, subject=req.subject, description=req.description,
        requester=req.requester, tags=req.tags, priority=req.priority, status=req.status,
    )
    result = _agent.resolve(ticket)
    return _to_response(result)


class ResolveByIdRequest(BaseModel):
    ticket_id: int


@app.post("/resolve_by_id", response_model=ResolveResponse)
def resolve_by_id(req: ResolveByIdRequest):
    """CLI/curl convenience for testing without a browser: looks the ticket up
    via ZendeskClient (live API or sample data) instead of taking ticket
    fields directly."""
    try:
        ticket = _zendesk.get_ticket(req.ticket_id)
    except KeyError as e:
        raise HTTPException(404, str(e))
    result = _agent.resolve(ticket)
    return _to_response(result)
