"""Docs connector (ingest_mode="chunk").

Ingests data/corpus/*.md: sliding-window chunking (~900 chars,
word-safe), embeds with the active provider, stores in the persistent
Chroma collection `deal_copilot_docs`. Re-running is idempotent for the
same source file (ids are deterministic per file+chunk index).
"""
from __future__ import annotations

from pathlib import Path

import chromadb

from connectors.base import BaseConnector
from providers import ensure_fitted

COLLECTION = "deal_copilot_docs"


class DocsConnector(BaseConnector):
    name = "docs"
    ingest_mode = "chunk"

    def __init__(self, corpus_dir, chroma_dir, provider=None):
        super().__init__(provider)
        self.corpus_dir = Path(corpus_dir)
        self.chroma_dir = Path(chroma_dir)

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

    def get_collection(self):
        client = chromadb.PersistentClient(path=str(self.chroma_dir))
        return client.get_or_create_collection(
            COLLECTION, metadata={"hnsw:space": "cosine"})

    def ingest(self, since=None) -> dict:
        items = self.fetch_changes(since)["items"]
        ensure_fitted([f"{it['title']}\n\n{it['text']}" for it in items])
        coll = self.get_collection()
        ids, docs, metas = [], [], []
        for it in items:
            for i, ch in enumerate(self.chunk_text(it["text"])):
                stem = Path(it["source"]).stem
                ids.append(f"{stem}#{i}")
                docs.append(f"{it['title']}\n\n{ch}")
                metas.append({"source": it["source"], "kind": "corpus",
                              "chunk": i})
        if ids:
            embeddings = self.provider.embed(docs)
            coll.upsert(ids=ids, documents=docs,
                        embeddings=embeddings, metadatas=metas)
        return {"files": len(items), "chunks": len(ids),
                "collection": COLLECTION}
