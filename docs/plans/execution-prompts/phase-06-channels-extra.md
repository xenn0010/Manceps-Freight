# Execution prompt: Phase 6 (channels-extra)

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

## 6. Phase 6 brief: WhatsApp Cloud API, Telegram, Gmail

**Prerequisites.** Phase 4 merged.

**Goal.** Three more channels share the same consent, outbox, inbox, and routing code.

### 6.1 Vendor facts

- WhatsApp Cloud webhooks (https://developers.facebook.com/docs/whatsapp/cloud-api/guides/set-up-webhooks, verified): payload shape
  `object`, `entry[].changes[].value{messaging_product, metadata{display_phone_number, phone_number_id}, contacts[], messages[]{from,id,timestamp,type,text.body}}`;
  up to 3 MB; non-200 responses retried with decreasing frequency up to 7 days; duplicates possible -> dedupe on message id.
- Local Hermes doc `hermes-agent/website/docs/user-guide/messaging/whatsapp-cloud.md` describes the GET verify-token challenge and using
  the App Secret to verify inbound signatures. UNVERIFIED against Meta: signature header name (believed `X-Hub-Signature-256`, sha256 HMAC
  of the raw body), the 24-hour customer-service window, template rules, outbound endpoint and payloads. Read Meta's pages
  (webhook creation, messages, templates) first and cite them in the report.
- Gmail push (https://developers.google.com/gmail/api/guides/push, verified): `users.watch` with Pub/Sub topic; grant publish to
  `gmail-api-push@system.gserviceaccount.com`; renew at least every 7 days (recommended daily); notification has `emailAddress` and
  `historyId`; call `history.list` from the last stored `historyId`; max one notification per second per user; notifications may be
  delayed or dropped, so also poll. UNVERIFIED: restricted-scope requirements (read mail is restricted), OAuth verification time,
  Pub/Sub push authentication (OIDC token) details. Read them and cite.
- Telegram Bot API: UNVERIFIED. Read https://core.telegram.org/bots/api for `setWebhook` (`secret_token`, header
  `X-Telegram-Bot-Api-Secret-Token`), `sendMessage`.

### 6.2 Design

- WhatsApp: `integrations/whatsapp/{client,webhook}.py`. GET handler echoes `hub.challenge` only when `hub.verify_token` matches
  `WHATSAPP_VERIFY_TOKEN` (constant-time compare). POST verifies the signature with `WHATSAPP_APP_SECRET` before parsing; resolves
  the tenant from `metadata.phone_number_id` -> `endpoints (kind=whatsapp)`; dedupes; stores; routes as in Phase 4. Outbound: free-form
  text only inside the service window per the verified rules; otherwise only an approved template name from a firm-level
  `whatsapp_templates` list; else the outbox row is `blocked: outside_window`. Consent channel `whatsapp` required.
- Telegram: webhook path `/v1/webhooks/telegram/{secret}` with the header check; dispatcher-only channel: sender must match
  `memberships` mapping stored when the dispatcher links their Telegram account with a one-time code from `POST /v1/endpoints/telegram/link`.
  Carriers cannot use Telegram.
- Gmail: OAuth 2.0 authorization code with PKCE, `state` stored server-side with 10-minute TTL, tokens encrypted in `platform.secrets`.
  Scopes: request the narrowest set that works (gmail.readonly + gmail.send, or gmail.modify if needed) and state the choice in the report.
  Routes: `GET /v1/integrations/gmail/connect` (returns URL), `GET /v1/integrations/gmail/callback`. Worker: `gmail_watch_renew` daily per
  mailbox, `gmail_history_sync` on push and every 5 minutes as a safety poll. Push endpoint `/v1/webhooks/gmail` verifies the Google-signed
  JWT (audience = our URL). Inbound mail handled like Phase 4 email.
- Each integration reports `not_configured` (503) without env: `WHATSAPP_APP_SECRET, WHATSAPP_VERIFY_TOKEN, WHATSAPP_ACCESS_TOKEN`;
  `TELEGRAM_BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET`; `GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET, GOOGLE_PUBSUB_TOPIC`.

### 6.3 Tests first

`test_whatsapp_challenge_only_with_token`, `test_whatsapp_bad_signature_403`, `test_whatsapp_dedupe`, `test_whatsapp_no_consent_blocked`,
`test_whatsapp_outside_window_needs_template`, `test_telegram_wrong_secret_403`, `test_telegram_only_linked_dispatcher`,
`test_gmail_state_mismatch_rejected`, `test_gmail_tokens_encrypted_never_returned`, `test_gmail_watch_renew_daily`,
`test_gmail_lost_push_recovered_by_poll`, `test_gmail_push_jwt_verified`, `test_all_channels_not_configured_503`, `test_wrong_tenant_matrix_new_routes`.

### 6.4 Acceptance criteria

1. WhatsApp webhook verification and signature checks work; duplicates are ignored.
2. No outbound WhatsApp without consent; outside-window sends need a template.
3. Telegram works for the linked dispatcher only.
4. Gmail OAuth state is verified; tokens are encrypted; watch is renewed daily; a missed push is recovered by polling.
5. Each channel is `not_configured` without credentials. All gates green.

## 7. Finish

End your run with the report format in section 5: status first, then exact gate outputs, files changed, decisions, what was not verified, and founder actions.
