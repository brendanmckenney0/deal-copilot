# Testing deal-copilot yourself (Mac)

You don't need to be a developer — follow the steps in order. Each
step tells you what success looks like. Everything runs on your own
machine; nothing is uploaded anywhere.

**You will need:** a Mac with Python 3.10+ (`python3 --version`) and
this repo cloned or downloaded.

## 1. Get the code

```bash
git clone <repo-url> deal-copilot
cd deal-copilot
```

**Success:** you see `app.py`, `requirements.txt`, `README.md`.

## 2. Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Success:** ends with `Successfully installed ...`.

## 3. Generate the sample documents

```bash
python scripts/generate_docs.py
```

**Success:** you see "wrote ..." lines for two PDFs
(`data/pdfs/`), ground-truth JSONs (`data/ground_truth/`), and five
markdown files (`data/corpus/`). All fictional.

## 4. Build the index

```bash
PROVIDER=local python scripts/build_index.py
```

**Success:** ends with `index build complete`, showing reconciliation
`[pass]` lines for the OM and the lease. This seeds the property
registry, extracts both PDFs into structured records, and chunks
everything into the vector store.

## 5. Start the app

```bash
python -m uvicorn app:app
```

**Success:** `Uvicorn running on http://127.0.0.1:8000`. Leave that
Terminal running. (Always use `python -m uvicorn`, not bare
`uvicorn` — some Macs have a stale copy outside the venv.)

> **Port already in use?** `python -m uvicorn app:app --port 8001`
> (then use `http://127.0.0.1:8001`).

## 6. Open the demo

Go to **http://127.0.0.1:8000**. Two tabs: **Ask** and **Screen a
document**.

## 7. Ask questions (the fused query path)

Try these in order — each exercises a different route:

1. **"When does the Bluefin Coffee lease expire?"**
   → route: structured. Answer with the date plus the renewal notice
   deadline, cited to the lease PDF page.
2. **"Summarize the management notes for Maple Grove."**
   → route: RAG. Answer built from retrieved passages, with sources.
3. **"Compare the asking price and cap rate across properties"**
   → route: both. A comparison table plus narrative.
4. **"What is the CEO's favorite color?"**
   → honest refusal: "I don't know based on the indexed
   documents." That is the system working as designed.

## 8. Screen a document

Click **Screen a document**, choose `lease`, upload
`data/pdfs/lease_bluefin.pdf`. **Success:** a job record showing
10/10 fields extracted, property resolved to Harbor Point, and
reconciliation checks passing.

> The uploader also accepts Markdown and text files (`.md`,
> `.markdown`, `.txt`) — handy for lease abstracts authored as text.
> Markdown has no real pages, so citations read "p.1".

## 9. Run the eval (optional)

In a **new** Terminal:

```bash
cd deal-copilot
source .venv/bin/activate
PROVIDER=local python eval/run_eval.py
```

**Success:** `== 20 passed, 0 failed ==`.

## 10. Try real LLM quality (optional, needs an OpenAI key)

```bash
export OPENAI_API_KEY="sk-..."
PROVIDER=openai python scripts/build_index.py
PROVIDER=openai python -m uvicorn app:app
```

Slower, a few cents per document — but real embeddings and
extraction. The guardrails (citations, NOT_FOUND, reconciliation)
apply identically.

> Never paste your API key into a chat window or commit the `.env`
> file.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ModuleNotFoundError: No module named 'fastapi'` | Your shell found a `uvicorn` outside the venv — use `python -m uvicorn app:app` |
| `address already in use` | Use `--port 8001` (see step 5) |
| Page won't load | Check the uvicorn Terminal is still running; URL must be `http://127.0.0.1:8000` exactly |
| Ask returns "I don't know" for everything | You skipped step 4 (build the index first), or the uvicorn Terminal was started before step 4 — restart it |
| `OPENAI_API_KEY` errors | You skipped step 10's `export`; check the key at platform.openai.com |
