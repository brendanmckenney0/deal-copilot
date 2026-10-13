"""Build the full demo index from scratch.

Wipes data/entities.db and data/chroma, then:
  1. seeds the fictional property registry (entities.seed)
  2. ingests data/corpus/*.md via DocsConnector (chunk mode)
  3. ingests the sample PDFs via DocIntelConnector (extract mode)

Idempotent: safe to re-run any time. Run scripts/generate_docs.py first.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from connectors.docintel_connector import DocIntelConnector  # noqa: E402
from connectors.docs_connector import DocsConnector  # noqa: E402
from entities.seed import seed  # noqa: E402
from entities.store import EntityStore  # noqa: E402
from providers import ensure_fitted, get_provider, save_state  # noqa: E402

DATA = ROOT / "data"
DB = DATA / "entities.db"
CHROMA = DATA / "chroma"
PDFS = DATA / "pdfs"
TFIDF = DATA / "tfidf.json"


def main() -> None:
    if DB.exists():
        DB.unlink()
    if CHROMA.exists():
        shutil.rmtree(CHROMA)
    if TFIDF.exists():
        TFIDF.unlink()

    provider = get_provider()

    # Fit the TF-IDF space ONCE over everything to be ingested, then save
    # it so the server/eval embed queries in the same space.
    corpus_texts = [p.read_text(encoding="utf-8")
                    for p in sorted((ROOT / "data" / "corpus").glob("*.md"))]
    pdf_texts = []
    try:
        from pypdf import PdfReader
        for pdf in ["om_maple_grove.pdf", "lease_bluefin.pdf"]:
            reader = PdfReader(str(PDFS / pdf))
            pdf_texts.append("\n\n".join((pg.extract_text() or "")
                                         for pg in reader.pages))
    except Exception:
        pass
    ensure_fitted(corpus_texts + pdf_texts)
    save_state(TFIDF)

    store = EntityStore(str(DB))
    seed(store)
    print(f"seeded {len(store.list_properties())} properties")

    docs = DocsConnector(ROOT / "data" / "corpus", CHROMA, provider)
    docs.authenticate({})
    r = docs.ingest()
    print(f"corpus: {r['files']} files -> {r['chunks']} chunks "
          f"[{r['collection']}]")

    for pdf, doc_type in [("om_maple_grove.pdf", "om"),
                          ("lease_bluefin.pdf", "lease")]:
        di = DocIntelConnector(PDFS / pdf, doc_type, store, CHROMA, provider)
        di.authenticate({})
        r = di.ingest()
        print(f"{pdf}: {r['fields_extracted']} fields ok, "
              f"property_id={r['property_id']}, gaps={len(r['gaps'])}, "
              f"chunks={r['chunks']}")
        for w in r["reconciliation"]:
            print(f"  reconcile [{w['status']}] {w['check']}: {w['detail']}")
        for g in r["gaps"]:
            print(f"  gap [{g['status']}] {g['field']}: {g['question']}")

    print("index build complete")


if __name__ == "__main__":
    main()
