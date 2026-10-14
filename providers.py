"""Unified provider abstraction behind PROVIDER=openai|local.

Interface every provider implements:
  embed(texts) -> list of embedding vectors
  answer(question, chunks, history) -> composed answer string
  extract_fields(pages, schema) -> {field_name: field_record}

  pages  = [{"page": int, "text": str}]
  schema = [{"name", "label", "kind": "text|number|money|percent|table",
             "columns"?: [str] (for tables)}]
  field_record = {"value", "page", "status": "ok|not_found|uncertain",
                  "citation"}

Local provider (default): deterministic, dependency-free demo backend.
  - embeddings: TF-IDF vectors over the ingested corpus (fit_corpus is
    called at ingest time), L2-normalized. Unknown terms hash into
    overflow buckets. No semantics — keyword overlap only.
  - answerer: template that quotes the retrieved chunks verbatim.
  - field extractor: NARROW regex over "Label: value" lines and
    "- col | col | col" table rows, tuned to the sample documents from
    scripts/generate_docs.py. It will NOT generalize to arbitrary PDFs.

Real quality needs PROVIDER=openai with OPENAI_API_KEY.
"""
from __future__ import annotations

import hashlib
import math
import os
import re
from abc import ABC, abstractmethod

WORD_RE = re.compile(r"[a-z0-9]+")

STOPWORDS = frozenset(
    """
    the a an and or of to in on for with is are was were be been being
    it its this that these those you your yours we our ours they their
    at as by from can will would could should do does did how what when
    where why which who whom whose if then than so such into about over
    under after before between not no yes all any each every more most
    other some such only own same too very just also per via
    """.split()
)

# -- TF-IDF embedding machinery (corpus is fitted at ingest time) --------

_idf: dict[str, float] | None = None
_idf_default: float = 1.0
_vocab_index: dict[str, int] | None = None
OVERFLOW = 256


def fit_corpus(texts: list[str]) -> None:
    """Fit IDF weights over the ingested texts. Called once per ingest.
    Fit ONCE over the whole corpus (see scripts/build_index.py) — refitting
    changes the embedding dimension and breaks the stored vectors."""
    global _idf, _idf_default, _vocab_index
    doc_freq: dict[str, int] = {}
    n_docs = 0
    for text in texts:
        n_docs += 1
        for t in {
            tok for tok in WORD_RE.findall(text.lower()) if tok not in STOPWORDS
        }:
            doc_freq[t] = doc_freq.get(t, 0) + 1
    n_docs = max(n_docs, 1)
    _idf = {t: math.log((n_docs + 1) / (df + 1)) + 1.0 for t, df in doc_freq.items()}
    _idf_default = math.log(n_docs + 1) + 1.0
    _vocab_index = {t: i for i, t in enumerate(sorted(_idf.keys()))}


def save_state(path) -> None:
    """Persist the fitted IDF/vocabulary so other processes (server, eval)
    embed in the same vector space. The .db and chunks.json are rebuilt by
    build_index.py; this file goes with them (gitignored)."""
    import json
    from pathlib import Path
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps({
        "idf": _idf, "idf_default": _idf_default,
        "vocab_index": _vocab_index, "overflow": OVERFLOW,
    }))


def load_state(path) -> bool:
    """Load a fitted state saved by save_state. Returns True on success."""
    import json
    from pathlib import Path
    global _idf, _idf_default, _vocab_index, OVERFLOW
    p = Path(path)
    if not p.exists():
        return False
    data = json.loads(p.read_text())
    _idf = data["idf"]
    _idf_default = data["idf_default"]
    _vocab_index = {t: int(i) for t, i in data["vocab_index"].items()}
    OVERFLOW = data.get("overflow", OVERFLOW)
    return True


def ensure_fitted(texts: list[str]) -> None:
    """Fit the IDF model only if this process hasn't fitted/loaded one yet."""
    if _idf is None or _vocab_index is None:
        fit_corpus(texts)


def _tfidf_embedding(text: str) -> list[float]:
    if _idf is None or _vocab_index is None:
        fit_corpus([text])
    assert _idf is not None and _vocab_index is not None
    tf: dict[str, int] = {}
    for term in WORD_RE.findall(text.lower()):
        if term in STOPWORDS:
            continue
        tf[term] = tf.get(term, 0) + 1
    vec = [0.0] * (len(_vocab_index) + OVERFLOW)
    for term, count in tf.items():
        weight = 1.0 + math.log(count)
        if term in _vocab_index:
            vec[_vocab_index[term]] += weight * _idf[term]
        else:
            h = int(hashlib.md5(term.encode("utf-8")).hexdigest(), 16)
            bucket = len(_vocab_index) + (h % OVERFLOW)
            sign = 1.0 if (h >> 7) & 1 else -1.0
            vec[bucket] += sign * weight * _idf_default
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


