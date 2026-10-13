"""Plugin registry for structured document extraction.

register(doc_type, schema, extractor) plugs in a new document type.
get(doc_type) -> (schema, extractor) for the pipeline.

Schema = list of {"name", "label", "kind", "columns"?} where kind is one of
text | number | money | percent | table. "columns" is required for tables.

Every extracted field returns a record:
  {"value", "page", "status": "ok|not_found|uncertain", "citation"}
"""
from __future__ import annotations

_REGISTRY: dict[str, dict] = {}


def register(doc_type: str, schema: list[dict], extractor) -> None:
    """extractor(pages, provider) -> {field_name: field_record}."""
    for f in schema:
        missing = {"name", "label", "kind"} - set(f)
        if missing:
            raise ValueError(f"schema field {f} missing {missing}")
        if f["kind"] not in ("text", "number", "money", "percent", "table"):
            raise ValueError(f"bad kind {f['kind']!r} for field {f['name']!r}")
        if f["kind"] == "table" and not f.get("columns"):
            raise ValueError(f"table field {f['name']!r} needs 'columns'")
    _REGISTRY[doc_type] = {"schema": schema, "extractor": extractor}


def get(doc_type: str):
    try:
        entry = _REGISTRY[doc_type]
    except KeyError:
        raise ValueError(f"unknown doc_type {doc_type!r}; "
                         f"registered: {sorted(_REGISTRY)}") from None
    return entry["schema"], entry["extractor"]


def registered_types() -> list[str]:
    return sorted(_REGISTRY)


def money_fields(doc_type: str) -> list[str]:
    """Names of fields with kind 'money' for a doc type (3x eval weight)."""
    schema, _ = get(doc_type)
    return [f["name"] for f in schema if f["kind"] == "money"]


# Built-in document types register on import.
from extraction import om as _om  # noqa: E402,F401
from extraction import lease as _lease  # noqa: E402,F401
