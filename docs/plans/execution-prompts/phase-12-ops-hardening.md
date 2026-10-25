# Execution prompt: Phase 12 (ops-hardening)

Manceps platform backend. Self-contained build prompt. Planned 2026-10-25.

## 0. How to use this prompt

You are a build agent. This prompt is self-contained. The repository root is
`/Users/yeabsirateshome/Documents/Mercepes`. Background plan files (reference only, not required reading) are in
`docs/plans/2026-10-25-manceps-platform-plan*.md`. If this prompt and a plan file disagree, this prompt wins; say so in
your report.

Working rules:
- Read the existing code named below before changing anything. Search, read, then edit.
- Write tests first (red), then the minimum code to pass (green), then tidy. Show the red run for at least one test per work package.
- Do not modify `hermes-agent/` (Hermes core). Agent features go in the `hermes-freight` plugin; platform features go in `backend/`.
- Never read or print `.env.local`, `atlas-credentials.env`, `hermes-secrets.env`, or any secret. Tests use fakes and mongomock only.
- Do not contact real vendors, do not deploy, do not touch git unless the founder asks. Local `uv sync` and test runs are expected.
- Never `cd` inside a command; set the working directory per command instead.
- Minimal diffs on existing files; match their style. Imports at the top of files. No scratch files left behind.
- If a vendor fact marked UNVERIFIED in this prompt matters to your code, open the official documentation page first and
  cite the URL in your report. If you cannot verify it, build the safe default (reject or `not_configured`) and say so.
- Up to 3 real attempts at any failing problem, then stop and report the blocker, what you tried, and what you need.

## 1. Product rules (encode in code and tests, not only docs)

1. **Bring-your-own-carrier only.** A firm dispatches its own contracted carriers. No shared truck pool, no assigning one
   load across firms, no booking a load before a carrier is chosen. The platform never handles freight money between
   shipper/broker and carrier; the dispatch fee is billed to the carrier separately.
2. **Consent before contact (TCPA).** No SMS, WhatsApp, or voice to a number without consent on file for that channel.
   Public FMCSA phone numbers are not consent. Every AI call and first message discloses that it is an AI.
3. **Human approval for money and contracts.** Accepting a rate, signing or approving a Rate Con, moving money, changing a
   carrier's fee, floor, consent, or agreement: always an approval request.
4. **Fail closed.** A failed lookup is `unknown`, never `pass`. A policy crash blocks. Missing credentials disable a feature
   with a clear 503, never skip a check.
5. **Tenant isolation.** One firm = one MongoDB database `firm_<tenant>`. The tenant comes from the authenticated principal,
   never from request bodies or model output. Cross-tenant reads are impossible by construction and covered by tests.
6. **No antitrust leakage.** Network features only expose aggregated, anonymized data with a minimum cohort size. No firm
   ever sees another firm's rates, floors, carriers or loads.

## 2. Engineering standards

- Python 3.11+, FastAPI, Pydantic v2, pymongo, uv, pytest, ruff, pyright **strict** for platform code (`backend/`).
- Type hints on every signature. Docstrings: one-line summary, then Args/Returns/Raises.
- Max 50 lines per function, 500 lines per file. No magic numbers: named constants or settings.
- Config only through the typed `Settings` object. Secrets are `SecretStr`, never logged, never returned by an API.
- Structured logging (structlog JSON). Every request and agent action carries `request_id` and `tenant_id`.
- No placeholders, TODOs, stubs, `...` bodies, commented-out code, or pseudo-code. An integration whose credentials are
  absent is still fully implemented: it reports `not_configured` (503) and its client is tested against a fake transport.
- External HTTP: timeouts, bounded retries with backoff for idempotent calls, a fake transport seam for tests.
  Webhooks verify signatures and are idempotent (dedupe by event id) and return 2xx fast.
- Every write to firm data appends an `audit` record (who, what, when, request id, session id).
- Money is integer cents. Datetimes are timezone-aware UTC. Phones are E.164.
- Tests use mongomock and fake integrations. Note mongomock limits (no transactions): use idempotent state markers instead.

## 3. API contract

