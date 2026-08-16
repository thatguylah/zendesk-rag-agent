"""
Real Zendesk Ticketing API client, with a transparent fallback to local sample
data when no credentials are configured -- so this repo runs standalone, and
points at a live Zendesk instance the moment ZENDESK_SUBDOMAIN / ZENDESK_EMAIL
/ ZENDESK_API_TOKEN are set in .env.

API reference: https://developer.zendesk.com/api-reference/ticketing/tickets/tickets/
Auth: HTTP Basic with "{email}/token" as the username and the API token as the
password (Zendesk's documented token-auth scheme).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import requests

from .config import CONFIG

SAMPLE_TICKETS_PATH = Path(__file__).resolve().parent.parent / "data" / "sample_tickets.json"


@dataclass
class Ticket:
    id: int
    subject: str
    description: str
    requester: str
    tags: List[str]
    priority: str
    status: str

    @property
    def full_text(self) -> str:
        return f"{self.subject}\n\n{self.description}"


class ZendeskClient:
    def __init__(self, config=CONFIG):
        self.config = config
        self._session: Optional[requests.Session] = None
        if config.use_live_zendesk:
            self._session = requests.Session()
            self._session.auth = (f"{config.zendesk_email}/token", config.zendesk_api_token)
            self._base_url = f"https://{config.zendesk_subdomain}.zendesk.com/api/v2"

    @property
    def is_live(self) -> bool:
        return self._session is not None

    def list_tickets(self, status: str = "open") -> List[Ticket]:
        if self._session is None:
            return self._load_sample_tickets()

        resp = self._session.get(f"{self._base_url}/tickets.json", params={"per_page": 25})
        resp.raise_for_status()
        payload = resp.json()
        return [
            Ticket(
                id=t["id"],
                subject=t.get("subject") or "",
                description=t.get("description") or "",
                requester=str(t.get("requester_id", "")),
                tags=t.get("tags", []),
                priority=t.get("priority") or "normal",
                status=t.get("status") or "open",
            )
            for t in payload.get("tickets", [])
            if status is None or t.get("status") == status
        ]

    def get_ticket(self, ticket_id: int) -> Ticket:
        if self._session is None:
            for t in self._load_sample_tickets():
                if t.id == ticket_id:
                    return t
            raise KeyError(f"No sample ticket with id {ticket_id}")

        resp = self._session.get(f"{self._base_url}/tickets/{ticket_id}.json")
        resp.raise_for_status()
        t = resp.json()["ticket"]
        return Ticket(
            id=t["id"], subject=t.get("subject") or "", description=t.get("description") or "",
            requester=str(t.get("requester_id", "")), tags=t.get("tags", []),
            priority=t.get("priority") or "normal", status=t.get("status") or "open",
        )

    def post_internal_note(self, ticket_id: int, body: str) -> None:
        """Adds the agent's draft as a private internal note (never a public
        reply) -- the agent always leaves a human to hit send. See guardrails.py
        and the README's 'human in the loop' section for why."""
        if self._session is None:
            print(f"[MOCK] Would post internal note to ticket {ticket_id}:\n{body}\n")
            return
        resp = self._session.put(
            f"{self._base_url}/tickets/{ticket_id}.json",
            json={"ticket": {"comment": {"body": body, "public": False}}},
        )
        resp.raise_for_status()

    @staticmethod
    def _load_sample_tickets() -> List[Ticket]:
        raw = json.loads(SAMPLE_TICKETS_PATH.read_text(encoding="utf-8"))
        return [Ticket(**t) for t in raw]
