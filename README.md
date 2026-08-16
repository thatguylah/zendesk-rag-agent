# Northwind Cloud — AI Ticket Resolution Agent

A small, honestly-scoped RAG proof-of-concept for Zendesk-integrated ticket resolution. It
simulates a common customer-support workflow: a support ticket comes in, the agent retrieves
the relevant knowledge-base article, drafts a grounded reply, and — critically — **knows when
not to answer**.

It's built against a fictional product ("Northwind Cloud," a project-management SaaS) rather
than real Zendesk customer data, using the real [Zendesk Ticketing API](https://developer.zendesk.com/api-reference/ticketing/introduction/)
shape so it's a one-config-change away from pointing at a live Zendesk account.

## Why this exists

This demo exists to demonstrate practical, hands-on depth across the core building blocks of a
production RAG system: prompt engineering, retrieval-augmented generation (RAG), vector stores,
and evaluation/guardrails for model safety and reliability. Every one of those has a dedicated,
working piece of code here — not just a wired-up API call to a hosted model.

## Architecture

```
Ticket (Zendesk API or sample data)
        │
        ▼
 1. Redact secrets in ticket text (guardrail: never let a pasted credential reach the LLM)
        │
        ▼
 2. Retrieve top-k KB articles from a Chroma vector store (embeddings: sentence-transformers
    by default, TF-IDF as an offline fallback)
        │
        ▼
 3. Retrieval-confidence guardrail: if nothing retrieved is actually relevant, STOP here and
    escalate to a human — never hand a weak match to the LLM and hope
        │
        ▼
 4. Generate a grounded draft reply (Ollama / Anthropic — swappable via one env var), using a
    system prompt that forbids answering outside the retrieved context and requires citations
        │
        ▼
 5. Redact secrets in the OUTPUT too (defense in depth)
        │
        ▼
 6. Groundedness/faithfulness guardrail: independently score whether the draft's claims are
    actually supported by the retrieved text — NOT by trusting the model's own confidence
        │
        ▼
 7. Gate: AUTO_SUGGEST / NEEDS_REVIEW / ESCALATE, routed to a human either way — the agent
    never sends a customer-facing reply itself
```

Every stage is its own file in `src/`, so it maps directly onto a "walk me through the
architecture" conversation:

| File | Responsibility |
|---|---|
| `src/zendesk_client.py` | Real Zendesk Ticketing API client (HTTP Basic + API token auth), falls back to `data/sample_tickets.json` with zero config |
| `src/embeddings.py` | Pluggable embedding backends: `sentence-transformers` (production) or `tfidf` (offline fallback, no downloads) |
| `src/ingest.py` | Loads KB markdown, embeds it, writes it into a persistent local Chroma collection |
| `src/retriever.py` | Top-k retrieval + the retrieval-confidence-floor guardrail |
| `src/prompts.py` | The system prompt — grounding rules, refusal instructions, citation format |
| `src/llm_providers.py` | `OllamaProvider` / `AnthropicProvider` / `MockProvider`, one shared interface |
| `src/guardrails.py` | Secret redaction, independent groundedness scoring, the auto-suggest/review/escalate gate |
| `src/agent.py` | Orchestrates all of the above into one `TicketResolutionAgent.resolve(ticket)` call |
| `run_demo.py` | CLI walkthrough over all sample tickets — the live-demo script |
| `app.py` | Streamlit UI — the visual live-demo screen-share |
| `evaluate.py` | Offline eval harness against a labeled test set — see **Evaluation** below |
| `tests/test_pipeline.py` | pytest suite, runs fully offline (no LLM, no internet) |

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # then fill in what you have — every field has a safe default
```

### LLM backend (default: local via Ollama)

You chose to start local. Install [Ollama](https://ollama.com), then:

```bash
ollama pull llama3.2
ollama serve   # usually starts automatically after install
```

That's it — `LLM_PROVIDER=ollama` is the default in `.env.example`, no API key needed.

To switch to Claude later, it's a two-line change in `.env`:
```
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
```
Nothing else in the codebase changes — that's the point of `src/llm_providers.py`.

### Embeddings

`sentence-transformers` (semantic, production-quality) is the default and will download the
`all-MiniLM-L6-v2` model (~80MB) from Hugging Face on first run. If you're on a machine with
no internet access at demo time, set `EMBEDDING_BACKEND=tfidf` in `.env` for a fully offline
(but weaker — see **Known limitations**) fallback.

### Zendesk

Leave `ZENDESK_SUBDOMAIN` / `ZENDESK_EMAIL` / `ZENDESK_API_TOKEN` blank to run against
`data/sample_tickets.json`. To point at your Zendesk trial account:

1. In Zendesk Admin Center: **Apps and integrations > APIs > Zendesk API** → enable token
   access, generate a token.
2. Set `ZENDESK_SUBDOMAIN` (the part before `.zendesk.com`), `ZENDESK_EMAIL`, and
   `ZENDESK_API_TOKEN` in `.env`.
3. Create a few real tickets in your trial account (or leave the seeded demo tickets Zendesk
   trials come with) — `run_demo.py` and `app.py` will pull from the live account automatically.

## Running it

```bash
python run_demo.py              # CLI walkthrough, all 10 sample tickets
python run_demo.py 1006         # just one ticket, by id

streamlit run app.py            # visual UI — this is what to screen-share

python evaluate.py              # offline eval harness, writes eval_report.md
pytest -v                       # full test suite (offline, no LLM required)
```

## Prompt engineering

`src/prompts.py` is a single system prompt with five explicit, prioritized rules — most
importantly: **answer only from retrieved context**, and **refuse in a specific, named way**
when context is insufficient, rather than leaving refusal to the model's judgment. The prompt
also requires a structured `CITED_ARTICLES:` line so citations are machine-parseable, not
just prose the agent has to re-interpret.

Deliberately *not* asked for: a self-reported confidence score. LLMs are well known to be
poorly calibrated about their own uncertainty — a hallucinated answer is often stated just as
confidently as a correct one. Trusting the model to grade itself defeats the purpose of a
guardrail. Confidence in this system is computed independently (see below).

## RAG & vector store

KB articles (`data/kb_articles/*.md`) are embedded and stored in a persistent local
[Chroma](https://www.trychroma.com/) collection (`src/ingest.py`). Retrieval is top-k cosine
similarity (`src/retriever.py`). The KB here is small enough to index at the article level;
a longer real-world KB would need a chunking step before this (noted as a next step, not
silently skipped).

## Guardrails & evaluation — the part the job spec calls out by name

Three independent, separately-testable checks (`src/guardrails.py`):

1. **Retrieval-confidence floor.** Before generation even happens: if the best-retrieved
   article isn't actually similar to the ticket, the agent refuses to draft anything and
   escalates. This is the single highest-leverage guardrail — most hallucination in RAG
   systems happens when weak retrieval results are handed to the LLM anyway.
2. **Secret/credential redaction**, applied to both the *input* (before it ever reaches the
   prompt) and the *output* (in case the model echoes or invents something credential-shaped).
   See ticket `1006` in the sample data, which pastes a fake live API token — the pipeline
   redacts it before it's ever sent to the LLM.
3. **Groundedness/faithfulness scoring**, computed independently of the model: the draft is
   split into sentences, and each sentence is checked for embedding similarity against the
   retrieved KB text. The score is the fraction of sentences that are actually supported —
   this is what feeds the final gate (auto-suggest / needs review / escalate), not the model's
   own say-so.

### `evaluate.py` — real numbers, not a vibe check

Run against `data/eval_set.json` (10 labeled tickets, including one deliberately
out-of-scope ticket and one with a pasted credential) with the offline TF-IDF + mock-LLM
stack (so it reproduces identically without any model/API dependency):

| Metric | Result |
|---|---|
| Retrieval hit-rate@3 | 90% (9/10) |
| Mean groundedness (generated drafts) | 94% |
| Secret redaction check (ticket 1006) | PASS |
| Out-of-scope escalation check (ticket 1007) | PASS |

The one miss is instructive, not swept under the rug: **ticket 1009** ("someone logged in
from an unrecognized location") retrieves the wrong article (`kb_001`, password reset,
matched on surface words like "account" and "login") instead of the correct one (`kb_010`,
security incident). The generated draft is then *fully grounded in the wrong article* —
94% groundedness on a wrong answer. This is exactly why groundedness and retrieval accuracy
are tracked as **two separate metrics**: a faithful-to-context answer isn't the same thing as
a correct one, and only measuring one of them hides the other's failures. (This is also the
single clearest argument for the semantic `sentence-transformers` backend over the offline
TF-IDF fallback — TF-IDF's pure lexical matching is exactly what causes this particular miss.)

`eval_report.md` in this repo is the actual output of the last run — regenerate it any time
with `python evaluate.py`.

## Known limitations (said out loud, not hidden)

- **TF-IDF fallback is lexical, not semantic** — see the ticket-1009 miss above. It exists so
  the pipeline is provably correct with zero network dependency (this is how it was
  developed and tested); `sentence-transformers` is the intended production path.
- **`MockProvider` is a deterministic extractive stand-in**, not a real model. It validates
  that retrieval → guardrails → gating are wired correctly; it says nothing about real
  generation quality. Swap in Ollama or Anthropic for a true generation-quality read.
- **Thresholds are starting points, not tuned constants.** `RETRIEVAL_CONFIDENCE_FLOOR` and
  the groundedness gate thresholds in `.env.example` were calibrated empirically against
  *this* small KB with the *TF-IDF* backend — re-run `evaluate.py` against your real KB and
  embedding backend before trusting them anywhere real.
- **Article-level chunking** only works because these sample KB articles are short. A longer
  real KB needs a sliding-window chunker in `ingest.py`.
- **No conversation memory / multi-turn handling** — each ticket is resolved independently,
  deliberately, to keep the scope to what's demoable in a few hours.

## ZAF sidebar app -- the agent, inside a real Zendesk ticket

[`../zaf-sidebar-app/`](../zaf-sidebar-app/) (a sibling of this repo, not nested inside it) is a
small [Zendesk Apps Framework](https://developer.zendesk.com/documentation/apps/) app
(`ticket_sidebar` location) that puts this same agent directly into the Zendesk agent
workspace, next to a real ticket -- rather than a separate Streamlit screen. It:

1. Reads the open ticket's fields via the ZAF SDK (`client.get('ticket...')`) -- no Zendesk
   API credentials needed in the app itself.
2. Sends them to `src/api.py` (a thin FastAPI wrapper around the same `TicketResolutionAgent`
   used by `app.py`) and renders the gate/draft/groundedness/KB-context exactly as the
   Streamlit UI does.
3. "Insert as reply draft" writes the draft into the ticket's reply composer
   (`client.set('comment.text', ...)`) -- it never submits anything itself. The agent still
   has to review it and hit send, same human-in-the-loop guarantee as everywhere else in this
   repo.

```
../zaf-sidebar-app/            # sibling of zendesk-rag-agent/, i.e. Zendesk/zaf-sidebar-app/
├── manifest.json              # ticket_sidebar location, api_base_url parameter
├── translations/
│   └── en.json                # required by zcli apps:validate -- app name/description strings
└── assets/
    ├── iframe.html
    ├── main.js                # ZAF SDK glue: get ticket -> call API -> render -> insert
    ├── style.css
    └── icon.png
```

### Running it against your sandbox

```bash
# 1. Start the API the app talks to (separate terminal, keep running)
source .venv/bin/activate
uvicorn src.api:app --reload --port 8000

# 2. One-time: authenticate zcli against YOUR sandbox (run this yourself)
#
#    Option A -- API token (zcli login -i): prompts for subdomain, email, and
#    API token (Admin Center > Apps and integrations > APIs > Zendesk API).
#
#    Option B -- OAuth client_credentials token (what this repo is set up
#    for): put the client secret in .oauth-client-secret (gitignored, already
#    present in this repo) and run:
./scripts/get_zendesk_oauth_token.sh
source .oauth-token.env
#    This calls POST https://ibm-38381.zendesk.com/oauth/tokens with your
#    OAuth client's client_credentials grant and writes ZENDESK_OAUTH_TOKEN /
#    ZENDESK_SUBDOMAIN to .oauth-token.env (gitignored, mode 600) -- zcli
#    picks ZENDESK_OAUTH_TOKEN up automatically ahead of any saved login.
#    client_credentials tokens are short-lived; re-run the script if zcli
#    starts failing auth after a long session.

# 3. Validate the manifest
cd ../zaf-sidebar-app
zcli apps:validate .

# 4. Start the local dev server -- this temporarily installs a dev build of
#    the app on your sandbox account for the duration of the session. It will
#    prompt once for the api_base_url parameter (default http://localhost:8000
#    is fine for local dev -- just press enter).
zcli apps:server
```

`zcli apps:server` prints `Apps server is running on http://localhost:4567`. Open a ticket in
your sandbox's agent workspace and add `?zcli_apps=true` to the URL, e.g.
`https://ibm-38381.zendesk.com/agent/tickets/<id>?zcli_apps=true` -- the sidebar app loads from
your local server for that page load. Click **Resolve with AI agent**, confirm the
gate/draft/context match what `app.py` shows for the same ticket content, then **Insert as reply
draft** and confirm it lands in the composer untouched -- you send it (or don't) manually.

`src/api.py`'s CORS is locked to `localhost:4567` (zcli's default dev-server port). If zcli
picks a different port, update `allow_origins` in `src/api.py` to match.

### Packaging for a persistent demo install

`zcli apps:server` is fine for live iteration, but for a live demo you may want a stable
install that doesn't depend on a dev server staying attached:

```bash
zcli apps:package    # writes a .zip
```

Then Admin Center > Apps and integrations > Zendesk Support apps > Upload private app, pointing
`api_base_url` at wherever `src/api.py` is actually reachable from (e.g. a tunnel like `ngrok
http 8000` if the API is only running on your laptop, not a public host).

## How this maps to real Zendesk platform work

This mirrors real Zendesk platform concepts on purpose: the retrieve → generate → govern loop
here is structurally the same idea behind Zendesk's own "Resolution Learning Loop" and their
AI agents' governance/guardrail story. The credential-redaction guardrail specifically mirrors
a rule an actual support team would need (KB article `kb_010` in the sample data even states
it explicitly: agents should never repeat back a customer's pasted credential).
