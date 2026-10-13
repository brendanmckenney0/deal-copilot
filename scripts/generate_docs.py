"""Generate the fictional sample documents + ground truth.

Deterministic: fixed content, no randomness. Everything is fictional —
no real company, property, or broker data.

Outputs:
  data/pdfs/*.pdf                     (gitignored; rebuilt here)
  data/ground_truth/*.json            (tracked)
  data/corpus/*.md                    (tracked; RAG corpus)

The PDFs use simple "Label: value" lines and "- col | col | col" table
rows so the local (narrow) extractor can parse them; the markdown files
keep facts consistent with the PDFs where they overlap.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

random.seed(20261013)  # deterministic; content is fixed regardless

ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = ROOT / "data" / "pdfs"
GT_DIR = ROOT / "data" / "ground_truth"
CORPUS_DIR = ROOT / "data" / "corpus"

# ---------------------------------------------------------------- OM ----

OM_PAGES = [
    [  # page 1: cover
        "MAPLE GROVE APARTMENTS",
        "Offering Memorandum",
        "1420 Elm Street, Dayton, OH 45402",
        "Prepared October 2026 — for discussion purposes only.",
    ],
    [  # page 2: overview
        "Property Overview",
        "Property Name: Maple Grove Apartments",
        "Address: 1420 Elm Street, Dayton, OH 45402",
        "Total Units: 120",
        "Year Built: 1987; Renovated: 2019",
        "Property Type: Garden-style multifamily",
    ],
    [  # page 3: unit mix
        "Unit Mix:",
        "- 1BR | 48 | $950",
        "- 2BR | 60 | $1,250",
        "- 3BR | 12 | $1,550",
        "Average Rent: $1,160 per month",
        "Occupancy: 94%",
    ],
    [  # page 4: financials
        "Financial Summary",
        "T-12 NOI: $1,240,000",
        "Proforma NOI: $1,380,000",
        "Asking Price: $18,500,000",
        "Cap Rate: 6.70%",
    ],
    [  # page 5: expenses
        "Operating Expenses",
        "Expenses Breakdown:",
        "- Property Taxes | $210,000",
        "- Insurance | $95,000",
        "- Management | $128,000",
        "- Maintenance | $140,000",
        "- Utilities | $86,000",
        "Total Expenses: $659,000",
    ],
    [  # page 6: sale terms
        "Sale Terms",
        "Sale Terms: All-cash to seller; 60-day close; 2% earnest money "
        "deposit; buyer assumes existing service contracts.",
    ],
]

OM_GROUND_TRUTH = {
    "doc_type": "om",
    "source_file": "om_maple_grove.pdf",
    "fields": {
        "property_name": {"value": "Maple Grove Apartments", "page": 2},
        "address": {"value": "1420 Elm Street, Dayton, OH 45402", "page": 2},
        "total_units": {"value": 120, "page": 2},
        "unit_mix": {"value": [
            {"unit_type": "1BR", "count": 48, "avg_rent": 950},
            {"unit_type": "2BR", "count": 60, "avg_rent": 1250},
            {"unit_type": "3BR", "count": 12, "avg_rent": 1550}], "page": 3},
        "avg_rent": {"value": 1160, "page": 3},
        "occupancy_pct": {"value": 94, "page": 3},
        "t12_noi": {"value": 1240000, "page": 4},
        "proforma_noi": {"value": 1380000, "page": 4},
        "asking_price": {"value": 18500000, "page": 4},
        "cap_rate_pct": {"value": 6.70, "page": 4},
        "expenses_breakdown": {"value": [
            {"category": "Property Taxes", "amount": 210000},
            {"category": "Insurance", "amount": 95000},
            {"category": "Management", "amount": 128000},
            {"category": "Maintenance", "amount": 140000},
            {"category": "Utilities", "amount": 86000}], "page": 5},
        "total_expenses": {"value": 659000, "page": 5},
        "sale_terms": {"value": "All-cash to seller; 60-day close; 2% earnest "
                                "money deposit; buyer assumes existing service "
                                "contracts.", "page": 6},
    },
}

# -------------------------------------------------------------- lease ----

LEASE_PAGES = [
    [  # page 1: cover
        "LEASE ABSTRACT",
        "Tenant Name: Bluefin Coffee Roasters LLC",
        "Premises Address: Suite 120, 88 Harbor Drive, Tampa, FL 33602",
        "Abstract prepared October 2026 — for discussion purposes only.",
    ],
    [  # page 2: term
        "Lease Term",
        "Commencement Date: 2024-06-01",
        "Expiration Date: 2029-05-31",
        "Renewal Notice Date: 2028-08-31",
    ],
    [  # page 3: economics
        "Economics",
        "Base Rent (Annual): $84,000",
        "Escalation Terms: 3% annual escalations on each anniversary of the "
        "Commencement Date.",
        "Renewal Options: One (1) five-year renewal option at 95% of fair "
        "market rent.",
        "Guarantor: Maria Chen",
    ],
    [  # page 4: use
        "Permitted Use",
        "Permitted Use: Specialty coffee retail and cafe.",
    ],
]

LEASE_GROUND_TRUTH = {
    "doc_type": "lease",
    "source_file": "lease_bluefin.pdf",
    "fields": {
        "tenant_name": {"value": "Bluefin Coffee Roasters LLC", "page": 1},
        "premises_address": {"value": "Suite 120, 88 Harbor Drive, Tampa, "
                                      "FL 33602", "page": 1},
        "commencement_date": {"value": "2024-06-01", "page": 2},
        "expiration_date": {"value": "2029-05-31", "page": 2},
        "base_rent_annual": {"value": 84000, "page": 3},
        "escalation_terms": {"value": "3% annual escalations on each "
                                      "anniversary of the Commencement Date.",
                             "page": 3},
        "renewal_options": {"value": "One (1) five-year renewal option at 95% "
                                     "of fair market rent.", "page": 3},
        "renewal_notice_date": {"value": "2028-08-31", "page": 2},
        "guarantor": {"value": "Maria Chen", "page": 3},
        "permitted_use": {"value": "Specialty coffee retail and cafe.",
                          "page": 4},
    },
}

# Second Harbor Point lease — a fitness tenant, earlier expiration.
LEASE2_PAGES = [
    [
        "LEASE ABSTRACT",
        "Tenant Name: Copperline Fitness LLC",
        "Premises Address: Suite 210, 88 Harbor Drive, Tampa, FL 33602",
        "Abstract prepared October 2026 — for discussion purposes only.",
    ],
    [
        "Lease Term",
        "Commencement Date: 2023-03-01",
        "Expiration Date: 2027-11-30",
        "Renewal Notice Date: 2027-05-31",
    ],
    [
        "Economics",
        "Base Rent (Annual): $96,000",
        "Escalation Terms: 2.5% annual escalations on each anniversary of "
        "the Commencement Date.",
        "Renewal Options: One (1) five-year renewal option at 95% of fair "
        "market rent.",
        "Guarantor: David Park",
    ],
    [
        "Permitted Use",
        "Permitted Use: Fitness center and gym.",
    ],
]

LEASE2_GROUND_TRUTH = {
    "doc_type": "lease",
    "source_file": "lease_copperline.pdf",
    "fields": {
        "tenant_name": {"value": "Copperline Fitness LLC", "page": 1},
        "premises_address": {"value": "Suite 210, 88 Harbor Drive, Tampa, "
                                      "FL 33602", "page": 1},
        "commencement_date": {"value": "2023-03-01", "page": 2},
        "expiration_date": {"value": "2027-11-30", "page": 2},
        "base_rent_annual": {"value": 96000, "page": 3},
        "escalation_terms": {"value": "2.5% annual escalations on each "
                                      "anniversary of the Commencement Date.",
                             "page": 3},
        "renewal_options": {"value": "One (1) five-year renewal option at 95% "
                                     "of fair market rent.", "page": 3},
        "renewal_notice_date": {"value": "2027-05-31", "page": 2},
        "guarantor": {"value": "David Park", "page": 3},
        "permitted_use": {"value": "Fitness center and gym.", "page": 4},
    },
}

# Ironworks industrial lease.
LEASE3_PAGES = [
    [
        "LEASE ABSTRACT",
        "Tenant Name: Great Lakes Logistics Inc",
        "Premises Address: 4500 Industrial Parkway, Gary, IN 46406",
        "Abstract prepared October 2026 — for discussion purposes only.",
    ],
    [
        "Lease Term",
        "Commencement Date: 2022-04-01",
        "Expiration Date: 2028-03-31",
        "Renewal Notice Date: 2027-09-30",
    ],
    [
        "Economics",
        "Base Rent (Annual): $210,000",
        "Escalation Terms: 3% annual escalations on each anniversary of the "
        "Commencement Date.",
        "Renewal Options: Two (2) three-year renewal options at 95% of fair "
        "market rent.",
        "Guarantor: Great Lakes Holdings LLC",
    ],
    [
        "Permitted Use",
        "Permitted Use: Warehousing and light distribution.",
    ],
]

LEASE3_GROUND_TRUTH = {
    "doc_type": "lease",
    "source_file": "lease_glakes.pdf",
    "fields": {
        "tenant_name": {"value": "Great Lakes Logistics Inc", "page": 1},
        "premises_address": {"value": "4500 Industrial Parkway, Gary, "
                                      "IN 46406", "page": 1},
        "commencement_date": {"value": "2022-04-01", "page": 2},
        "expiration_date": {"value": "2028-03-31", "page": 2},
        "base_rent_annual": {"value": 210000, "page": 3},
        "escalation_terms": {"value": "3% annual escalations on each "
                                      "anniversary of the Commencement Date.",
                             "page": 3},
        "renewal_options": {"value": "Two (2) three-year renewal options at "
                                     "95% of fair market rent.", "page": 3},
        "renewal_notice_date": {"value": "2027-09-30", "page": 2},
        "guarantor": {"value": "Great Lakes Holdings LLC", "page": 3},
        "permitted_use": {"value": "Warehousing and light distribution.",
                          "page": 4},
    },
}

# Second OM — Harbor Point mixed-use, so cross-property OM comparison
# has two rows. Reconciliation must hold: unit counts sum to 14,
# 905250/12750000 = 7.10% cap, expenses sum to 522000.
OM2_PAGES = [
    [
        "HARBOR POINT",
        "Offering Memorandum",
        "88 Harbor Drive, Tampa, FL 33602",
        "Prepared October 2026 — for discussion purposes only.",
    ],
    [
        "Property Overview",
        "Property Name: Harbor Point",
        "Address: 88 Harbor Drive, Tampa, FL 33602",
        "Total Units: 14",
        "Year Built: 2016",
        "Property Type: Mixed-use retail and office",
    ],
    [
        "Unit Mix:",
        "- Retail | 8 | $2,400",
        "- Office | 6 | $3,100",
        "Average Rent: $2,700 per month",
        "Occupancy: 92%",
    ],
    [
        "Financial Summary",
        "T-12 NOI: $905,250",
        "Proforma NOI: $980,000",
        "Asking Price: $12,750,000",
        "Cap Rate: 7.10%",
    ],
    [
        "Operating Expenses",
        "Expenses Breakdown:",
        "- Property Taxes | $180,000",
        "- Insurance | $72,000",
        "- Management | $96,000",
        "- Maintenance | $110,000",
        "- Utilities | $64,000",
        "Total Expenses: $522,000",
    ],
    [
        "Sale Terms",
        "Sale Terms: 1031 exchange considered; 45-day close; 3% earnest "
        "money deposit; seller to deliver estoppels within 15 days.",
    ],
]

OM2_GROUND_TRUTH = {
    "doc_type": "om",
    "source_file": "om_harbor_point.pdf",
    "fields": {
        "property_name": {"value": "Harbor Point", "page": 2},
        "address": {"value": "88 Harbor Drive, Tampa, FL 33602", "page": 2},
        "total_units": {"value": 14, "page": 2},
        "unit_mix": {"value": [
            {"unit_type": "Retail", "count": 8, "avg_rent": 2400},
            {"unit_type": "Office", "count": 6, "avg_rent": 3100}],
            "page": 3},
        "avg_rent": {"value": 2700, "page": 3},
        "occupancy_pct": {"value": 92, "page": 3},
        "t12_noi": {"value": 905250, "page": 4},
        "proforma_noi": {"value": 980000, "page": 4},
        "asking_price": {"value": 12750000, "page": 4},
        "cap_rate_pct": {"value": 7.10, "page": 4},
        "expenses_breakdown": {"value": [
            {"category": "Property Taxes", "amount": 180000},
            {"category": "Insurance", "amount": 72000},
            {"category": "Management", "amount": 96000},
            {"category": "Maintenance", "amount": 110000},
            {"category": "Utilities", "amount": 64000}], "page": 5},
        "total_expenses": {"value": 522000, "page": 5},
        "sale_terms": {"value": "1031 exchange considered; 45-day close; 3% "
                                "earnest money deposit; seller to deliver "
                                "estoppels within 15 days.", "page": 6},
    },
}

# ------------------------------------------------------------- corpus ----

CORPUS = {
    "maple-grove-overview.md": """# Maple Grove Apartments — Overview

