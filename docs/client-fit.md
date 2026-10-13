# Client fit — net-lease asset management

Role-based analysis (no personal data): how deal-copilot fits a
**net-lease asset-management shop** — a firm holding single-tenant
properties on long corporate leases, where the asset-management team
operates the portfolio day to day.

## Where the pain is

1. **Lease abstraction at scale.** Key terms live in lease PDFs and
   go stale in spreadsheets. Every new team member re-reads the same
   documents.
2. **Critical-date tracking.** Renewal options, expirations, and
   notice deadlines — a missed notice can cost a full option term.
   This is the highest-ROI automation target: it is concrete,
   measurable, and the cost of failure is obvious.
3. **Rent and delinquency monitoring**, and **tenant exposure**
   questions ("what's our exposure to tenant X across the portfolio?").
4. **Investor reporting** — synthesizing portfolio facts into
   narratives, repeatedly.

## How the two halves map

- The **extraction half** (DealScreener pattern: cited fields,
  NOT_FOUND discipline, deterministic reconciliation) pointed at
  **leases** becomes lease abstraction + a critical-date diary.
- The **RAG half** (Atlas pattern) becomes conversational Q&A over
  leases, memos, and market notes — with the firm's system of record
  (e.g. Yardi) as the structured source to connect.

## Recommended wedge

A **lease abstraction + critical dates pilot** on a bounded set
(e.g. 50–100 leases → structured abstracts + a diary of notice
deadlines). It exercises both halves of the system, produces a
measurable artifact, and sits squarely in the buyer's world. Then
expand: portfolio monitoring, proactive critical-date alerts,
investor-reporting synthesis — and the retainer (new leases and
amendments keep flowing in; that is the annuity).

## Honest caveats

- **OM/acquisition screening applies mainly to dispositions** for
  this buyer profile — they are holders, not flippers. Do not lead
  the pitch with it.
- **System-of-record integration needs their IT.** API access and
  data mapping are a discovery topic, not a mid-pilot surprise.
- **Economics fields need human review.** Same citation/NOT_FOUND
  discipline as the demo; the reviewer is part of the product.
- **Amendments and estoppels** create versioning complexity the MVP
  does not handle — name it early.
