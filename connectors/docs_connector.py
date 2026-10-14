"""Docs connector (ingest_mode="chunk").

Ingests data/corpus/*.md: sliding-window chunking (~900 chars,
word-safe), embeds with the active provider, stores chunks + embeddings
in data/chunks.json (pure-python chunk store; see query/chunkstore.py).
Re-running is idempotent for the same source file (ids are deterministic
per file+chunk index).
"""
from __future__ import annotations

from pathlib import Path

from connectors.base import BaseConnector
from providers import ensure_fitted
from query.chunkstore import append_chunks


class DocsConnector(BaseConnector):
    name = "docs"
    ingest_mode = "chunk"

    def __init__(self, corpus_dir, data_dir, provider=None):
        super().__init__(provider)
        self.corpus_dir = Path(corpus_dir)
        self.data_dir = Path(data_dir)

    def authenticate(self, creds: dict):
        self.creds = creds  # demo-scale: local files need no real auth
        if not self.corpus_dir.exists():
            raise FileNotFoundError(f"corpus dir {self.corpus_dir} missing")

    def discover(self) -> list:
        return [{"ref": str(p), "label": p.stem}
                for p in sorted(self.corpus_dir.glob("*.md"))]

    def fetch_changes(self, since) -> dict:
        items = []
        for d in self.discover():
            items.append({"title": d["label"],
                          "text": Path(d["ref"]).read_text(encoding="utf-8"),
                          "source": Path(d["ref"]).name})
        return {"items": items}

    def ingest(self, since=None) -> dict:
        items = self.fetch_changes(since)["items"]
        ensure_fitted([f"{it['title']}\n\n{it['text']}" for it in items])
        chunks = []
        for it in items:
            for i, ch in enumerate(self.chunk_text(it["text"])):
                stem = Path(it["source"]).stem
                chunks.append({"id": f"{stem}#{i}",
                               "text": f"{it['title']}\n\n{ch}",
                               "source": it["source"]})
        if chunks:
            embeddings = self.provider.embed([c["text"] for c in chunks])
            for c, emb in zip(chunks, embeddings):
                c["embedding"] = emb
            append_chunks(self.data_dir, chunks)
        return {"files": len(items), "chunks": len(chunks),
                "collection": "chunks.json"}