Maple Grove Apartments is a 120-unit garden-style multifamily property at
1420 Elm Street, Dayton, OH 45402, about ten minutes from downtown Dayton.

Built in 1987 and renovated in 2019, the property offers a mix of 1BR, 2BR,
and 3BR units. Occupancy was 94% at the time of the October 2026 offering
memorandum, with an average rent of $1,160 per month.
""",
    "maple-grove-management.md": """# Maple Grove Apartments — Management Notes

On-site management notes (October 2026):

- On-site manager: Dana Whitfield; maintenance lead: Priya Natarajan.
- Average maintenance turnaround is 48 hours for non-emergency tickets.
- Two shared laundry facilities, one per building cluster.
- Surface parking: 180 spaces, unassigned.
- Quarterly unit inspections; annual HVAC servicing each fall.
""",
    "harbor-point-overview.md": """# Harbor Point — Overview

Harbor Point is a mixed-use property at 88 Harbor Drive, Tampa, FL 33602,
built in 2016. The ground floor holds retail suites; the upper floors are
office space.

Suite 120 is leased to Bluefin Coffee Roasters LLC, a specialty coffee
retail and cafe tenant. Their lease commenced 2024-06-01 and runs through
2029-05-31, with base rent of $84,000 per year and 3% annual escalations.
""",
    "ironworks-overview.md": """# Ironworks Industrial Park — Overview

