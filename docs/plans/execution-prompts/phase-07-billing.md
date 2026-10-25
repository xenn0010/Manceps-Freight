# Execution prompt: Phase 7 (billing)

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

## 6. Phase 7 brief: Stripe subscription billing, plan limits, trial, dunning

**Prerequisites.** Phase 1 merged (Phase 2 recommended for schedules).

**Goal.** Each firm has a subscription with a trial, plan limits enforced in the API, and dunning states that degrade the
product safely.

### 6.1 Verified Stripe facts (https://docs.stripe.com/webhooks)

- Verify every webhook with the `Stripe-Signature` header, the raw request body and the endpoint secret (`whsec_`). Use the official
  `stripe` Python library's `Webhook.construct_event` (snapshot events). Default tolerance 5 minutes; never use 0.
- Return 2xx quickly and process asynchronously (store the event, enqueue a job).
- Duplicates happen; events are not ordered; dedupe on event id; fetch the current object from the API instead of trusting event order.
- Live-mode retries for up to three days with exponential backoff.
- Check the current Python SDK and API version from https://docs.stripe.com/api before pinning; do not use preview versions.
- UNVERIFIED: exact Checkout Session and Billing Portal parameter names for the pinned SDK version; read the docs and cite.

### 6.2 Design

- `billing_accounts` (platform): `tenant_id, stripe_customer_id, subscription_id, plan, status (trialing|active|past_due|canceled|none), trial_end, current_period_end, dunning_state, limits`.
- Plans in `manceps_core/limits.py` as a code table: `trial`, `solo` (up to 3 carriers), `team` (up to 12), `fleet` (up to 40) with limits
  `carriers, members, imports_per_month, agent_messages_per_day, storage_mb`. Stripe price ids come from `STRIPE_PRICE_IDS` JSON
  (plan -> price id). Numbers in the table are placeholders the founder sets; define them as settings with defaults and say so.
- Firm activation (Phase 1 handler) also creates the billing account with `plan=trial`, `trial_end = now + TRIAL_DAYS` (setting, default 14), no
  Stripe customer yet. Customer creation happens at first checkout.
- Routes: `GET /v1/billing`, `POST /v1/billing/checkout` (Checkout Session in subscription mode with `client_reference_id = tenant_id`),
  `POST /v1/billing/portal`, `POST /v1/webhooks/stripe`, `GET /v1/firm/usage`.
- Webhook events handled: `checkout.session.completed`, `customer.subscription.created|updated|deleted`, `invoice.paid`,
  `invoice.payment_failed`, `customer.subscription.trial_will_end`. Each handler re-fetches the subscription and recomputes the state
  from it (idempotent, order-independent).
- Limit enforcement: dependency `enforce_limit("carriers")` on create routes and import commit (commit reports `limit_reached` for
  rows beyond the limit instead of partially failing silently: rows over the limit are `skip` with reason). Response 402 `plan_limit_reached`
  with `details.limit` and `details.current`.
- Dunning: `past_due` for `DUNNING_GRACE_DAYS` (default 7) keeps full access with banner event `billing.past_due`; after the grace period:
  agent-initiated outbound and schedules pause (`firms.status="past_due"` honored by outbox and scheduler), reads and approvals still work; `canceled`
  gives read-only plus data export. Dispatching and safety messages from the dispatcher are never blocked by billing.
- No `STRIPE_SECRET_KEY` -> billing routes 503; trial still works so development is possible; production without Stripe keys refuses to start
  paid plans (fail closed on creating `active`).
- Do not store card data; use hosted Checkout and the portal.

### 6.3 Tests first

`test_webhook_bad_signature_400`, `test_webhook_stale_timestamp_400`, `test_webhook_dedupe_event_id`, `test_out_of_order_events_converge`,
`test_trial_defaults`, `test_limit_blocks_402`, `test_import_commit_skips_rows_over_limit`, `test_past_due_pauses_agent_outbound_only`,
`test_canceled_read_only`, `test_checkout_503_without_keys`, `test_no_card_data_stored` (schema scan), `test_wrong_tenant_matrix_new_routes`.

### 6.4 Acceptance criteria

1. Webhooks are verified, deduped, and converge to the right state out of order.
2. Trial, limits, and dunning behave as specified and are time-injected in tests.
3. Billing never blocks reading data, approving, or exporting.
4. Without Stripe keys the routes are 503. All gates green.

### 6.5 Do not do

No Connect, no invoices to carriers (Phase 8). No live Stripe calls in tests (fake client).

## 7. Finish

End your run with the report format in section 5: status first, then exact gate outputs, files changed, decisions, what was not verified, and founder actions.