# -- provider interface ----------------------------------------------------

class Provider(ABC):
    name: str = "base"

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]: ...

    @abstractmethod
    def answer(self, question: str, chunks: list[dict],
               history: list[dict]) -> str: ...

    @abstractmethod
    def extract_fields(self, pages: list[dict], schema: list[dict]) -> dict: ...


def _ok(value, page, citation):
    return {"value": value, "page": page, "status": "ok",
            "citation": (citation or "")[:200]}


def _not_found(label):
    return {"value": None, "page": None, "status": "not_found",
            "citation": f"label '{label}' not found in document"}


def _parse_number(raw: str):
    cleaned = raw.replace("$", "").replace(",", "").strip()
    cleaned = re.split(r"\s", cleaned)[0].rstrip("%")
    try:
        return int(cleaned) if re.fullmatch(r"-?\d+", cleaned) else float(cleaned)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Local provider
# ---------------------------------------------------------------------------

class LocalProvider(Provider):
    """No-key provider: TF-IDF retrieval + template answers + a NARROW
    schema-driven regex extractor (see module docstring)."""

    name = "local"

    # -- RAG side ------------------------------------------------------
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [_tfidf_embedding(t) for t in texts]

    def answer(self, question, chunks, history):
        if not chunks:
            return "I don't know based on the indexed documents."
        lines = [f"Based on the indexed documents, here's what I found:", ""]
        for i, ch in enumerate(chunks, 1):
            snippet = ch["text"].strip().replace("\n", " ")
            if len(snippet) > 700:
                snippet = snippet[:700].rsplit(" ", 1)[0] + "..."
            lines.append(f"**{i}. {ch.get('title', ch.get('source', '?'))}** "
                         f"(relevance {ch.get('score', 0):.2f})")
            lines.append(f"> {snippet}")
            lines.append("")
        lines.append("_Local demo provider: verbatim quotes only. "
                     "Set PROVIDER=openai for composed answers._")
        return "\n".join(lines).strip()

    # -- extraction side (NARROW, schema-driven) ------------------------
    def extract_fields(self, pages, schema):
        out = {}
        for field in schema:
            kind = field["kind"]
            if kind == "table":
                out[field["name"]] = self._extract_table(pages, field)
            else:
                out[field["name"]] = self._extract_line(pages, field)
        return out

    def _extract_line(self, pages, field):
        label = field["label"]
        pat = re.compile(rf"^{re.escape(label)}\s*:\s*(.+?)\s*$",
                         re.MULTILINE | re.IGNORECASE)
        cont_stop = re.compile(r"^\s*([A-Za-z][A-Za-z0-9 .()/'\-–]*\s*:|[-•]\s+)")
        # A next line that is a complete standalone sentence (starts
        # uppercase, ends with terminal punctuation) is not a wrapped
        # continuation — e.g. disclaimer lines after an address.
        sentence_end = re.compile(r"^[A-Z].*[.!?]$")
        for pg in pages:
            m = pat.search(pg["text"])
            if m:
                # PDFs wrap long lines visually; join continuation lines
                # that don't start a new label or table row.
                raw = m.group(1).strip()
                lines = pg["text"].splitlines()
                try:
                    idx = next(i for i, ln in enumerate(lines)
                               if m.group(0) in ln)
                except StopIteration:
                    idx = None
                if idx is not None:
                    for ln in lines[idx + 1:]:
                        if not ln.strip() or cont_stop.match(ln):
                            break
                        # Stop before a standalone sentence (disclaimer
                        # etc.); keep joining mid-phrase wraps, which
                        # typically end with a comma or a lowercase word.
                        if not raw.endswith(",") and sentence_end.match(ln.strip()):
                            break
                        raw += " " + ln.strip()
                if not raw:
                    return {"value": None, "page": pg["page"],
                            "status": "uncertain",
                            "citation": f"p{pg['page']}: {label} (empty value)"}
                if field["kind"] in ("number", "money", "percent"):
                    parsed = _parse_number(raw)
                    if parsed is None:
                        return {"value": None, "page": pg["page"],
                                "status": "uncertain",
                                "citation": f"p{pg['page']}: {label}: {raw} "
                                            f"(unparseable)"}
                    return _ok(parsed, pg["page"], f"p{pg['page']}: {label}: {raw}")
                return _ok(raw, pg["page"], f"p{pg['page']}: {label}: {raw}")
        return _not_found(label)

    def _extract_table(self, pages, field):
        label = field["label"]
        columns = field.get("columns", [])
        header_pat = re.compile(rf"^{re.escape(label)}\s*:?\s*$",
                                re.MULTILINE | re.IGNORECASE)
        row_pat = re.compile(r"^\s*[-•]\s*(.+?)\s*$")
        stop_pat = re.compile(r"^[A-Za-z][A-Za-z0-9 .()/'\-–]*\s*:\s*\S")
        for pg in pages:
            m = header_pat.search(pg["text"])
            if not m:
                continue
            rows = []
            for line in pg["text"][m.end():].splitlines():
                stripped = line.strip()
                if not stripped:
                    if rows:
                        break
                    continue
                rm = row_pat.match(line)
                if rm:
                    cells = [c.strip() for c in rm.group(1).split("|")]
                    if columns and len(cells) == len(columns):
                        row = {}
                        for col, cell in zip(columns, cells):
                            parsed = _parse_number(cell)
                            row[col] = parsed if parsed is not None else cell
                        rows.append(row)
                    else:
                        rows.append({"raw": rm.group(1).strip()})
                    continue
                if stop_pat.match(line):
                    break
            if rows:
                return _ok(rows, pg["page"],
                           f"p{pg['page']}: {label} ({len(rows)} rows)")
        return _not_found(label)


