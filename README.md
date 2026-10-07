# AI Data Analyst

Ask questions about your data in plain language. A team of agents plans the work, writes and **validates** SQL, runs it read-only, picks a chart, explains the result and has a reviewer check the answer.

```
Question → Planner → [SQL Agent × N in parallel] → Data Analyst → [Visualization ∥ Insight] → Reviewer → Answer
                              │
              validate (sqlglot) → read-only engine (DuckDB locally / Athena on AWS)
```

## Quick start (local, 3 minutes)

```bash
cp .env.example .env          # set ANTHROPIC_API_KEY  (or LLM_PROVIDER=bedrock with AWS credentials)
docker compose up --build     # postgres + api + web
```

Open **http://localhost:3000** (API docs: http://localhost:8000/docs).

1. **Datasets** → upload `sample_data/sales.csv` (1,200 orders). It is profiled automatically.
2. **Documents** → upload `sample_data/sales_policy.md`.
3. **Analyst** → try:
   - *What were our top 10 products by revenue?*
   - *Show monthly revenue by region*
   - *Which orders would be classified as Premium according to our sales policy, and what share of revenue are they?*

No Docker? `make backend-dev` (SQLite) and `make frontend-dev` in two terminals. Tests: `make test`.

## What's in the box

| Phase | Where |
|---|---|
| 1 Foundation | `backend/` FastAPI, `frontend/` Next.js, Postgres + Docker (`docker-compose.yml`) |
| 2 Auth | `backend/app/auth.py` – Cognito JWT (RS256/JWKS), orgs, roles `viewer < analyst < admin`; `AUTH_MODE=dev` for local |
| 3 Datasets | `api/datasets.py` – CSV, TSV, Excel, Parquet, JSON, **PostgreSQL / MySQL** query import, **REST API** import |
| 4 Processing | `ingestion/` – schema detection, snake_case cleanup, types, missing values, duplicates, stats, outliers, quality score |
| 5–6 AI + SQL agent | `agents/sql_agent.py`, `sql/validator.py` – schema-aware prompts, validation, read-only execution, correction loop (3 tries, also retries empty results), error recovery |
| 7 Multi-agent | `agents/pipeline.py` – Planner, SQL ×N (`asyncio.gather`), Analyst, Viz ∥ Insight, Reviewer; every step traced |
| 8 Visualization | `agents/viz.py` – KPI, bar, line, pie, scatter, histogram, table (Vega-Lite specs; rules choose, LLM titles) |
| 9 Dashboard UI | Dataset manager, analyst chat, query history, SQL viewer, charts, insights, dashboard builder, CSV/PNG/JSON export |
| 10 AWS data arch | S3 → Glue → Athena engine (`engines.py`, `ingestion/glue.py`), RDS, ECS, Bedrock, EventBridge → SQS worker |
| 11 RAG | `rag/` – chunk → embed (Bedrock Titan, or offline hash fallback) → retrieve → used by Planner/SQL/Analyst/Insight |
| 12 Security | see below |
| 13 Observability | JSON logs, request IDs, CloudWatch EMF metrics (latency, tokens, **cost per query**), agent trace per answer, alarms + dashboard in Terraform |
| 14–16 Infra / CI / Deploy | `infra/terraform/`, `.github/workflows/ci-cd.yml` |

## Security model

* **The LLM is untrusted.** Every query passes `sql/validator.py`: exactly one statement, `SELECT`/`WITH` only, table allowlist (the org's datasets), no table functions / file readers / system functions, no schema-qualified names, row cap enforced.
* **Engine lockdown (defense in depth).** DuckDB runs in-memory with external access disabled, restricted to the tenant's directory, configuration locked, 30 s timeout. Athena runs in a workgroup with enforced result location and a per-query scan cutoff. Both are covered by tests that bypass the validator on purpose.
* **Tenancy.** Every row/query is scoped by `org_id`; S3 layout `org=<id>/dataset=<id>/`; one Glue database per org; the agent only ever sees that org's schemas. *Note:* all orgs share one Athena workgroup and one IAM task role, so isolation on AWS is enforced by the application layer (validator allowlist + per-org Glue database), not by IAM. If you need hard isolation, add per-tenant workgroups/roles. Postgres Row-Level Security is not implemented.
* **Secrets.** RDS master password lives in Secrets Manager and is injected into ECS. DB import passwords are used once and never stored. `ALLOW_PRIVATE_HOSTS=false` in AWS blocks SSRF via DB/API imports.
* **Limits & audit.** Upload size, row cap, query timeout, per-org daily question cap; `audit_logs` records uploads, imports, deletes and every question with its SQL (`GET /api/audit`, admin only).

## Deploy to AWS

Prereqs: AWS account with Bedrock model access enabled, Terraform ≥ 1.6, AWS CLI, a GitHub OIDC role.

```bash
cd infra && ./bootstrap.sh us-east-1           # state bucket + lock, writes terraform/backend.hcl
cd terraform && terraform init -backend-config=backend.hcl
terraform apply -var desired_count=0           # everything except running tasks
```

In GitHub set secret `AWS_ROLE_ARN` and variables `AWS_REGION`, `TF_STATE_BUCKET`, then push to `main`: the workflow tests → builds → scans (Trivy) → pushes to ECR → `terraform apply -var image_tag=<sha>` → waits for ECS → smoke-tests `/health`.

Afterwards: create users in Cognito with attribute `custom:org_id` and add them to the `admin` / `analyst` / `viewer` group (users with no group are viewers). Add an ACM certificate via `-var acm_certificate_arn=…` for HTTPS.

## Configuration

See `.env.example`. Key switches: `LLM_PROVIDER` (`anthropic`|`bedrock`), `QUERY_ENGINE` (`duckdb`|`athena`), `STORAGE` (`local`|`s3`), `AUTH_MODE` (`dev`|`cognito`), `EMBEDDINGS_PROVIDER` (`hash`|`bedrock`).

## What has and hasn't been verified

| | Status |
|---|---|
| Backend: validator (30 cases), ingestion + profiling, upload → ask pipeline with self-correction, tenant isolation, RBAC, dashboards, RAG, DuckDB lockdown, chart selection | ✅ 34 automated tests pass; real server smoke-tested with the sample CSV |
| Frontend | ✅ `next build` passes (type-checked). Not clicked through in a browser against a live LLM. |
| Real LLM quality (prompts for planner/SQL/analyst/insight/reviewer) | ⚠️ Tests use a scripted fake LLM. Try your own questions and tune `agents/` prompts. |
| Docker images / `docker compose` | ⚠️ Written but not built here (no Docker in my environment) |
| Terraform, GitHub Actions | ⚠️ Not applied or validated (no Terraform/AWS access). Run `terraform validate` first and expect small fixes. |
| Athena engine, Glue registration, SQS worker, Cognito login, Bedrock calls | ⚠️ Implemented, untested against real AWS. Check the Bedrock model id (`BEDROCK_MODEL_ID`) available in your account. |

## Known limits / next steps

* Schema context is the full profile of the selected datasets (capped at 60 columns/table). For warehouses with hundreds of tables, add embedding-based table/column retrieval.
* "Query optimization" is prompt rules + enforced LIMIT/timeout; there is no EXPLAIN-driven rewrite yet.
* RAG vectors are stored as JSON and searched with numpy (fine up to ~tens of thousands of chunks); switch to pgvector beyond that.
* Schema is created with `create_all` at startup; introduce Alembic before your first production schema change.
* Excel: first sheet only. Large uploads go through the API (no presigned S3 upload yet).
* Cognito: first-login "new password required" flow isn't in the UI.
