"""Base connector: every data source plugs in here.

ingest_mode controls how fetched content enters the fused system:
  "chunk"   -> free text is chunked + embedded into the RAG vector store
  "extract" -> structured fields are pulled via the extraction registry
               into the entity store, AND the raw text is also chunked
               into the vector store so one document is queryable both ways.

ConnectorPair binds one connector class to one credential dict and a
schedule. Demo-scale: credentials are a plain dict, schedule is a
cron-ish string — no real OAuth. A production deployment would use a
secrets manager and per-connector ACLs.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class BaseConnector(ABC):
    name = "base"
    ingest_mode = "chunk"  # "chunk" | "extract"

    def __init__(self, provider=None):
        from providers import get_provider
        self.provider = provider or get_provider()

    @abstractmethod
    def authenticate(self, creds: dict):
        """Demo-scale auth: validate/store the credential dict."""

    @abstractmethod
    def discover(self) -> list:
        """List candidate items available at the source."""

    @abstractmethod
    def fetch_changes(self, since) -> dict:
        """Delta fetch; returns {"items": [...]} changed since the marker."""

    def chunk_text(self, text: str, size: int = 900,
                   overlap: int = 120) -> list[str]:
        """Word-safe sliding-window chunking (~900 chars)."""
        words = text.split()
        chunks, cur, cur_len = [], [], 0
        for w in words:
            if cur_len + len(w) + 1 > size and cur:
                chunks.append(" ".join(cur))
                tail, tail_len = [], 0
                for tw in reversed(cur):
                    if tail_len + len(tw) + 1 > overlap:
                        break
                    tail.append(tw)
                    tail_len += len(tw) + 1
                cur, cur_len = list(reversed(tail)), tail_len
            cur.append(w)
            cur_len += len(w) + 1
        if cur:
            chunks.append(" ".join(cur))
        return chunks


@dataclass
class ConnectorPair:
    """One connector x credential = one ingestion unit."""
    connector: str
    credential: dict = field(default_factory=dict)
    schedule: str = "daily"
