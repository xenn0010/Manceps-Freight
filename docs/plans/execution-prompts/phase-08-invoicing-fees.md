# Execution prompt: Phase 8 (invoicing-fees)

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

## 6. Phase 8 brief: invoices, payments, aging, factoring handoff, dispatch-fee invoices

**Prerequisites.** Phases 1, 3, 4 (outbox), 7 merged. Legal gate: the founder confirms a lawyer has reviewed the fee model and the
Connect structure before any live charge. Build and test everything with fakes regardless; add the setting
`FEE_COLLECTION_ENABLED` (default 0) that blocks live fee charges until the founder sets it.

**Goal.** Delivered loads become invoices; the firm tracks receivables and chases payments; invoices can be handed to a factor;
the firm bills its carriers' dispatch fee through its own Stripe connected account with ACH.

### 6.1 Verified Stripe ACH facts (https://docs.stripe.com/payments/ach-direct-debit)

- Settlement up to 4 business days (T+2 faster settlement for eligible accounts); payment confirmation is delayed; failures can arrive
  days later; business-account debits can be disputed for up to 2 business days, personal accounts for up to 60 days; a dispute
  invalidates the mandate; late failures after `succeeded` become disputes with a fee.
- A mandate is required. Stripe stores it when using hosted Checkout, Payment Element or the hosted invoice page. Banks must be verified
  (Financial Connections or microdeposits; 10 days to finish microdeposits).
- Stripe can retry failed Direct Debit invoice payments at most 2 times within 40 days. Billing and Invoicing support ACH.
- Connect needs the `us_bank_account_ach_payments` capability on the platform and on connected accounts.
UNVERIFIED (resolve before coding): which connected account type and charge type to use (plan assumes Standard accounts and direct
charges so the invoice is the firm's), Connect onboarding API names (Account Links), fees, and any platform regulatory duties.
Read https://docs.stripe.com/connect and cite what you choose. If the choice is unclear, stop and report instead of guessing.

### 6.2 Design

Invoices (firm DB `invoices`, `payments`): `kind` broker_invoice or dispatch_fee; amounts integer cents; number from counter `invoice`
(`INV-<year>-<5 digits>`); statuses draft, pending_approval, sent, partial, paid, void, overdue. Create only from loads in `delivered` or
later with a POD document and `rate_cents`. `POST /v1/invoices/{id}/send` creates a `send_invoice` approval (kind added to registry;
payload: invoice id, recipient, channel, document hash); apply action renders the PDF (reportlab or weasyprint: pick one, pin it),
stores it as a document, enqueues the outbox send (consent rules apply to SMS; email to broker billing contacts uses the email path), moves
invoice to `sent` and the load to `invoiced`, once.
Payments: manual recording, factor remittance, or Stripe webhook; partial and full; `paid` when sum >= amount; load moves to `paid`.
Aging: `GET /v1/receivables/aging` buckets 0-30, 31-60, 61-90, 90+ by days past due (boundaries tested). Worker `aging_scan` daily marks `overdue`
and creates `payment_chase` reminders on days 1, 7, 14 after due (settings); chase messages go through the outbox to the broker's billing
contact; the agent drafts the text; sending follows consent rules. The agent can propose but not send an invoice.
Factoring: `FactoringProvider` protocol with `EmailFactoring` (builds one PDF package: invoice + rate con + POD; sends to the firm-configured
factor address through email transport; records `factoring.submitted_at`) and `OtrFactoring` behind `FACTORING_OTR_ENABLED=0` (do not
implement HTTP calls until you have read https://docs.otrsolutions.com and found auth + endpoints; if not available, leave the class absent
and the flag rejected at startup; do not write a stub).
Dispatch fee: `POST /v1/dispatch-fee-invoices {period_start, period_end, carrier_id?}` (owner) computes per carrier
`round_half_up(rate_cents * dispatch_fee_pct / 100)` for loads delivered in the period that have no fee invoice yet, groups by carrier,
creates draft `dispatch_fee` invoices and one `bill_carrier` approval (owner-only). On approval (and only if `FEE_COLLECTION_ENABLED=1` and the
Connect account is ready) the worker creates a Stripe invoice on the firm's connected account for the carrier customer (hosted invoice page
collects the ACH mandate); webhooks for the connected account update payments; `charge.dispute.created` and `invoice.payment_failed`
raise events and a dispatcher alert. The platform takes no application fee in this phase.
Connect onboarding: `POST /v1/billing/connect/onboard` returns the hosted onboarding link; status stored in `billing_accounts.connect`.
Guardrails: a repo test scans for any Stripe charge creation tied to load revenue (there must be none) and asserts fee invoices are the
only Stripe objects created on connected accounts.

### 6.3 Tests first

`test_invoice_requires_pod_and_delivered`, `test_cents_only_no_floats`, `test_send_requires_approval_and_once`, `test_aging_boundaries`,
`test_payment_partial_then_paid_moves_load`, `test_chase_goes_through_outbox_with_consent_rules`, `test_factor_email_package_contents`,
`test_otr_flag_rejected_when_unimplemented`, `test_fee_rounding_half_up_odd_cents`, `test_fee_idempotent_per_load`,
`test_bill_carrier_owner_only`, `test_no_stripe_object_before_approval`, `test_connect_not_ready_409`, `test_fee_collection_flag_blocks_live`,
`test_no_load_revenue_charge_code_path` (grep), `test_dispute_event_raises_alert`, `test_wrong_tenant_matrix_new_routes`.

### 6.4 Acceptance criteria

1. Invoices exist only for delivered loads with POD; money in cents.
2. Sending an invoice requires approval and happens once.
3. Aging buckets are exact at 30/31/60/61/90/91.
4. Fee math is half-up and each load is billed at most once.
5. No Stripe objects are created before approval; none for load revenue at all; live collection is off by default.
6. Disputes and failures raise alerts. All gates green.

### 6.5 Do not do

No live charges, ever, in tests. No loan or advance logic (factoring advances are the factor's). No platform application fee.

## 7. Finish

End your run with the report format in section 5: status first, then exact gate outputs, files changed, decisions, what was not verified, and founder actions.
