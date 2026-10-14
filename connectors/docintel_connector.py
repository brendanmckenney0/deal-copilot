"""Doc-intelligence connector (ingest_mode="extract").

Takes a document path + doc_type, extracts its text (paged for PDFs,
single page for markdown/text), runs the extraction registry for that
doc_type, stores the structured record in the entity store's
`extractions` table, AND chunks the raw text into the JSON chunk store —
so one document is queryable both as structured data and via RAG.
"""
from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

from connectors.base import BaseConnector
from extraction import guardrails, registry
from providers import ensure_fitted
from query.chunkstore import append_chunks

SUPPORTED_SUFFIXES = {".pdf", ".md", ".markdown", ".txt"}


class DocIntelConnector(BaseConnector):
    name = "docintel"
    ingest_mode = "extract"

    def __init__(self, doc_path, doc_type, entity_store, data_dir,
                 provider=None):
        super().__init__(provider)
        self.doc_path = Path(doc_path)
        self.doc_type = doc_type
        self.store = entity_store
        self.data_dir = Path(data_dir)

    def authenticate(self, creds: dict):
        self.creds = creds  # demo-scale
        if not self.doc_path.exists():
            raise FileNotFoundError(f"document {self.doc_path} missing")
        if self.doc_path.suffix.lower() not in SUPPORTED_SUFFIXES:
            raise ValueError(
                f"unsupported file type {self.doc_path.suffix!r}; "
                f"supported: {sorted(SUPPORTED_SUFFIXES)}")

    def discover(self) -> list:
        if self.doc_path.exists():
            return [{"ref": str(self.doc_path), "label": self.doc_path.stem,
                     "doc_type": self.doc_type}]
        return []

    def fetch_changes(self, since) -> dict:
        return {"items": self.discover()}

    def extract_pages(self) -> list[dict]:
        suffix = self.doc_path.suffix.lower()
        if suffix == ".pdf":
            reader = PdfReader(str(self.doc_path))
            return [{"page": i + 1, "text": (pg.extract_text() or "")}
                    for i, pg in enumerate(reader.pages)]
        # markdown / text have no real pages — treat the whole file as
        # page 1 so citations stay honest ("p.1").
        text = self.doc_path.read_text(encoding="utf-8", errors="replace")
        return [{"page": 1, "text": text}]

    def ingest(self, since=None) -> dict:
        pages = self.extract_pages()
        schema, extractor = registry.get(self.doc_type)
        fields = extractor(pages, self.provider)

        issues = guardrails.validate(fields, schema)
        reconciliation = [r for r in fields.pop("_reconciliation", [])]
        gaps = guardrails.gap_report(fields, schema)

        property_id = self._resolve_property(fields)
        self.store.save_extraction(doc_type=self.doc_type, fields=fields,
                                   property_id=property_id,
                                   source_file=self.doc_path.name)

        # Also chunk the raw text into the chunk store (queryable both ways).
        kind = ("pdf" if self.doc_path.suffix.lower() == ".pdf"
                else "text")
        full_text = "\n\n".join(p["text"] for p in pages)
        chunks = self.chunk_text(full_text)
        if chunks:
            ensure_fitted(chunks)
            embeddings = self.provider.embed(chunks)
            fname = self.doc_path.name
            append_chunks(self.data_dir, [
                {"id": f"{fname}#{i}", "text": ch, "source": fname,
                 "embedding": emb}
                for i, (ch, emb) in enumerate(zip(chunks, embeddings))])

        return {"doc_type": self.doc_type,
                "source_file": self.doc_path.name,
                "property_id": property_id,
                "fields_extracted": sum(1 for f in fields.values()
                                       if isinstance(f, dict)
                                       and f.get("status") == "ok"),
                "validation_issues": issues,
                "reconciliation": reconciliation,
                "gaps": gaps,
                "chunks": len(chunks)}

    def _resolve_property(self, fields: dict) -> int | None:
        # OM: resolve via property name; lease: via tenant alias, then
        # premises address (which may mention the property).
        for key in ("property_name", "tenant_name", "premises_address"):
            rec = fields.get(key)
            if isinstance(rec, dict) and rec.get("value"):
                pid = self.store.resolve(str(rec["value"]))
                if pid:
                    return pid
        return None
