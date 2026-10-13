"""Shared extraction guardrails.

Principles:
- NOT_FOUND discipline: a missing value is reported as not_found, NEVER
  invented. "uncertain" marks a value that was found but couldn't be
  parsed cleanly.
- Per-field page citation required: every "ok" field carries the page
  number and a short quote of the source line.
- Deterministic reconciliation checks run in code; mismatches are
  flagged as warnings, never silently "fixed".
- gap_report() turns missing/uncertain fields into follow-up questions.
"""
from __future__ import annotations

import re


def _ok_value(fields: dict, name: str):
    f = fields.get(name, {})
    return f.get("value") if f.get("status") == "ok" else None


def _to_float(v):
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        cleaned = v.replace("$", "").replace(",", "").strip().rstrip("%")
        cleaned = re.split(r"\s", cleaned)[0]
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def validate(fields: dict, schema: list[dict]) -> list[dict]:
    """Structural integrity: every schema field present, valid status,
    and page citations on ok fields."""
    issues = []
    for f in schema:
        name = f["name"]
        rec = fields.get(name)
        if not isinstance(rec, dict):
            issues.append({"severity": "error",
                           "message": f"field '{name}' missing from result"})
            continue
        if rec.get("status") not in ("ok", "not_found", "uncertain"):
            issues.append({"severity": "error",
                           "message": f"field '{name}' has invalid status"})
        if rec.get("status") == "ok" and not rec.get("page"):
            issues.append({"severity": "warn",
                           "message": f"field '{name}' ok but has no page citation"})
    return issues


def reconcile(doc_type: str, fields: dict) -> list[dict]:
    """Deterministic cross-checks. Each: {"check","status","detail"} with
    status in pass|warn|skip. Warnings are surfaced, never auto-fixed."""
    if doc_type == "om":
        return _reconcile_om(fields)
    if doc_type == "lease":
        return _reconcile_lease(fields)
    return [{"check": "unknown_doc_type", "status": "skip",
             "detail": f"no checks defined for {doc_type!r}"}]


def _reconcile_om(fields: dict) -> list[dict]:
    checks = []

    # unit mix counts should sum to the stated total
    mix, total = _ok_value(fields, "unit_mix"), _ok_value(fields, "total_units")
    if isinstance(mix, list) and total is not None:
        s = sum(_to_float(r.get("count")) or 0 for r in mix if isinstance(r, dict))
        checks.append({"check": "unit_mix_sums_to_total",
                       "status": "pass" if s == _to_float(total) else "warn",
                       "detail": f"mix sums to {s:g} units vs stated total {total}"})
    else:
        checks.append({"check": "unit_mix_sums_to_total", "status": "skip",
                       "detail": "unit mix or total units not available"})

    # cap rate ≈ t12_noi / asking_price
    noi = _to_float(_ok_value(fields, "t12_noi"))
    price = _to_float(_ok_value(fields, "asking_price"))
    cap = _to_float(_ok_value(fields, "cap_rate_pct"))
    if noi and price and cap is not None:
        implied = noi / price * 100
        checks.append({"check": "cap_rate_math",
                       "status": "pass" if abs(implied - cap) <= 0.25 else "warn",
                       "detail": f"NOI/price implies {implied:.2f}% "
                                 f"vs stated {cap:.2f}%"})
    else:
        checks.append({"check": "cap_rate_math", "status": "skip",
                       "detail": "NOI, price, or cap rate not available"})

    # expense line items should sum to the stated total
    brk = _ok_value(fields, "expenses_breakdown")
    tot = _to_float(_ok_value(fields, "total_expenses"))
    if isinstance(brk, list) and tot:
        s = sum(_to_float(r.get("amount")) or 0 for r in brk
                if isinstance(r, dict))
        checks.append({"check": "expenses_sum_to_total",
                       "status": "pass" if abs(s - tot) <= 1 else "warn",
                       "detail": f"line items sum to ${s:,.0f} "
                                 f"vs stated total ${tot:,.0f}"})
    else:
        checks.append({"check": "expenses_sum_to_total", "status": "skip",
                       "detail": "expenses breakdown or total not available"})
    return checks


def _reconcile_lease(fields: dict) -> list[dict]:
    checks = []
    tenant = _ok_value(fields, "tenant_name")
    rent = _ok_value(fields, "base_rent_annual")
    checks.append({"check": "base_rent_present_if_tenant",
                   "status": ("pass" if rent else "warn") if tenant else "skip",
                   "detail": (f"tenant '{tenant}' with annual base rent "
                              f"${_to_float(rent):,.0f}" if tenant and rent else
                              f"tenant '{tenant}' present but base rent missing"
                              if tenant else "no tenant extracted")})

    comm = _ok_value(fields, "commencement_date")
    exp = _ok_value(fields, "expiration_date")
    if comm and exp:
        checks.append({"check": "term_order",
                       "status": "pass" if str(comm) < str(exp) else "warn",
                       "detail": f"term {comm} → {exp}"})
    else:
        checks.append({"check": "term_order", "status": "skip",
                       "detail": "commencement/expiration not both available"})

    notice = _ok_value(fields, "renewal_notice_date")
    checks.append({"check": "renewal_notice_date_present",
                   "status": "pass" if notice else "warn",
                   "detail": (f"renewal notice deadline {notice}" if notice
                              else "no renewal notice date — critical date "
                                   "cannot be tracked")})
    return checks


GAP_QUESTIONS = {
    "t12_noi": "Request the trailing-twelve-month operating statement.",
    "asking_price": "Confirm the asking price and whether it is firm.",
    "cap_rate_pct": "Ask what cap rate the pricing is based on.",
    "expenses_breakdown": "Request a detailed operating expense breakdown.",
    "expiration_date": "Confirm the lease expiration date — critical date.",
    "renewal_options": "Confirm renewal options and notice requirements.",
    "renewal_notice_date": "Confirm the renewal notice deadline — critical date.",
    "base_rent_annual": "Confirm current base rent.",
    "guarantor": "Confirm whether a guaranty exists and who the guarantor is.",
}


def gap_report(fields: dict, schema: list[dict] | None = None) -> list[dict]:
    """Missing/uncertain fields -> follow-up questions for the analyst."""
    labels = {f["name"]: f["label"] for f in (schema or [])}
    gaps = []
    for name, rec in fields.items():
        if name.startswith("_") or not isinstance(rec, dict):
            continue
        if rec.get("status") in ("not_found", "uncertain"):
            label = labels.get(name, name)
            gaps.append({
                "field": name,
                "status": rec.get("status"),
                "question": GAP_QUESTIONS.get(
                    name, f"Confirm {label} — not stated in the document."),
            })
    return gaps
