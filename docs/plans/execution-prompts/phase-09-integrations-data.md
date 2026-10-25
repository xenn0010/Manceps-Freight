# Execution prompt: Phase 9 (integrations-data)

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

## 6. Phase 9 brief: reference sync, ELD (Motive, Samsara), DocuSeal e-sign

**Prerequisites.** Phases 3 and 4 merged. Encryption helper `manceps_core/secrets.py` exists (Phase 4); if not, build it now.

**Goal.** Fresh FMCSA reference data with visible age; ELD data per carrier through OAuth; the dispatch agreement is signed by the
carrier through DocuSeal and recorded.

### 6.1 Vendor facts

- Samsara (https://developers.samsara.com/docs/oauth-20, verified): authorize `https://api.samsara.com/oauth2/authorize` with `client_id`,
  `state` (more than 8 chars, verified on return), `response_type=code`; token `https://api.samsara.com/oauth2/token` (POST form, HTTP Basic
  `client_id:client_secret`); code lasts 10 minutes; access token about 1 hour (`expires_in`); **each refresh token is single use**: save the new
  access and refresh token after every refresh, never refresh concurrently, refresh just in time, if a refresh fails after use the carrier
  must re-authorize; scopes `admin:read`, `admin:write`; revoke at `https://api.samsara.com/oauth2/revoke`. Webhooks: UNVERIFIED (read Samsara's
  webhook docs).
- Motive: search results only (https://developer-docs.gomotive.com/docs/oauth-20, https://developer.gomotive.com/reference/authentication-oauth-20):
  OAuth 2.0 authorization code; token exchange `POST https://api.gomotive.com/oauth/token`; developer account must be enabled by Motive; scopes cover
  vehicles, users, HOS, locations; request all scopes up front. UNVERIFIED: authorize URL, refresh behavior, expiry, webhooks, rate limits,
  endpoints for vehicle locations. Open those pages and cite them. Use read-only scopes only.
- DocuSeal (https://www.docuseal.com/docs/api, verified): `X-Auth-Token`; `POST /submissions` from a template to submitters by email or phone;
  webhook events include `form.completed`, `submission.completed`, `submission.expired`; failed webhooks retried 48 hours on production.
  UNVERIFIED: how webhooks are authenticated (secret header?). Read the webhook page or SDK; the handler rejects requests until implemented.
- FMCSA/Socrata: see `hermes-freight/deploy/load_reference.py` (datasets `az4n-8mr2`, `qh9u-swkp`; insurance data stale since 2023-12-06 per HANDOFF).

### 6.2 Design

- `reference.sync` job: wraps the logic of `load_reference.py` (copy the pure functions into `manceps_core/reference/sync.py`, keep the script
  working) and writes `freight_reference` collections plus `platform.reference_meta {dataset, source_updated_at, synced_at, rows}`.
  Weekly schedule at platform level (not per firm). `GET /v1/reference/status` shows ages. A bond result from data older than
  `BOND_MAX_AGE_DAYS=90` is `unknown`. Never lowers a verdict to pass.
- OAuth framework `manceps_api/integrations/oauth.py`: `state` records (tenant, user, provider, carrier_id, PKCE verifier, expires 10 min) in
  `platform.oauth_states`; callback verifies and consumes; tokens saved to `platform.secrets` via envelope encryption; `platform.integrations`
  row per `(tenant, provider, carrier)` (extend unique index to include `subject_id`).
- Refresh coordinator: per integration lock using a Mongo lease (`find_one_and_update` on a `locked_until` field); only the lock holder calls the
  token endpoint; the new token pair is written in one update; losers wait and re-read. Failure after a spent refresh token -> status `error`,
  reason `reauthorize`, event `integration.error`, carrier flagged, nothing guessed.
- `eld_poll` job (every `ELD_POLL_MINUTES=5` per connected carrier with an open load): fetch current vehicle location, store on `trucks.last_location {lat, lon, at, source}`
  and `load_events` for geofence arrivals when a stop has coordinates; consent: ELD sharing needs `eld_data_consent` on the carrier record, granted by the carrier
  via the portal (ledger entry); without it the connect route refuses.
- Provider interface `EldProvider.current_location(vehicle_ref)`, `list_vehicles()`; fakes for tests; Motive and Samsara clients with injectable transports.
- DocuSeal: `POST /v1/carriers/{id}/agreement/send` (dispatcher) creates an `esign_agreement` approval (kind added) whose payload names the template
  and the carrier contact; apply posts to `/submissions` once. Webhook `submission.completed` downloads the signed document, stores it
  (Phase 3 pipeline), sets `carriers.agreement_doc_id` and `agreement_signed=true` through the core repo with `created_by={kind:"esign"}` and a
  ledger-like audit entry; the template text itself is the lawyer's responsibility (`DOCUSEAL_TEMPLATE_ID`).
- Portal agreement routes `GET|POST /v1/portal/agreement` return the signing link only.

### 6.3 Tests first

`test_oauth_state_mismatch_rejected`, `test_oauth_state_single_use_and_expires`, `test_tokens_encrypted_not_in_logs_or_responses`,
`test_samsara_refresh_token_replaced_atomically`, `test_concurrent_refresh_single_upstream_call`, `test_refresh_failure_marks_error_no_guess`,
`test_eld_requires_carrier_consent`, `test_eld_poll_updates_location_and_geofence_event`, `test_provider_contract_fake_vs_client_stubbed`,
`test_docuseal_webhook_rejected_without_verified_scheme`, `test_signed_agreement_sets_flag_once`, `test_reference_age_makes_bond_unknown`,
`test_reference_sync_idempotent`, `test_wrong_tenant_matrix_new_routes`.

### 6.4 Acceptance criteria

1. OAuth state is verified and single-use; tokens never appear in any response, log, or test snapshot.
2. Concurrent refreshes produce one upstream call; single-use refresh tokens are replaced atomically.
3. A failed refresh marks the integration `error`; no location is invented.
4. ELD sharing requires the carrier's consent.
5. The signed agreement is recorded exactly once; the webhook is authenticated by the verified scheme.
6. Stale bond data yields `unknown`. All gates green.

## 7. Finish

End your run with the report format in section 5: status first, then exact gate outputs, files changed, decisions, what was not verified, and founder actions.