- REST under `/v1`, JSON, OpenAPI generated and committed (`backend/openapi.json`), stable `operationId` (`<resource>_<verb>`),
  typed request and response models, cursor pagination `{items, next_cursor}`, error envelope
  `{"error": {"code", "message", "details"}}`, `Idempotency-Key` on creates and payment-like endpoints.
- Auth: access JWT (EdDSA, 15 min) + rotating refresh token; roles per firm: owner > dispatcher > viewer; carriers and drivers
  use scoped links only.
- Real-time: Server-Sent Events per firm.
- Every endpoint has tests for: happy path, validation error, auth failure, wrong-tenant access.

## 4. Quality gates (all must pass; paste the real output in the report)

Run from `backend/` (set the working directory, do not `cd`):
1. `uv run pytest -q --cov=manceps_core --cov=manceps_api --cov=manceps_worker --cov-fail-under=90`
2. `uv run ruff check .`
3. `uv run pyright` (strict, 0 errors)
4. `uv run python scripts/export_openapi.py --check` (committed `openapi.json` matches the app)
5. `uv run python scripts/vendor_core.py --check` (plugin copy of `manceps_core` matches)
6. Plugin suite: working directory `hermes-freight/`, `python -m pytest -q` with its own venv per its `requirements-dev.txt` (must stay green)
7. Security self-check written in the report: authz on every route, tenant scoping on every query, input size limits, upload
   type and size limits, rate limits on auth and public routes, no secrets in logs or responses.
8. A short end-to-end test drives the main flow through the HTTP API against mongomock and fake integrations.

## 5. Report format (end your run with exactly this)

- **Status:** done / partial / blocked, then the evidence: the exact gate outputs (commands and their final lines).
- **Files changed:** list with one line each.
- **Decisions made and why.**
- **Not verified / not done:** said plainly, including UNVERIFIED vendor facts you could not confirm.
- **Founder actions needed next.**

## 6. Phase 12 brief: operations and hardening

**Prerequisites.** Phases 1 to 11 merged.

**Goal.** The founder can run the platform: see every firm, queue, and integration; suspend, export, delete; scale Atlas users and
projects; observe, back up, and restore; seed demo data. Production readiness review included.

### 6.1 Verified Atlas facts

