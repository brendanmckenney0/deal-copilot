# deal-copilot

A fused demo: **RAG over documents** + **structured document
extraction**, behind one query router and one entity store. Ask
questions about a fictional property portfolio — some answers come
from structured records (lease dates, OM money fields), some from
retrieved passages, some from both.

All data is fictional. See `docs/architecture.md` for the design and
`docs/client-fit.md` for who this product serves.

## Quickstart

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/generate_docs.py   # build sample PDFs + corpus + ground truth
python scripts/build_index.py     # ingest everything (entity store + Chroma)
python -m uvicorn app:app         # open http://127.0.0.1:8000
```

Two tabs: **Ask** (routed Q&A with citations) and **Screen a
document** (upload a PDF as `om` or `lease`, get structured fields +
gap report). Try:

- "When does the Bluefin Coffee lease expire?" → structured
- "Summarize the management notes for Maple Grove." → RAG
- "Compare the asking price and cap rate across properties" → both

`PROVIDER=local` (default) runs everything with no key and no cost —
narrow but honest. Set `PROVIDER=openai` + `OPENAI_API_KEY` for real
embeddings, generation, and extraction.

## Eval

```bash
PROVIDER=local python eval/run_eval.py
```

Combined suite: field-level extraction accuracy vs ground truth (money
fields weighted 3×), 6 router-classification tests, 4 end-to-end ask
tests (structured, RAG, comparison, refusal). Currently **20/20**.

## Repo layout

```
connectors/       unified connector framework (chunk + extract modes)
extraction/       pluggable doc-type registry: om + lease schemas,
                  guardrails (NOT_FOUND discipline, reconciliation)
entities/         SQLite property registry + alias resolution
query/            heuristic router, fused ask path, permissions filter
providers.py      PROVIDER=openai|local (embeddings, generation, extraction)
app.py            FastAPI: /health, /ingest, /jobs/{id}, /ask, UI
scripts/          generate_docs.py (samples), build_index.py (ingest all)
eval/             combined eval runner
docs/             architecture.md, client-fit.md
static/           demo UI
```

## For clients

This is the demo kernel of an asset-management copilot: lease
abstraction + critical-date tracking as the pilot (bounded lease set
→ structured abstracts + notice-deadline diary), expanding to
portfolio monitoring, proactive alerts, and investor-reporting
synthesis. See `docs/client-fit.md`.
