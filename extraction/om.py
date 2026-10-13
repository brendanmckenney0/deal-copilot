"""OM (offering memorandum) schema + extractor.

~13 fields an underwriter needs from a multifamily OM: identity, unit
mix, income, pricing, expenses, sale terms. Every field carries
{value, page, status, citation} — never an invented number.
"""
from __future__ import annotations

from extraction import guardrails, registry

OM_SCHEMA = [
    {"name": "property_name", "label": "Property Name", "kind": "text"},
    {"name": "address", "label": "Address", "kind": "text"},
    {"name": "total_units", "label": "Total Units", "kind": "number"},
    {"name": "unit_mix", "label": "Unit Mix", "kind": "table",
     "columns": ["unit_type", "count", "avg_rent"]},
    {"name": "avg_rent", "label": "Average Rent", "kind": "money"},
    {"name": "occupancy_pct", "label": "Occupancy", "kind": "percent"},
    {"name": "t12_noi", "label": "T-12 NOI", "kind": "money"},
    {"name": "proforma_noi", "label": "Proforma NOI", "kind": "money"},
    {"name": "asking_price", "label": "Asking Price", "kind": "money"},
    {"name": "cap_rate_pct", "label": "Cap Rate", "kind": "percent"},
    {"name": "expenses_breakdown", "label": "Expenses Breakdown",
     "kind": "table", "columns": ["category", "amount"]},
    {"name": "total_expenses", "label": "Total Expenses", "kind": "money"},
    {"name": "sale_terms", "label": "Sale Terms", "kind": "text"},
]


def extract_om(pages, provider):
    """Run the provider's field extractor, then deterministic reconciliation."""
    fields = provider.extract_fields(pages, OM_SCHEMA)
    fields["_reconciliation"] = guardrails.reconcile("om", fields)
    return fields


registry.register("om", OM_SCHEMA, extract_om)
