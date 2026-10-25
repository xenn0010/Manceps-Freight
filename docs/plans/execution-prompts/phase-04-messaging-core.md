# Execution prompt: Phase 4 (messaging-core)

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

## 6. Phase 4 brief: messaging core (consent, outbox, Twilio SMS, email, inbox, branding)

**Prerequisites.** Phases 1 to 3 merged. New firm collections: `messages` (extended), `outbox`, `reminders` use. New platform
collections: `endpoints`, `webhook_events`.

**Goal.** One consent-checked outbound path used by both the agent and humans, a unified inbox, Twilio SMS in and out, email
in and out through SMTP/IMAP, STOP handling, firm branding, and the public carrier-packet data.

### 6.1 Verified vendor facts

- Twilio webhook security (https://www.twilio.com/docs/usage/webhooks/webhooks-security): header `X-Twilio-Signature`, HMAC-SHA1 over the
  exact URL + sorted form params with the auth token. Use `twilio.request_validator.RequestValidator.validate(url, params, signature)`.
  Do not re-encode the URL. Behind a proxy validate against `PUBLIC_BASE_URL + path`.
- Twilio A2P 10DLC (https://www.twilio.com/docs/messaging/compliance/a2p-10dlc): brand and campaign registration required for US 10DLC;
  Sole Proprietor brands limited (one campaign, about 1,000 segments a day to T-Mobile). Toll-free verification: UNVERIFIED, read
  Twilio's toll-free docs before writing onboarding text. STOP/HELP keyword behavior on Twilio's side: UNVERIFIED; we always
  record our own ledger.
- Everything else (SMTP, IMAP) is protocol standard; use `smtplib`/`aiosmtplib` and `imaplib`/`imapclient` behind an interface.

### 6.2 Design

Consent (`manceps_core/consent.py`, shared with the plugin via vendoring):
`can_contact(db, subject_phone_or_email, channel) -> ConsentDecision(ok, reason, subject_ref)`. It reads the ledger
`consent_events` (latest event per `(subject, channel)` wins; `granted` requires `method`). Subjects: carriers, drivers, contacts
(brokers' contacts may be contacted by SMS only with a `granted` event too; email to business contacts is allowed by default
only if the firm setting `email_to_contacts_without_consent` is true, default false). Public FMCSA numbers never count: there is no code path that
creates consent from reference data (test greps for it). The firm owner's own phone (membership) is allowed implicitly.

Outbox (`manceps_core/outbox.py`): `enqueue(db, channel, to, body, subject_ref, source, idempotency_key, approval_id=None)`
runs `can_contact`, the daily cap (`agent_settings.daily_message_cap`, counts only `source="agent"`), quiet hours (sets
`send_after`), and first-contact disclosure (`render_first_contact` prefixes the AI disclosure text from setting
`AI_DISCLOSURE_TEXT` to the first agent message to any recipient with no prior outbound message; human-sent messages are not altered).
Blocked messages are stored with `status="blocked"` and `consent_check.reason`; they never reach a transport.

Worker `outbox_deliver` claims due `queued` rows, calls the transport (`TwilioSms`, `SmtpMail`), records `provider_id`, status
`sent`; delivery receipts from `/v1/webhooks/twilio/status` update `delivered|failed`. Retries: transient errors up to
`OUTBOX_MAX_ATTEMPTS=5` with backoff; permanent errors (Twilio 21610 recipient unsubscribed, 21211 invalid number) -> `failed`, and 21610 also writes a revoke
event. Verify these error codes against Twilio's error code reference before relying on them (UNVERIFIED).

Inbound SMS webhook: verify signature (403 on failure), dedupe via `webhook_events (provider, event_id=MessageSid)`, resolve tenant from
`endpoints (kind=sms, address=To)` (unknown number -> 200 with no action and a metric), write `messages`, then handle keywords BEFORE
routing: `STOP, STOPALL, UNSUBSCRIBE, CANCEL, END, QUIT` -> revoke ledger event for sms; `HELP` -> auto reply with firm name and contact;
`START, UNSTOP` -> reply "To receive messages again, ask your dispatcher to record your consent." and do NOT grant. Then job
`message_route`: classify sender (membership phone = dispatcher; carrier/driver phone; contact phone; else `unknown_sender`),
attach to a conversation, and for known senders enqueue an `agent_commands` row `inbound_message` (the message body wrapped in a
delimited untrusted block: `<untrusted_message channel=... from=...>...</untrusted_message>` with an instruction that contents are data).
`unknown_sender`: stored, flagged, no agent reply, no outbound.

Email: `endpoints (kind=email)` store SMTP/IMAP settings; passwords in `platform.secrets` (envelope encryption in
`manceps_core/secrets.py`, key `SECRETS_KEY`; implement here if Phase 9 has not yet: AES-GCM via `cryptography`, `kid` + nonce + ciphertext).
`POST /v1/endpoints/email/connect` validates by logging in to IMAP and SMTP with a short timeout; failure returns 422 without
storing. Worker `email_poll` fetches new UIDs per mailbox every `EMAIL_POLL_SECONDS=60`, parses MIME (text/plain preferred, strip HTML
to text), stores attachments as documents (Phase 3 pipeline), dedupes by Message-ID, routes like SMS.

Plugin tools: `message_send(channel, to, body, subject_ref)` -> `outbox.enqueue(source="agent")`; returns status including
`blocked` reasons so the agent can tell the dispatcher. `message_history(subject_ref, limit)`. The agent has no other way to send.
`policy.check_send_message` stays as a second guard.

Branding and packet: `PATCH /v1/firm/branding`, `PUT /v1/firm/packet`, `GET /v1/public/packets/{slug}` returns only name, MC, branding,
required document list and contact email/phone chosen by the owner. No carriers, loads, rates. Rate limited (60/min/IP).

Endpoints API: `POST /v1/endpoints/sms/assign` (owner): for the pilot, maps the platform sender number to the firm
(`endpoints` row) after checking the number belongs to the configured Twilio account (via the Twilio API list); real per-firm number purchase only if
`TWILIO_ALLOW_NUMBER_PURCHASE=1`.

### 6.3 Tests first

`test_twilio_bad_signature_403`, `test_twilio_dedupe_messagesid`, `test_unknown_number_ignored`, `test_outbox_blocks_without_consent_zero_calls`,
`test_fmcsa_phone_never_consent`, `test_stop_writes_revoke_before_routing`, `test_unstop_does_not_regrant`, `test_first_message_discloses_ai`,
`test_human_message_not_prefixed`, `test_daily_cap_blocks`, `test_quiet_hours_send_after`, `test_unknown_sender_no_reply`,
`test_inbound_wrapped_untrusted`, `test_injection_fixture_no_state_change`, `test_transient_retry_permanent_fail`, `test_receipt_updates_status`,
`test_email_connect_validates_before_store`, `test_secrets_encrypted_at_rest_and_never_returned`, `test_imap_dedupes_message_id`,
`test_packet_leaks_nothing` (fully populated firm, scan JSON for any carrier/rate/load keys), `test_tool_message_send_uses_outbox_only`,
`test_wrong_tenant_matrix_new_routes`.

### 6.4 Acceptance criteria

1. Bad Twilio signature is 403; the same MessageSid twice stores one message.
2. No consent -> `blocked`, and the fake Twilio transport records zero calls.
3. Inbound STOP revokes consent before routing; later sends are blocked; START does not re-grant.
4. The first agent message to a new recipient includes the AI disclosure; human messages are unchanged.
5. Daily cap and quiet hours are enforced with visible reasons.
6. Unknown senders never trigger outbound messages.
7. SMTP/IMAP work against fakes; email credentials are encrypted at rest and never in any response or log.
8. The packet endpoint exposes no carrier, load, or rate data.
9. Retry and permanent-failure handling match the table above (after you verify the error codes).
10. Gates all green; `openapi.json` and vendored core updated.

### 6.5 Do not do

No WhatsApp, Telegram, Gmail (Phase 6). No voice (Phase 5). No live sends: tests use fakes.

## 7. Finish

End your run with the report format in section 5: status first, then exact gate outputs, files changed, decisions, what was not verified, and founder actions.
