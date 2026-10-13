# Infrastructure — what deal-copilot needs in production

Nothing exotic. The demo is one process on SQLite + Chroma + local
files; production splits it into standard cloud pieces. Each layer
has one decision that matters.

```
                    ┌──────────────┐
                    │ Load balancer │
                    └──────┬───────┘
                           ▼
              ┌────────────────────────┐
              │ API tier (stateless)   │  FastAPI: /ask, /ingest,
              │ 2+ replicas            │ /jobs — containerized,
              └───────────┬────────────┘  no local state
                          ▼
              ┌────────────────────────┐
              │ Worker tier (async)    │  Celery/Temporal + Redis:
              │ autoscale on queue     │  classify → extract →
              │ depth                  │  reconcile → resolve →
              └───────────┬────────────┘  write. Separate from the
                          ▼               API so document backlogs
        ┌─────────────────────────────┐   never block questions.
        │ LLM APIs (no GPUs needed)   │
        │ Azure OpenAI recommended    │
        └─────────────────────────────┘
```

## Compute

- **API tier**: stateless containers (ECS / GKE / AKS, or App
  Service). Light — the heavy lifting is LLM API calls.
- **Worker tier**: separate pool, autoscaled on queue depth.
- **No GPUs** while models are API-based. Self-hosted models are a
  different (much more expensive) conversation; don't start there.

## Data

- **Postgres** — entity store (properties, aliases, extractions),
  job records, audit log, review-queue state. The demo's SQLite
  migrates here with no schema redesign.
- **Vector DB with strong metadata filtering** — pgvector if they
  already run Postgres (simplest), or Pinecone/Qdrant managed. The
  metadata filtering is non-negotiable: it is how per-user
  permissions are enforced at retrieval time.
- **Object storage** (S3 / Azure Blob) for raw PDFs — the system of
  record for source files. The database holds extracted fields and
  citations, never the files themselves.
- **Redis** — job queue plus caching for repeat questions.

## LLM

- API-based (OpenAI / Anthropic). **Azure OpenAI** is usually the
  path of least resistance for firms like the target client:
  existing Microsoft relationship, private networking options,
  familiar procurement.
- **Cost control from day one**: per-tenant usage metering and
  budget alerts. Extraction dominates spend (roughly cents per
  document — a 100-lease pilot is tens of dollars in LLM cost);
  `/ask` is pennies per query.

## Identity, secrets, integration

- **Identity**: the customer's Okta / Entra via OIDC for the review
  surface and API access; service principals for the watchers.
- **Secrets**: Key Vault / Secrets Manager / Vault for API keys and
  connector credentials. Never env files in production.
- **Watchers**: Microsoft Graph API (email, SharePoint), S3 event
  notifications, CRM webhooks.
- **Write-back**: Yardi API (requires the client's IT — surfaced in
  discovery, not mid-pilot), Slack webhooks for critical-date
  alerts, ticketing API for the review queue.
- **Network**: VPC with private subnets for workers and databases;
  only the load balancer is public — or fully private behind their
  VPN, if required.

## Observability

- Structured JSON logs per job (ingest → extract → reconcile →
  resolve), shipped to Datadog / CloudWatch / Loki.
- Dashboards: job latency, extraction hit-rate **per document
  type**, queue depth, LLM spend per tenant.
- Tracing (OpenTelemetry / Langfuse) for the ask pipeline.
- Alerting: PagerDuty/Opsgenie for pipeline failures; Slack for
  data-quality drift (field hit-rate drops when a source format
  changes).

## Deployment

- **IaC** (Terraform), **CI/CD** (GitHub Actions), three
  environments (dev / staging / prod). Staging runs against
  scrubbed documents.
- **The eval suite gates every deploy.** The 20 checks in
  `eval/run_eval.py` (extraction accuracy, router classification,
  refusal behavior) run in CI; a model, prompt, or dependency change
  that drops extraction accuracy cannot ship. The eval is not just
  dev tooling — it is the deploy gate.

## Cost shape

- **Pilot**: a few hundred dollars/month (managed Postgres, Redis,
  container hosting) + LLM usage.
- **Production**: low single-thousands/month in infra + usage-based
  LLM spend. No GPU line items.

## The real decision: who hosts

- **We host (multi-tenant SaaS)**: fastest to pilot, simplest to
  operate. Their documents leave their network — needs explicit
  sign-off, and some firms will never agree.
- **They host (deploy into their Azure/AWS)**: slower to stand up,
  but it answers the data-residency question permanently. For a
  financial firm, this is usually where it ends up.

Recommended: pilot on ours, architect for theirs — keep the
deployment portable (containers + Terraform) so the migration is a
re-deploy, not a rewrite.
