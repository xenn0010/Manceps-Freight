# Execution prompt: Phase 5 (voice-vapi)

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

## 6. Phase 5 brief: Vapi voice

**Prerequisites.** Phase 4 merged (consent, outbox, endpoints, webhook framework).

**Goal.** The firm's Vapi number answers calls with a disclosed AI, server tools read and write through the platform, call
reports become records, and outbound calls happen only with consent and a human approval.

### 6.1 Vendor facts

Verified:
- https://docs.vapi.ai/server-url/events : server messages `assistant-request` (answer within 7.5 s), `tool-calls`, `status-update`
  (`scheduled, queued, ringing, in-progress, forwarding, ended`), `end-of-call-report` (has `endedReason` and `artifact`: recording,
  transcript, messages). `tool-calls` request has `call`, `toolCallList[]` with `id`, `type`, `function{name, arguments}`.
  Response: `{"results":[{"name":"...","toolCallId":"...","result":"<string>"}]}`.
- https://docs.vapi.ai/server-url/setting-server-urls : server URL requests are authenticated by a Custom Credential
  (`server.credentialId`) attached to the server URL on account, phone number, assistant, or tool.
- https://docs.vapi.ai/api-reference/calls/create : `POST https://api.vapi.ai/call`, bearer private key; body `assistantId`,
  `phoneNumberId`, `customer.number` (E.164), `assistantOverrides.variableValues`; 201 returns a Call.
UNVERIFIED (must be resolved first): the exact authentication scheme of a Custom Credential (header name or HMAC). Open
https://docs.vapi.ai/server-url/server-authentication (or the page the setting-server-urls page links to) and implement exactly
that. Until the scheme is implemented and tested, the webhook handler rejects every request (401).

### 6.2 Design

- `integrations/vapi/client.py`: `create_call(assistant_id, phone_number_id, number, variables)` with timeout, retries only on 5xx and
  network errors (not on 4xx), injectable transport.
- Tenant resolution for inbound: `call.phoneNumberId` or the called number -> `endpoints (kind=voice)`. Unknown -> a safe generic
  response and no data access.
- Server tools, tenant-scoped through the endpoint, read through core repos:
  - `lookup_load_status(reference)`: only for callers whose number matches a carrier/driver/broker contact of the firm; returns
    status and ETA text; never rates or floors.
  - `take_broker_offer(...)`: stores an offer as a `loads` row in `offered` (source `call`), links the broker by MC when given, emits
    `load.offered`, returns "The dispatcher will confirm." It never accepts or counters a rate (rule 3).
  - `log_driver_issue(...)`: creates a note and an event; urgent flag raises a `dispatcher_alert` event.
- `end-of-call-report`: dedupe by call id; create `calls` row with summary, structured data (schema in
  `hermes-freight/vapi/assistant.json` `analysisPlan`), transcript saved as a document (Phase 3), `ai_disclosed` true only if the
  assistant first message contains the disclosure; then enqueue an `agent_commands` `inbound_message` with the summary as untrusted data.
- Outbound: `POST /v1/calls/outbound` (dispatcher) validates `can_contact(phone, "voice")` (422 `no_consent`), creates an `outbound_call`
  approval (kind added to the registry; payload: phone, purpose, assistant id, script variables, max duration); on approval the apply
  action enqueues job `vapi_outbound` which re-checks consent and the allowed window and then posts `/call` once (job idempotency key =
  approval id). Allowed local window setting `CALL_WINDOW_LOCAL = (8, 21)` in the recipient's timezone from the area code table (build a small
  area-code to timezone map; unknown -> hold and ask the dispatcher). The window values are placeholders for the lawyer (UNVERIFIED).
- `deploy/vapi_sync.py` (VM or laptop, uses `VAPI_API_KEY`): updates the assistant from `vapi/assistant.json`, sets the server URL and
  credential id, and refuses to push if `firstMessage` lacks "AI". Update `assistant.json` model to the current default
  if the founder wants (do not guess a model id; leave as is and note it).
- Vapi-bought numbers have a daily outbound cap (HANDOFF); handle a 400 limit error as a retry-tomorrow `send_after`.

### 6.3 Tests first

`test_webhook_rejects_without_credential`, `test_webhook_credential_scheme_matches_docs` (written after you read the docs),
`test_tool_calls_response_shape`, `test_unknown_number_safe_response`, `test_lookup_never_returns_rates`, `test_take_offer_creates_offered_load_only`,
`test_end_of_call_report_idempotent`, `test_report_text_wrapped_untrusted`, `test_injection_in_transcript_no_state_change`,
`test_outbound_requires_consent_and_approval`, `test_outbound_single_post_on_retry`, `test_outbound_window_hold`, `test_assistant_has_ai_disclosure`,
`test_assistant_request_latency_under_7s`, `test_wrong_tenant_matrix_new_routes`.

### 6.4 Acceptance criteria

1. Unauthenticated Vapi requests are 401.
2. `tool-calls` responses match the verified shape.
3. Offers become `offered` loads and nothing more; no rate is ever accepted by voice tools.
4. A duplicated end-of-call report creates one call row.
5. Outbound without voice consent is 422; with consent it needs an approval and posts to Vapi exactly once.
6. Calls outside the window are held.
7. All gates green.

### 6.5 Do not do

No live calls. No changes to the Vapi account from tests. Do not remove AI disclosure or recording notice from the greeting.

## 7. Finish

End your run with the report format in section 5: status first, then exact gate outputs, files changed, decisions, what was not verified, and founder actions.
