"""Lease abstraction schema + extractor.

~10 fields an asset manager needs at a glance from a commercial lease:
who, where, how long, how much, what can change, who guarantees it.
Critical-date fields (expiration_date, renewal_notice_date) drive the
monitoring use case — "which tenants expire in 2027?"
"""
from __future__ import annotations

from extraction import guardrails, registry

LEASE_SCHEMA = [
    {"name": "tenant_name", "label": "Tenant Name", "kind": "text"},
    {"name": "premises_address", "label": "Premises Address", "kind": "text"},
    {"name": "commencement_date", "label": "Commencement Date", "kind": "text"},
    {"name": "expiration_date", "label": "Expiration Date", "kind": "text"},
    {"name": "base_rent_annual", "label": "Base Rent (Annual)", "kind": "money"},
    {"name": "escalation_terms", "label": "Escalation Terms", "kind": "text"},
    {"name": "renewal_options", "label": "Renewal Options", "kind": "text"},
    {"name": "renewal_notice_date", "label": "Renewal Notice Date",
     "kind": "text"},
    {"name": "guarantor", "label": "Guarantor", "kind": "text"},
    {"name": "permitted_use", "label": "Permitted Use", "kind": "text"},
]


def extract_lease(pages, provider):
    fields = provider.extract_fields(pages, LEASE_SCHEMA)
    fields["_reconciliation"] = guardrails.reconcile("lease", fields)
    return fields


registry.register("lease", LEASE_SCHEMA, extract_lease)
