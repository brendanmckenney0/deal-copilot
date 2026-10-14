"""JSON chunk store — pure-python replacement for Chroma at demo scale.

The RAG path only ever needed: store chunk texts + embeddings + source
metadata at index time, then top-k cosine similarity at query time.
With dozens of chunks, brute-force cosine is exactly equivalent to an
approximate vector index, with zero heavy dependencies.

chunks.json schema: {"chunks": [{"id", "text", "source", "embedding"}]}
"""
from __future__ import annotations

import json
import math
from pathlib import Path

FILENAME = "chunks.json"


def save_chunks(data_dir: Path | str, chunks: list[dict]) -> Path:
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / FILENAME
    path.write_text(json.dumps({"chunks": chunks}), encoding="utf-8")
    return path


def load_chunks(data_dir: Path | str) -> list[dict]:
    path = Path(data_dir) / FILENAME
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("chunks", [])
    except (json.JSONDecodeError, OSError):
        return []


def append_chunks(data_dir: Path | str, new_chunks: list[dict]) -> Path:
    """Merge new chunks into the store, replacing same-id entries.

    Lets the corpus connector and the doc-intel connector each add
    chunks (e.g. user uploads) without wiping each other's work.
    """
    existing = {c["id"]: c for c in load_chunks(data_dir) if "id" in c}
    for c in new_chunks:
        existing[c["id"]] = c
    return save_chunks(data_dir, list(existing.values()))


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def query(question_vec: list[float], chunks: list[dict],
          top_k: int = 5, threshold: float = 0.12) -> list[dict]:
    """Top-k chunks by cosine similarity, gated by threshold.

    Returns dicts {text, source, title, score}, highest score first —
    the same shape _rag produced from Chroma.
    """
    scored = []
    for ch in chunks:
        emb = ch.get("embedding") or []
        sim = _cosine(question_vec, emb)
        if sim >= threshold:
            scored.append({"text": ch["text"],
                           "source": ch.get("source", "?"),
                           "title": ch.get("source", "?"),
                           "score": sim})
    scored.sort(key=lambda c: c["score"], reverse=True)
    return scored[:top_k]