# ---------------------------------------------------------------------------
# OpenAI provider
# ---------------------------------------------------------------------------

class OpenAIProvider(Provider):
    name = "openai"

    def __init__(self, api_key=None, embed_model="text-embedding-3-small",
                 chat_model="gpt-4o-mini"):
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("pip install openai") from exc
        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        self._client = OpenAI(api_key=key)
        self._embed_model = embed_model
        self._chat_model = chat_model

    def embed(self, texts):
        resp = self._client.embeddings.create(model=self._embed_model,
                                              input=texts)
        return [d.embedding for d in resp.data]

    def answer(self, question, chunks, history):
        context = "\n\n".join(f"[Source: {c.get('title', c.get('source', '?'))}]\n{c['text']}"
                              for c in chunks)
        messages = [{
            "role": "system",
            "content": ("Answer ONLY using the excerpts below. Cite each fact "
                        "with the source title in brackets. If the excerpts "
                        "don't contain the answer, say exactly: "
                        "\"I don't know based on the indexed documents.\""),
        }]
        for turn in (history or [])[-6:]:
            messages.append({"role": turn["role"], "content": turn["content"]})
        messages.append({"role": "user",
                         "content": f"Excerpts:\n{context}\n\nQuestion: {question}"})
        resp = self._client.chat.completions.create(
            model=self._chat_model, messages=messages, temperature=0.2)
        return (resp.choices[0].message.content or "").strip()

    def extract_fields(self, pages, schema):
        import json as _json
        spec = "\n".join(
            f"- {f['name']} ({f['kind']}): {f['label']}" + (
                f"  columns: {', '.join(f['columns'])}" if f.get("columns") else ""
            ) for f in schema)
        system = (
            "Extract the listed fields from the document. Rules:\n"
            '1. Return ONLY JSON: {"fields": [{"name": str, "value": ..., '
            '"page": int|null, "status": "ok|not_found|uncertain", '
            '"citation": str}]}.\n'
            "2. EVERY field needs a page number and a short citation quote, "
            'or status "not_found" with value null. NEVER invent a value.\n'
            "3. Report figures exactly as stated; do not do arithmetic.\n"
            f"Fields:\n{spec}"
        )
        doc = "\n\n".join(f"--- PAGE {p['page']} ---\n{p['text'][:4000]}"
                          for p in pages)
        resp = self._client.chat.completions.create(
            model=self._chat_model,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": f"Extract the fields.\n\n{doc}"}],
            temperature=0)
        data = _json.loads(resp.choices[0].message.content)
        names = {f["name"] for f in schema}
        out = {}
        for f in data.get("fields", []):
            if f.get("name") not in names:
                continue
            out[f["name"]] = {
                "value": f.get("value"), "page": f.get("page"),
                "status": f.get("status", "uncertain"),
                "citation": str(f.get("citation", ""))[:200],
            }
        for f in schema:
            out.setdefault(f["name"], _not_found(f["label"]))
        return out


PROVIDER_NAME = os.environ.get("PROVIDER", "local").lower()


def get_provider(name=None):
    selected = (name or os.environ.get("PROVIDER", "local")).lower()
    if selected == "openai":
        return OpenAIProvider()
    if selected == "local":
        return LocalProvider()
    raise ValueError(f"Unknown provider {selected!r}; expected 'openai'|'local'")
