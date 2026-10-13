"""Heuristic query router.

Returns {"route": "structured"|"rag"|"both", "intent": ..., "entities": [...]}.

Rules:
- aggregation/comparison keywords (average, compare, total, how many,
  highest, lowest) -> structured
- "what did X say", "summarize", "according to" -> rag
- entity name present + descriptive question, or "compare" with entities
  -> both
- default -> rag

Intent templates for structured:
  lease_expiry(property) | lease_field(property, field)
  | om_field(property, field) | compare(field, properties)

Deterministic and demo-scale; a production router would be learned with
the eval sets as training signal.
"""
from __future__ import annotations

import re

AGG_RE = re.compile(
    r"\b(average|avg|total|sum|how many|compare|comparison|highest|lowest)\b",
    re.IGNORECASE)
RAG_RE = re.compile(
    r"\b(what did .* say|what does .* say|according to|summariz\w*)\b",
    re.IGNORECASE)
FIELD_RE = re.compile(
    r"\b(expir\w*|renewal|cap rate|asking price|noi|occupancy|units?"
    r"|base rent|rent|tenant|guarantor|permitted use|escalation"
    r"|commencement|sale terms|expenses)\b",
    re.IGNORECASE)

LEASE_FIELD_RES = [
    (r"\btenant\b", "tenant_name"),
    (r"\bguarantor\b", "guarantor"),
    (r"\bpermitted use\b", "permitted_use"),
    (r"\bescalation\w*\b", "escalation_terms"),
    (r"\brenewal\b", "renewal_options"),
    (r"\bcommencement\b", "commencement_date"),
    (r"\bexpir\w*\b", "expiration_date"),
    (r"\bbase rent\b", "base_rent_annual"),
]
OM_FIELD_RES = [
    (r"\basking price\b", "asking_price"),
    (r"\bcap rate\b", "cap_rate_pct"),
    (r"\bproforma\b", "proforma_noi"),
    (r"\bnoi\b", "t12_noi"),
    (r"\boccupancy\b", "occupancy_pct"),
    (r"\bunits?\b", "total_units"),
    (r"\bexpenses\b", "total_expenses"),
    (r"\bsale terms\b", "sale_terms"),
    (r"\baddress\b", "address"),
    (r"\bprice\b", "asking_price"),
    (r"\brent\b", "avg_rent"),
]


def _detect_field(question: str):
    q = question.lower()
    for pat, fname in LEASE_FIELD_RES:
        if re.search(pat, q):
            return ("lease", fname)
    for pat, fname in OM_FIELD_RES:
        if re.search(pat, q):
            return ("om", fname)
    return (None, None)


def route(question: str, store) -> dict:
    """Classify the question. store = EntityStore (for entity detection)."""
    q = question.lower()
    entity_ids = store.find_aliases_in(question)
    entities = []
    for pid in entity_ids:
        prop = store.get_property(pid)
        if prop:
            entities.append({"id": pid, "name": prop["canonical_name"]})

    agg_hit = bool(AGG_RE.search(q))
    rag_hit = bool(RAG_RE.search(q))
    field_hit = bool(FIELD_RE.search(q))

    if rag_hit and not agg_hit:
        route_ = "rag"
    elif agg_hit and entities:
        route_ = "both"
    elif agg_hit:
        route_ = "structured"
    elif entities and re.search(
            r"\b(tell me about|describe|explain|overview)\b", q):
        route_ = "both"
    elif field_hit and entities:
        route_ = "structured"
    elif entities and re.search(r"\b(what|which|who)\b", q):
        route_ = "both"
    else:
        route_ = "rag"

    intent = _build_intent(question, route_, entities)
    return {"route": route_, "intent": intent, "entities": entities}


def _build_intent(question: str, route_: str, entities: list[dict]):
    q = question.lower()
    if route_ == "rag":
        return None
    first = entities[0] if entities else None

    if re.search(r"\bexpir\w*\b", q) or "when does" in q and "lease" in q:
        if first:
            return {"type": "lease_expiry", "property": first}
        return {"type": "lease_expiry", "property": None}

    if "compare" in q or "comparison" in q:
        doc_type, field = _detect_field(question)
        return {"type": "compare", "field": field,
                "doc_type": doc_type, "properties": entities}

    doc_type, field = _detect_field(question)
    if doc_type == "lease" and first:
        return {"type": "lease_field", "property": first, "field": field}
    if doc_type == "om" and first:
        return {"type": "om_field", "property": first, "field": field}
    if first:
        # entity + field-ish question, default to OM record
        return {"type": "om_field", "property": first, "field": field}
    return None
