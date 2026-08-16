#!/usr/bin/env python3
"""
The 2-minute live-demo script: loops over sample (or live) tickets and prints
what the agent would draft, with full guardrail reasoning visible -- this is
what you'd run with a screen share during the interview.

Usage:
    python run_demo.py            # all tickets
    python run_demo.py 1006       # just one ticket, by id
"""
import sys

from src.agent import TicketResolutionAgent
from src.config import CONFIG
from src.guardrails import Gate
from src.ingest import build_index
from src.zendesk_client import ZendeskClient

GATE_LABEL = {
    Gate.AUTO_SUGGEST: "\033[92m● AUTO-SUGGEST\033[0m  (high confidence, ready for agent review)",
    Gate.NEEDS_REVIEW: "\033[93m● NEEDS REVIEW\033[0m  (partially grounded, agent must verify)",
    Gate.ESCALATE_LOW_GROUNDEDNESS: "\033[91m● ESCALATE\033[0m       (had KB context, answer still drifted)",
    Gate.ESCALATE_NO_KB_MATCH: "\033[91m● ESCALATE\033[0m       (no relevant KB article found)",
}


def main():
    print(f"LLM provider:      {CONFIG.llm_provider}")
    print(f"Embedding backend: {CONFIG.embedding_backend}")
    print("Building/refreshing KB vector index...")
    build_index()

    client = ZendeskClient()
    print(f"Zendesk source:    {'LIVE zendesk account' if client.is_live else 'data/sample_tickets.json (no live credentials configured)'}")
    print("=" * 78)

    agent = TicketResolutionAgent()
    tickets = client.list_tickets()

    if len(sys.argv) > 1:
        wanted_id = int(sys.argv[1])
        tickets = [t for t in tickets if t.id == wanted_id]

    for ticket in tickets:
        result = agent.resolve(ticket)

        print(f"\n#{ticket.id}  {ticket.subject}")
        print(f"   \"{ticket.description[:140]}{'...' if len(ticket.description) > 140 else ''}\"")
        print(f"   Retrieved: " + ", ".join(
            f"{c.kb_id} ({c.similarity:.2f})" for c in result.retrieved_chunks
        ) if result.retrieved_chunks else "   Retrieved: (nothing above confidence floor)")
        print(f"   Gate:      {GATE_LABEL[result.gate]}")
        if result.retrieval_sufficient:
            print(f"   Groundedness: {result.groundedness:.0%}  |  Cited: {', '.join(result.cited_kb_ids) or 'none'}")
            print(f"   Draft: {result.draft_reply}")
        for note in result.notes:
            print(f"   \033[96mnote:\033[0m {note}")
        print("-" * 78)


if __name__ == "__main__":
    main()
