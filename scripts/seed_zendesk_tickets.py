#!/usr/bin/env python3
"""
Seeds data/sample_tickets.json into the live Zendesk sandbox as real tickets,
so the ZAF sidebar app has tickets that actually match the Northwind Cloud KB
to demo against, instead of whatever unrelated tickets the trial account
seeded by default.

Idempotent: every created ticket is tagged SEED_TAG and given
external_id = str(sample_ticket["id"]); reruns detect existing seeded tickets
via search and skip creation rather than duplicating them.

Usage:
    source .oauth-token.env   # ZENDESK_SUBDOMAIN / ZENDESK_OAUTH_TOKEN
    python scripts/seed_zendesk_tickets.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_TICKETS = json.loads((ROOT / "data" / "sample_tickets.json").read_text(encoding="utf-8"))
SEED_TAG = "northwind-demo-seed"


def display_name(email: str) -> str:
    local = email.split("@")[0]
    return local.replace(".", " ").replace("_", " ").replace("-", " ").title()


def main() -> None:
    subdomain = os.environ.get("ZENDESK_SUBDOMAIN", "ibm-38381")
    token = os.environ.get("ZENDESK_OAUTH_TOKEN")
    if not token:
        print("Missing ZENDESK_OAUTH_TOKEN -- run `source .oauth-token.env` first "
              "(or ./scripts/get_zendesk_oauth_token.sh if it's stale).", file=sys.stderr)
        sys.exit(1)

    base = f"https://{subdomain}.zendesk.com/api/v2"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    resp = requests.get(f"{base}/search.json", headers=headers,
                         params={"query": f"type:ticket tags:{SEED_TAG}"})
    resp.raise_for_status()
    existing = resp.json()["results"]
    if existing:
        print(f"Found {len(existing)} ticket(s) already tagged '{SEED_TAG}' -- skipping creation "
              "(delete them in Zendesk first if you want to reseed):")
        for t in existing:
            print(f"  #{t['id']}  {t['subject']}")
        return

    tickets_payload = [
        {
            "subject": t["subject"],
            "comment": {"body": t["description"]},
            "requester": {"name": display_name(t["requester"]), "email": t["requester"]},
            "priority": t["priority"],
            "tags": t["tags"] + [SEED_TAG],
            "external_id": str(t["id"]),
        }
        for t in SAMPLE_TICKETS
    ]

    resp = requests.post(f"{base}/tickets/create_many.json", headers=headers,
                          json={"tickets": tickets_payload})
    resp.raise_for_status()
    job_id = resp.json()["job_status"]["id"]
    print(f"Submitted create_many job {job_id}, polling for completion...")

    status_url = f"{base}/job_statuses/{job_id}.json"
    job_status = None
    for _ in range(30):
        time.sleep(1)
        job_status = requests.get(status_url, headers=headers).json()["job_status"]
        if job_status["status"] in ("completed", "failed", "killed"):
            break

    if job_status is None or job_status["status"] != "completed":
        print(f"Job did not complete cleanly: {json.dumps(job_status, indent=2)}", file=sys.stderr)
        sys.exit(1)

    print("Created tickets:")
    for result, sample in zip(job_status["results"], SAMPLE_TICKETS):
        if result.get("id") is not None and not result.get("error"):
            print(f"  Zendesk #{result['id']}  (sample {sample['id']})  {sample['subject']}")
        else:
            print(f"  FAILED (sample {sample['id']} {sample['subject']}): {result}", file=sys.stderr)


if __name__ == "__main__":
    main()
