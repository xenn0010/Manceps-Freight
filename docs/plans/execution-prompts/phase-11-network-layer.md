# Execution prompt: Phase 11 (network-layer)

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

## 6. Phase 11 brief: network layer (broker scorecards and fraud alerts)

**Prerequisites.** Phases 1 and 8 merged (payments data), Phase 4 (messages) optional.

**Goal.** Firms get broker scorecards and fraud alerts built from anonymized cross-firm signals without exposing any firm's
rates, floors, carriers, or loads (product rule 6).

### 6.1 Design principles (enforce in code)

- Collection `platform.network_signals` has no field that can identify a firm, carrier, or load: allowed fields are
  `broker_mc, signal, bucket, week, cohort_token`. `cohort_token = HMAC-SHA256(NETWORK_SALT, tenant_id)` truncated to 16 hex chars; the salt is a
  secret in env (`NETWORK_SALT`); it is only used to count distinct contributors, and tokens rotate yearly (`week` year is part of the HMAC input).
  Reading the collection must not allow joining to firms without the salt.
- Signals (weekly, per broker): `payment_days_bucket` (0-15, 16-30, 31-45, 46-60, 60+ from invoice issue to payment), `paid_detention` (yes/no
  bucketed by share), `fraud_report_count` (reports go through the review flow, not raw counts), `cancelled_after_booking_rate_bucket`.
  Values are buckets, never raw numbers. Rates and dollars are never signals.
- Minimum cohort `NETWORK_MIN_COHORT = 5` distinct `cohort_token`s per broker and signal over the trailing 26 weeks. Below the floor the API
  returns `{insufficient_data: true}` and no counts. Above it, only bucketed distributions with each bucket suppressed if fewer than 2
  contributors (secondary suppression to prevent differencing attacks). Never return the exact cohort size; return `cohort: "5+"`.
- Differencing defense: scorecards are recomputed weekly and cached for the week, so a new contributor cannot be inferred by diffing responses
  within the week; document the residual risk in the report.
- Opt-out: `PUT /v1/network/participation {contribute: bool}` (owner). Opt-out removes that firm's future signals; past anonymized aggregates stay
  (state this in the terms text draft). Opted-out firms still read alerts.
- Fraud alerts: `POST /v1/network/reports {kind: hijacked_mc|double_brokering, mc, evidence_doc_ids, description}` creates a `pending_review` alert
  with reporter token (not tenant id) visible only to the operator. Broadcast to firms only after operator approval (Phase 12 admin route; add a
  minimal internal CLI `scripts/review_alert.py` now). Alerts are shown only to firms that have the MC in `brokers`, `carriers`, or an open load.
  Alerts state facts and the review status; wording avoids accusations beyond the evidence (template, to be reviewed by a lawyer; UNVERIFIED).
- Writes happen only in `manceps_core/network/signals.py` (weekly worker job `network_aggregate` reading each opted-in firm's DB through TenantDb,
  emitting bucketed signals). No other module may import `network_signals` for write (import-lint test).

### 6.2 Tests first

`test_signal_docs_have_only_allowed_fields`, `test_no_tenant_id_anywhere_in_network_collections` (seed 6 firms, scan all documents recursively),
`test_cohort_floor_insufficient_data`, `test_exact_cohort_size_never_returned`, `test_small_bucket_suppressed`, `test_week_cache_blocks_diffing`
(add a 6th contributor mid-week, response unchanged until recompute), `test_opt_out_stops_contribution`, `test_opted_out_still_gets_alerts`,
`test_alert_pending_until_reviewed`, `test_alert_only_to_firms_with_relationship`, `test_reporter_identity_hidden`,
`test_only_signals_module_writes_collection`, `test_scorecard_route_tenant_matrix`, `test_rates_never_in_signals`.

### 6.3 Acceptance criteria

1. No document in network collections can identify a firm, carrier, load, or dollar amount.
2. Scorecards need at least 5 distinct firms, hide exact counts, and suppress small buckets.
3. Fraud reports are reviewed before broadcast, and reporters are not identifiable by other firms.
4. Opt-out is honored. All gates green.

### 6.4 Do not do

No cross-firm lane rates, no benchmarking of a firm's rates against others, no sharing of carrier names. If a requirement seems to need
them, stop and report (antitrust risk, needs lawyer).

## 7. Finish

End your run with the report format in section 5: status first, then exact gate outputs, files changed, decisions, what was not verified, and founder actions.
