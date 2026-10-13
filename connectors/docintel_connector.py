"""Doc-intelligence connector (ingest_mode="extract").

Takes a PDF path + doc_type, extracts pages with pypdf, runs the
extraction registry for that doc_type, stores the structured record in
the entity store's `extractions` table, AND chunks the PDF text into
Chroma — so one document is queryable both as structured data and via
RAG.
"""
from __future__ import annotations

from pathlib import Path

import chromadb
from pypdf import PdfReader

from connectors.base import BaseConnector
from connectors.docs_connector import COLLECTION
from extraction import guardrails, registry
from providers import ensure_fitted


class DocIntelConnector(BaseConnector):
    name = "docintel"
    ingest_mode = "extract"

    def __init__(self, pdf_path, doc_type, entity_store, chroma_dir,
                 provider=None):
        super().__init__(provider)
        self.pdf_path = Path(pdf_path)
        self.doc_type = doc_type
        self.store = entity_store
        self.chroma_dir = Path(chroma_dir)

    def authenticate(self, creds: dict):
        self.creds = creds  # demo-scale
        if not self.pdf_path.exists():
            raise FileNotFoundError(f"PDF {self.pdf_path} missing")

    def discover(self) -> list:
        if self.pdf_path.exists():
            return [{"ref": str(self.pdf_path), "label": self.pdf_path.stem,
                     "doc_type": self.doc_type}]
        return []

    def fetch_changes(self, since) -> dict:
        return {"items": self.discover()}

    def extract_pages(self) -> list[dict]:
        reader = PdfReader(str(self.pdf_path))
        return [{"page": i + 1, "text": (pg.extract_text() or "")}
                for i, pg in enumerate(reader.pages)]

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
                                   source_file=self.pdf_path.name)

        # Also chunk the raw PDF text into Chroma (queryable both ways).
        full_text = "\n\n".join(p["text"] for p in pages)
        chunks = self.chunk_text(full_text)
        if chunks:
            ensure_fitted(chunks)
            embeddings = self.provider.embed(chunks)
            coll = chromadb.PersistentClient(
                path=str(self.chroma_dir)).get_or_create_collection(
                    COLLECTION, metadata={"hnsw:space": "cosine"})
            fname = self.pdf_path.name
            coll.upsert(
                ids=[f"{fname}#{i}" for i in range(len(chunks))],
                documents=chunks,
                embeddings=embeddings,
                metadatas=[{"source": fname, "kind": "pdf",
                            "doc_type": self.doc_type, "chunk": i}
                           for i in range(len(chunks))])

        return {"doc_type": self.doc_type,
                "source_file": self.pdf_path.name,
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
