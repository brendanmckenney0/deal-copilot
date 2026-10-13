"""deal-copilot API.

  GET  /health            -> service + provider status
  POST /ingest            -> multipart file (pdf/md/txt) + doc_type form
                             field; runs the doc-intel pipeline
                             synchronously and returns a job envelope
                             {"job_id", "status": "complete", ...}
  GET  /jobs/{job_id}     -> the stored job record
  POST /ask               -> {"question"} -> routed fused answer
  GET  /                  -> the demo UI (static/index.html)

Run with:  python -m uvicorn app:app   (from the repo root)
"""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from connectors.docintel_connector import DocIntelConnector, SUPPORTED_SUFFIXES
from entities.seed import seed
from entities.store import EntityStore
from providers import PROVIDER_NAME, get_provider, load_state
from query.ask import Asker

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
UPLOADS = DATA / "uploads"
CHROMA = DATA / "chroma"

app = FastAPI(title="deal-copilot")
JOBS: dict[str, dict] = {}

_store = EntityStore(str(DATA / "entities.db"))
_provider = get_provider()
load_state(DATA / "tfidf.json")  # same embedding space as the index, if built
_asker = Asker(_store, CHROMA, _provider)


@app.on_event("startup")
def _startup():
    UPLOADS.mkdir(parents=True, exist_ok=True)
    if not _store.list_properties():
        seed(_store)  # make sure entity resolution works for uploads


@app.get("/health")
def health():
    return {"status": "ok", "provider": PROVIDER_NAME,
            "properties": len(_store.list_properties())}


@app.post("/ingest")
def ingest(file: UploadFile = File(...), doc_type: str = Form(...)):
    job_id = uuid.uuid4().hex[:12]
    if doc_type not in ("om", "lease"):
        return JSONResponse(
            {"job_id": job_id, "status": "failed",
             "error": f"doc_type must be 'om' or 'lease', got {doc_type!r}"},
            status_code=400)
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        return JSONResponse(
            {"job_id": job_id, "status": "failed",
             "error": f"unsupported file type {suffix!r}; "
                      f"supported: {sorted(SUPPORTED_SUFFIXES)}"},
            status_code=400)
    dest = UPLOADS / f"{job_id}_{Path(file.filename or 'upload').name}"
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    try:
        conn = DocIntelConnector(dest, doc_type, _store, CHROMA, _provider)
        conn.authenticate({})
        result = conn.ingest()
    except Exception as exc:  # noqa: BLE001 - surfaced in the job record
        record = {"job_id": job_id, "status": "failed",
                  "error": f"{type(exc).__name__}: {exc}"}
        JOBS[job_id] = record
        return JSONResponse(record, status_code=500)
    prop = _store.get_property(result["property_id"]) \
        if result["property_id"] else None
    record = {"job_id": job_id, "status": "complete",
              "doc_type": doc_type, "source_file": dest.name,
              "property": prop["canonical_name"] if prop else None,
              "fields_extracted": result["fields_extracted"],
              "reconciliation": result["reconciliation"],
              "gaps": result["gaps"],
              "validation_issues": result["validation_issues"]}
    JOBS[job_id] = record
    return record


@app.get("/jobs/{job_id}")
def job(job_id: str):
    record = JOBS.get(job_id)
    if not record:
        return JSONResponse({"error": "unknown job_id"}, status_code=404)
    return record


@app.post("/ask")
def ask(body: dict):
    question = (body.get("question") or "").strip()
    if not question:
        return JSONResponse({"error": "question is required"},
                            status_code=400)
    return _asker.ask(question)


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")