- Free tier: 500 collections and 100 databases total, 100 ops/s, 500 connections, 10 GB in/out per rolling 7 days
  (https://www.mongodb.com/docs/atlas/reference/free-shared-limitations/).
- 100 database users per project; recommended maximum collections plus indexes: M10 5,000, M20/M30 10,000, M40+ 100,000
  (https://www.mongodb.com/docs/atlas/reference/atlas-limits/).
- UNVERIFIED: Atlas Admin API create-user request shape and rate limits (page did not render). Read
  https://www.mongodb.com/docs/atlas/reference/api-resources-spec/v2/ (the "Create One Database User in One Project" operation) and the
  rate-limit page, cite them, then align `hermes-freight/deploy/provision_tenant.py` (scoped mode already exists) with what you read.
  The founder must run one real integration test against an Atlas project (provide the script, do not run it yourself).

### 6.2 Design

- Operator auth: separate JWT audience `operator`, separate signing key set (`OPERATOR_JWT_KEYS_JSON`), issued by `scripts/operator_token.py`
  (run locally by the founder), optional `OPERATOR_IP_ALLOWLIST`. Operator tokens fail on firm routes; firm tokens fail on `/v1/admin/*`.
  Every operator action writes `platform.operator_audit`.
- Routes (plan part 3 section 17): firms list/detail, suspend/resume, queues, job retry, flags, health, export, delete, seed. A suspended firm gets 403
  `firm_suspended` on all firm routes, its agent commands are not claimed (bridge skips suspended tenants: add a platform-side filter in claim query),
  schedules do not run.
- Feature flags: `platform.feature_flags`; `flags.enabled(key, tenant_id)` with per-firm overrides, cached 30 s; `GET /v1/me` returns the firm's flags.
- Health: Atlas ping and latency, collection count versus tier limit (`ATLAS_COLLECTION_LIMIT` setting; warns at 80%), R2 head, bridge heartbeat age, last
  successful run per vendor, job lag, dead letters, webhook failure counts.
- Observability: structlog JSON already; add OpenTelemetry tracing (`opentelemetry-sdk`, OTLP exporter configured by env, off by default) and Prometheus metrics
  at `/metrics` behind operator auth: request latency, job lag, command queue depth, SSE connections, webhook failures per provider, outbox blocked reasons.
- Backups: Atlas continuous backup is a paid-tier feature (UNVERIFIED: confirm in docs which tiers); plan the logical backup path that works on any tier:
  `infra/backup/dump_firms.py` writes per-firm JSON-lines (all collections) to R2 under `backups/<date>/<tenant>/`, encrypted with `BACKUP_KEY`
  (AES-GCM streaming), retention `BACKUP_RETENTION_DAYS=30`; `infra/backup/restore.py` restores one firm into a scratch database and verifies counts and hashes.
  Both are idempotent and tested against mongomock.
- Firm export (`firm_export` job): bundle of all collections as JSONL plus documents manifest and files, zipped to R2, 7-day download URL max 24 h in practice
  (presign 1 hour on request). Firm deletion: 30-day grace; after grace the job deletes documents prefix, drops `firm_<tenant>`, deletes the Atlas user, disables
  integrations (revoke OAuth tokens), removes platform rows by `tenant_id` except `billing_accounts` and `operator_audit`, and writes a deletion receipt.
- Scaling users and shards: `deploy/atlas_users.py` creates a scoped user per firm (readWrite on `firm_<tenant>`, read on `freight_reference`, scope = cluster) and stores
  nothing in Mongo except `firms.atlas_user` name; the password goes only to the VM profile `.env`. `manceps_core/shards.py`: registry `platform.atlas_shards {id, project, cluster, uri_ref, firms, user_count, status}`;
  `allocate()` picks the shard with `user_count < ATLAS_USERS_SOFT_LIMIT (90)` and collections headroom; API/worker TenantDb routes by `firms.atlas_shard` through a
  client pool keyed by shard (default shard when absent).
- Migrations: `scripts/migrate.py --all [--dry-run]` runs numbered migrations recorded in `platform.schema_migrations`, per firm with bounded concurrency; ships migration
  0001 that backfills `created_at/updated_at` and runs `ensure_firm_indexes`.
- Seeds: `scripts/seed_demo.py` creates a demo firm (10 carriers, 40 loads across all statuses, 3 approvals pending, notes, documents metadata only) via core repos; refuses when
  `ENV=production` unless `--force-demo`.
- Production readiness checklist doc is NOT a new markdown file: put it in the report as a table (secrets set, Atlas tier, IP allowlist, backups tested, restore tested, key rotation
  run, rate limits on, CORS origins, cookie flags, alerts configured).

### 6.3 Tests first

`test_operator_token_rejected_on_firm_routes`, `test_firm_token_rejected_on_admin_routes`, `test_operator_actions_audited`, `test_suspended_firm_403_and_no_claims`,
`test_flags_override_and_cache`, `test_health_reports_collection_headroom`, `test_metrics_require_operator`, `test_backup_restore_roundtrip_counts_and_hashes`,
`test_backup_encrypted_and_retention_prunes`, `test_export_contains_all_collections`, `test_delete_grace_then_removes_everything_but_billing_and_operator_audit`,
`test_delete_revokes_integrations`, `test_shard_allocation_soft_limit`, `test_tenantdb_routes_by_shard`, `test_migration_runner_idempotent_dry_run`,
`test_seed_refuses_in_production`, `test_atlas_user_payload_is_least_privilege` (fake Admin API transport asserts roles and scopes), `test_wrong_tenant_matrix_unchanged`.

### 6.4 Acceptance criteria

1. Operator and firm tokens are mutually rejected; all operator actions are audited.
2. Suspension stops API access, schedules, and agent command claims.
3. Export is complete (counts match); deletion removes everything required and keeps billing and operator audit.
4. Backup and restore round-trip with verified counts and hashes.
5. The Atlas user payload is least privilege; shard allocation respects the soft limit.
6. Metrics and health show job lag, queue depth, webhook failures, and collection headroom.
7. All gates green; the report includes the production readiness table and states plainly what was not run against real services.

## 7. Finish

End your run with the report format in section 5: status first, then exact gate outputs, files changed, decisions, what was not verified, and founder actions.
