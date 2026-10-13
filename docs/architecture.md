# deal-copilot — architecture

A fused system: **RAG over documents** (Atlas-style) + **structured
document extraction** (DealScreener-style), behind one query router,
one entity store, and one honesty layer.

```
Sources: PDFs (OMs, leases), markdown corpus
                    │
        ┌───────────┴───────────┐
        ▼                       ▼
  Ingestion mode A:       Ingestion mode B:
  chunk + embed           extract + structure
  (DocsConnector)         (DocIntelConnector)
        │                       │
        ▼                       ▼
  Chroma vector store     Entity store (SQLite)
  (passages, citations)   (properties, aliases,
                           extractions)
        │                       │
        └───────────┬───────────┘
                    ▼
          Query router (heuristic)
          structured | rag | both
                    │
        ┌───────────┴───────────┐
        ▼                       ▼
  Structured intents      RAG retrieval
  (lease_expiry,          (similarity-gated,
   lease_field,            permission-filtered)
   om_field, compare)
                    │
                    ▼
          Fused answer + citations
          + shared honesty layer
          ("I don't know" / NOT_FOUND)
```

## Connectors (`connectors/`)

`BaseConnector` defines the interface: `authenticate`, `discover`,
`fetch_changes`, `ingest`, plus an `ingest_mode` flag (`"chunk"` or
`"extract"`). A connector×credential pairing is a small config object
(demo-scale; production would add OAuth and per-pair schedules).

- **DocsConnector** (mode=chunk): ingests a directory of markdown into
  Chroma via `chunk_text` (900-char word-safe windows).
- **DocIntelConnector** (mode=extract): takes one PDF, extracts pages
  with pypdf, runs the extraction registry for its `doc_type`, stores
  the structured record in the entity store, **and** chunks the raw
  PDF text into Chroma — so one document is queryable both ways.

## Extraction registry (`extraction/`)

Schema-driven and pluggable: `register(doc_type, schema, extractor)`.
Two document types ship:

- **om** — offering memorandum fields (NOI, cap rate, unit mix,
  rents, expenses, sale terms).
- **lease** — lease-abstraction fields (tenant, premises, dates, base
  rent, escalations, renewal options + notice date, guarantor,
  permitted use).

Every field returns `{value, page, status, citation}` where status is
`ok | not_found | uncertain`. Missing data is an explicit `not_found`,
never a guess. `guardrails.py` adds deterministic reconciliation in
code (unit sums, cap-rate math, term ordering) and a gap report with
follow-up questions.

## Entity store (`entities/`)

SQLite with three tables: `properties` (canonical registry),
`aliases` (normalized alias → property), `extractions` (structured
records per document). `EntityStore.resolve(name)` is deterministic:
normalized exact alias match, then longest-alias substring fallback.
This is demo-scale entity resolution — the auditable foundation; a
production version adds LLM-assisted resolution with human
confirmation for ambiguous matches.

## Query router (`query/router.py`)

Heuristic classifier returning `{route, intent, entities}`:

- aggregation/comparison keywords ("average", "compare", "how many")
  → **structured**
- "what did X say", "summarize", "according to" → **rag**
- entity + descriptive question → **both**

Structured intents (`lease_expiry`, `lease_field`, `om_field`,
`compare`) execute deterministically against the extractions table.
RAG retrieval is similarity-gated and permission-filtered
(`query/permissions.py` is the enforcement point; demo uses a single
demo user).

## Providers (`providers.py`)

One `PROVIDER=openai|local` abstraction for embeddings, generation,
and extraction. The local provider is deliberately narrow (TF-IDF
embeddings, regex extractors tuned to the sample documents) —
documented as such; it exists so the demo runs with no key and no
cost. The OpenAI provider is the real path.

## Honesty

One shared layer: structured fields use `not_found`, RAG answers use
"I don't know based on the indexed documents." Nothing is ever
invented to fill a gap.
