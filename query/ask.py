"""ask: the fused query path.

Orchestration:
  1. route the question (router) -> structured | rag | both
  2. resolve entities via the entity store
  3. structured: execute the intent against the extractions table
     rag:        retrieve top-k chunks from Chroma behind a similarity gate
  4. permission filter (the enforcement point) on everything retrieved
  5. fuse + shared honesty layer: if nothing was found above threshold,
     answer "I don't know based on the indexed documents."

Returns {"route", "answer", "citations", "table"?, "knew"}.
"""
from __future__ import annotations

import logging
from pathlib import Path

import chromadb

from connectors.docs_connector import COLLECTION
from query import permissions, router

log = logging.getLogger("deal_copilot.ask")

REFUSAL = "I don't know based on the indexed documents."
RAG_THRESHOLD = 0.12  # min cosine similarity for a chunk to count
RAG_TOP_K = 5


def _ensure_idf(chroma_dir, provider):
    """Make sure query-time embeddings live in the same vector space as the
    stored ones. Prefers the fitted state saved by scripts/build_index.py;
    falls back to fitting from the stored documents."""
    from providers import _idf, fit_corpus, load_state
    if _idf is not None:
        return
    state_path = Path(chroma_dir).parent / "tfidf.json"
    if load_state(state_path):
        return
    try:
        coll = chromadb.PersistentClient(path=str(chroma_dir)) \
            .get_collection(COLLECTION)
        docs = coll.get(include=["documents"])["documents"] or []
    except Exception:
        docs = []
    fit_corpus(docs or ["deal copilot empty corpus"])


def _format_value(value):
    if isinstance(value, float):
        return f"${value:,.0f}" if value >= 1000 else f"{value:g}"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, list):
        return "; ".join(
            ", ".join(f"{k}: {v}" for k, v in r.items())
            if isinstance(r, dict) else str(r) for r in value)
    return str(value)


def _field_answer(prop_name, field_label, rec, source_file):
    if not rec or rec.get("status") != "ok":
        return None, None
    answer = (f"{prop_name} — {field_label}: "
              f"{_format_value(rec['value'])}")
    citation = {"source": source_file, "page": rec.get("page"),
                "quote": rec.get("citation", "")}
    return answer, citation


class Asker:
    def __init__(self, store, chroma_dir, provider=None, user=None):
        from providers import get_provider
        self.store = store
        self.chroma_dir = Path(chroma_dir)
        self.provider = provider or get_provider()
        self.user = user or permissions.DEMO_USER

    # -- structured intents -------------------------------------------
    def _latest_extraction(self, property_id, doc_type):
        recs = self.store.get_extractions(property_id=property_id,
                                          doc_type=doc_type)
        return recs[0] if recs else None

    def _run_intent(self, intent):
        """Returns (answer_fragments, citations, table_or_None)."""
        frags, cites = [], []
        table = None
        if not intent:
            return frags, cites, table
        itype = intent.get("type")

        if itype == "lease_expiry":
            prop = intent.get("property")
            rec = self._latest_extraction(prop["id"], "lease") if prop else None
            fields = rec["fields"] if rec else {}
            exp = fields.get("expiration_date")
            ans, cit = _field_answer(
                prop["name"] if prop else "?", "lease expiration",
                exp, rec["source_file"] if rec else "?")
            if ans:
                frags.append(ans)
                cites.append(cit)
                notice = fields.get("renewal_notice_date")
                if notice and notice.get("status") == "ok":
                    frags.append(f"Renewal notice deadline: {notice['value']}")
                    cites.append({"source": rec["source_file"],
                                  "page": notice.get("page"),
                                  "quote": notice.get("citation", "")})

        elif itype in ("lease_field", "om_field"):
            prop = intent.get("property")
            field = intent.get("field")
            if not prop or not field:
                return frags, cites, table  # nothing structured to answer
            doc_type = "lease" if itype == "lease_field" else "om"
            rec = self._latest_extraction(prop["id"], doc_type)
            fields = rec["fields"] if rec else {}
            ans, cit = _field_answer(
                prop["name"], field.replace("_", " "),
                fields.get(field), rec["source_file"] if rec else "?")
            if ans:
                frags.append(ans)
                cites.append(cit)

        elif itype == "compare":
            field, doc_type = intent.get("field"), intent.get("doc_type")
            props = intent.get("properties") or []
            if not props:
                # "across properties": every property with this doc type
                for p in self.store.list_properties():
                    if self._latest_extraction(p["id"], doc_type):
                        props.append({"id": p["id"],
                                      "name": p["canonical_name"]})
            rows = []
            for p in props:
                rec = self._latest_extraction(p["id"], doc_type)
                fields = rec["fields"] if rec else {}
                frec = fields.get(field) if field else None
                if frec and frec.get("status") == "ok":
                    rows.append({"property": p["name"],
                                 (field or "value").replace("_", " "):
                                     _format_value(frec["value"])})
                    cites.append({"source": rec["source_file"],
                                  "page": frec.get("page"),
                                  "quote": frec.get("citation", "")})
            if rows:
                table = {"columns": list(rows[0].keys()), "rows": rows}
                frags.append(
                    f"Comparison of {(field or 'value').replace('_', ' ')} "
                    f"across {len(rows)} propert"
                    f"{'y' if len(rows) == 1 else 'ies'} (see table).")

        cites = permissions.filter_for_user(self.user, cites)
        return frags, cites, table

    # -- RAG ------------------------------------------------------------
    def _rag(self, question):
        _ensure_idf(self.chroma_dir, self.provider)
        try:
            coll = chromadb.PersistentClient(
                path=str(self.chroma_dir)).get_collection(COLLECTION)
        except Exception:
            return [], []
        qvec = self.provider.embed([question])[0]
        res = coll.query(query_embeddings=[qvec], n_results=RAG_TOP_K,
                         include=["documents", "metadatas", "distances"])
        docs = res["documents"][0] if res["documents"] else []
        metas = res["metadatas"][0] if res["metadatas"] else []
        dists = res["distances"][0] if res["distances"] else []
        chunks = []
        for doc, meta, dist in zip(docs, metas, dists):
            sim = 1.0 - float(dist)  # cosine distance -> similarity
            if sim >= RAG_THRESHOLD:
                chunks.append({"text": doc, "source": meta.get("source", "?"),
                               "title": meta.get("source", "?"),
                               "score": sim})
        chunks = permissions.filter_for_user(self.user, chunks)
        return chunks, chunks

    # -- fused ask -------------------------------------------------------
    def ask(self, question: str, history=None) -> dict:
        routed = router.route(question, self.store)
        route_, intent = routed["route"], routed["intent"]
        log.info("route=%s intent=%s entities=%s", route_, intent,
                 [e["name"] for e in routed["entities"]])

        frags, cites, table = [], [], None
        if route_ in ("structured", "both"):
            sf, sc, table = self._run_intent(intent)
            frags.extend(sf)
            cites.extend(sc)

        rag_answer = ""
        if route_ in ("rag", "both"):
            chunks, _ = self._rag(question)
            if chunks:
                rag_answer = self.provider.answer(question, chunks,
                                                  history or [])

        knew = bool(frags) or bool(rag_answer)
        if not knew:
            return {"route": route_, "answer": REFUSAL, "citations": [],
                    "knew": False}

        parts = []
        if frags:
            parts.append("\n".join(frags))
        if rag_answer:
            parts.append(rag_answer)
        out = {"route": route_, "answer": "\n\n".join(parts),
               "citations": cites, "knew": True}
        if table:
            out["table"] = table
        return out
