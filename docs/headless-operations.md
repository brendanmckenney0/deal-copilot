# Headless operations — running deal-copilot inside the enterprise

The demo has two tabs. In production, both dissolve into
infrastructure: the system disappears into the firm's operations.
Nobody "uses" it — deadlines stop getting missed and questions get
answered where people already work.

## Ingestion: watchers, not uploads

Documents arrive on their own; nobody uploads anything.

- **Monitored inbox** — leases, amendments, and estoppels arrive by
  email; a watcher pulls attachments.
- **Drop folders** — SharePoint / S3 locations the brokers and
  property managers already use.
- **Scheduled exports** — Yardi (or the system of record) on a
  nightly cadence.
- **Webhooks** — CRM events (new deal, new lease version).

Each watcher is a connector — the `BaseConnector` framework already
abstracts this. The demo's doc_type dropdown becomes automatic
classification: filename and sender rules first, an LLM classifier
for the ambiguous cases, with low-confidence classifications routed
to review.

## Processing: async jobs

`POST /ingest` becomes an internal endpoint behind a job queue
(Celery, Temporal, or similar):

```
classify → extract → reconcile → resolve entity →
write entity store + vector index
```

The job envelope (`job_id`, status, fields extracted, gaps,
reconciliation) is the audit trail. Failed documents go to a
dead-letter queue with the error attached — never silently dropped.
Retries with backoff for transient failures (LLM rate limits,
unavailable exports).

## Where the value lands

**Critical-date diary.** Extracted renewal, expiration, and notice
dates feed a dates API plus proactive alerts at 90/60/30 days before
each notice deadline. This is the killer headless feature: no app to
open, the deadline just never gets missed.

**Write-back.** Structured fields land on the property/lease record
in the system of record. The firm's data gets better without anyone
doing data entry.

**Ask as a service.** `POST /ask` behind whatever surface the firm
already lives in: a Slack/Teams bot ("@copilot, what's our exposure
to coffee tenants in Tampa?"), the intranet, an Excel plugin. Even
the conversational surface goes headless.

**Review queue.** Low-confidence extractions and ambiguous entity
resolutions become tasks in the firm's ticketing system, assigned to
a named reviewer. Human-in-the-loop survives the loss of the UI.

## A day in the life

1. A lease amendment arrives by email → the watcher picks it up.
2. Classified as `lease`, extracted, reconciled; the Bluefin Coffee
   renewal notice deadline moves from 2028-08-31 to 2029-02-28.
3. The Yardi lease record is updated; the critical-date diary
   recalculates alerts.
4. The asset manager gets a Slack ping: "Bluefin amendment
   abstracted — notice deadline moved, 2 fields need your review"
   with a link to the review task.
5. Monday 8am: the 90-day critical-date digest lands automatically.

## What headless demands that the demo doesn't

- **Observability carries everything.** Per-job structured logs,
  extraction hit-rate dashboards per document type, alerts when a
  source format changes and field hit-rates drop.
- **Eval runs on a schedule**, not just in CI — a rolling sample of
  production documents against ground truth, so drift is caught.
- **Permissions become real.** The `query/permissions.py` stub is fed
  by the firm's identity provider (Okta/Entra); every retrieval and
  every aggregate is filtered to what the requester may see.
- **Configuration replaces clicking.** Per-client schemas, field
  mappings, thresholds, and alert rules are API-managed config with
  versioning — not settings pages.

## Business shape

The headless deployment is the retainer story: the pilot proves the
extraction quality on a bounded set; the production rollout wires it
into their systems; the ongoing engagement covers new document types,
new sources, monitoring, and eval. Every new lease and amendment
flowing through the system deepens the moat — and the annuity.