Ironworks Industrial Park is an industrial property in Gary, IN, with
240,000 square feet across three buildings. The park is rail-served, with
18 dock doors and 24-foot clear heights.

Current use is light manufacturing and distribution warehousing.
""",
    "portfolio-notes.md": """# Portfolio Notes

General notes across the fictional demo portfolio:

- All three properties are fictional and used only for this demo.
- Critical dates (lease expirations, renewal notice deadlines) are tracked
  per lease abstract; Harbor Point's Bluefin Coffee lease has a renewal
  notice deadline of 2028-08-31.
- Quarterly property inspections are scheduled for all assets.
""",
    "harbor-point-leasing.md": """# Harbor Point — Leasing Notes

Leasing status (October 2026):

- Suite 120: Bluefin Coffee Roasters LLC — lease through 2029-05-31,
  renewal notice deadline 2028-08-31.
- Suite 210: Copperline Fitness LLC — lease through 2027-11-30,
  renewal notice deadline 2027-05-31. The fitness tenant's renewal
  decision is the key 2027 event for this property.
- Remaining retail suites are marketed at $28 per square foot.
""",
    "ironworks-leasing.md": """# Ironworks Industrial Park — Leasing Notes

Leasing status (October 2026):

- Building A (120,000 SF): Great Lakes Logistics Inc — lease through
  2028-03-31, renewal notice deadline 2027-09-30. Base rent $210,000
  per year with 3% annual escalations.
