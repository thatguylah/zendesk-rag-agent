#!/usr/bin/env python3
"""
Offline evaluation harness -- the "how do you know it's reliable" answer.

Computes, against data/eval_set.json:
  - Retrieval hit-rate@k: did a relevant KB article show up in the top-k
    results (or, for the one ticket with no correct KB article, did the
    system correctly decline rather than force a match)?
  - Mean groundedness across generated drafts.
  - Gate distribution (how often the system would auto-suggest vs escalate).
  - Two targeted safety checks: the pasted-credential ticket must never leak
    the credential, and the out-of-scope ticket must escalate, not hallucinate.

Run with: python evaluate.py
Writes a human-readable report to eval_report.md.
"""
import json
from pathlib import Path

from src.agent import TicketResolutionAgent
from src.config import CONFIG
from src.guardrails import Gate
from src.ingest import build_index
from src.zendesk_client import ZendeskClient

EVAL_SET_PATH = Path(__file__).parent / "data" / "eval_set.json"


def run_evaluation(config=CONFIG) -> dict:
    build_index(config)
    client = ZendeskClient(config)
    agent = TicketResolutionAgent(config=config)
    eval_set = json.loads(EVAL_SET_PATH.read_text())

    rows = []
    for item in eval_set:
        ticket = client.get_ticket(item["ticket_id"])
        result = agent.resolve(ticket)
        retrieved_ids = [c.kb_id for c in result.retrieved_chunks]
        expected = set(item["expected_kb_ids"])

        if expected:
            retrieval_hit = bool(expected & set(retrieved_ids))
        else:
            # Correct behavior for an unanswerable ticket is to escalate, not retrieve-and-answer.
            retrieval_hit = not result.retrieval_sufficient

        rows.append({
            "ticket_id": ticket.id,
            "subject": ticket.subject,
            "expected_kb_ids": sorted(expected),
            "retrieved_kb_ids": retrieved_ids,
            "retrieval_hit": retrieval_hit,
            "gate": result.gate.value,
            "groundedness": round(result.groundedness, 2) if result.retrieval_sufficient else None,
            "input_had_secret": result.input_had_secret,
            "output_had_secret": result.output_had_secret,
            "draft_preview": (result.draft_reply[:100] + "...") if result.draft_reply else None,
            "note": item["note"],
        })

    n = len(rows)
    retrieval_accuracy = sum(r["retrieval_hit"] for r in rows) / n
    grounded_rows = [r for r in rows if r["groundedness"] is not None]
    mean_groundedness = sum(r["groundedness"] for r in grounded_rows) / len(grounded_rows) if grounded_rows else 0.0
    gate_counts = {g.value: sum(1 for r in rows if r["gate"] == g.value) for g in Gate}

    secret_ticket = next(r for r in rows if r["ticket_id"] == 1006)
    secret_check_pass = secret_ticket["input_had_secret"] and (
        secret_ticket["draft_preview"] is None or "sk_live_" not in secret_ticket["draft_preview"]
    )
    no_kb_ticket = next(r for r in rows if r["ticket_id"] == 1007)
    no_kb_check_pass = no_kb_ticket["gate"] == Gate.ESCALATE_NO_KB_MATCH.value

    return {
        "config": {"llm_provider": config.llm_provider, "embedding_backend": config.embedding_backend},
        "rows": rows,
        "retrieval_accuracy": retrieval_accuracy,
        "mean_groundedness": mean_groundedness,
        "gate_counts": gate_counts,
        "secret_check_pass": secret_check_pass,
        "no_kb_check_pass": no_kb_check_pass,
    }


def render_report(results: dict) -> str:
    lines = []
    lines.append("# Evaluation Report\n")
    lines.append(f"Config: LLM provider = `{results['config']['llm_provider']}`, "
                  f"embedding backend = `{results['config']['embedding_backend']}`\n")
    lines.append(f"- **Retrieval accuracy**: {results['retrieval_accuracy']:.0%} "
                 f"({sum(r['retrieval_hit'] for r in results['rows'])}/{len(results['rows'])} tickets)")
    lines.append(f"- **Mean groundedness** (generated drafts only): {results['mean_groundedness']:.0%}")
    lines.append(f"- **Gate distribution**: {results['gate_counts']}")
    lines.append(f"- **Secret redaction check** (ticket 1006 never leaks the pasted token): "
                 f"{'PASS' if results['secret_check_pass'] else 'FAIL'}")
    lines.append(f"- **Out-of-scope escalation check** (ticket 1007 escalates instead of hallucinating): "
                 f"{'PASS' if results['no_kb_check_pass'] else 'FAIL'}\n")
    lines.append("| Ticket | Expected KB | Retrieved KB | Hit | Gate | Groundedness |")
    lines.append("|---|---|---|---|---|---|")
    for r in results["rows"]:
        lines.append(
            f"| {r['ticket_id']} {r['subject'][:40]} | {', '.join(r['expected_kb_ids']) or '(none)'} "
            f"| {', '.join(r['retrieved_kb_ids'])} | {'✅' if r['retrieval_hit'] else '❌'} "
            f"| {r['gate']} | {r['groundedness'] if r['groundedness'] is not None else '-'} |"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    results = run_evaluation()
    report = render_report(results)
    print(report)
    Path("eval_report.md").write_text(report, encoding="utf-8")
    print("\nWritten to eval_report.md")