- Buildings B and C are vacant and being marketed to distribution users.
""",
}


def build_pdf(path: Path, pages: list[list[str]], title: str) -> None:
    styles = getSampleStyleSheet()
    body = styles["Normal"]
    body.fontSize = 11
    body.leading = 15
    heading = styles["Heading2"]
    story = []
    for i, lines in enumerate(pages):
        for line in lines:
            style = heading if line.isupper() and len(line) < 60 else body
            story.append(Paragraph(line, style))
            story.append(Spacer(1, 0.08 * inch))
        if i < len(pages) - 1:
            story.append(PageBreak())
    doc = SimpleDocTemplate(str(path), pagesize=LETTER,
                            title=title, author="deal-copilot demo")
    doc.build(story)


def main() -> None:
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    GT_DIR.mkdir(parents=True, exist_ok=True)
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)

    docs = [
        ("om_maple_grove.pdf", OM_PAGES, OM_GROUND_TRUTH,
         "Maple Grove Apartments — Offering Memorandum"),
        ("om_harbor_point.pdf", OM2_PAGES, OM2_GROUND_TRUTH,
         "Harbor Point — Offering Memorandum"),
        ("lease_bluefin.pdf", LEASE_PAGES, LEASE_GROUND_TRUTH,
         "Bluefin Coffee Roasters — Lease Abstract"),
        ("lease_copperline.pdf", LEASE2_PAGES, LEASE2_GROUND_TRUTH,
         "Copperline Fitness — Lease Abstract"),
        ("lease_glakes.pdf", LEASE3_PAGES, LEASE3_GROUND_TRUTH,
         "Great Lakes Logistics — Lease Abstract"),
    ]
    for fname, pages, gt, title in docs:
        pdf = PDF_DIR / fname
        build_pdf(pdf, pages, title)
        (GT_DIR / fname.replace(".pdf", ".json")).write_text(
            json.dumps(gt, indent=2) + "\n")
        print(f"wrote {pdf} ({len(pages)} pages)")

    for fname, text in CORPUS.items():
        (CORPUS_DIR / fname).write_text(text)

    print(f"wrote {len(CORPUS)} corpus files to {CORPUS_DIR}")
    print(f"wrote ground truth to {GT_DIR}")


if __name__ == "__main__":
    main()
