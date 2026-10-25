# Manceps platform plan, part 4: integration matrix

Every integration has: a client class, a **fake transport** (used in all tests), and a `not_configured` state
(routes answer 503 `integration_not_configured`; features that depend on it turn off, checks never pass by default).

Verification legend:

- **VERIFIED** = I opened the official page this session. URL listed.
- **LOCAL-DOC** = read in the cloned Hermes docs under `hermes-agent/website/docs`.
- **IN-CODE** = already used by working code in this repo (HANDOFF says live-tested), docs not re-opened now.
- **SEARCH-ONLY** = a search result summary only; the page was not opened.
- **UNVERIFIED** = from memory or assumption. The build agent must verify before coding against it.

## 1. Data store and infrastructure

### MongoDB Atlas
- Use: all state. Admin API to create per-firm database users (`provision_tenant.py` already does this).
- VERIFIED limits (https://www.mongodb.com/docs/atlas/reference/free-shared-limitations/):
  Free 0.5 GB; 500 connections; 100 ops/s; **100 databases and 500 collections total**; 10 GB in and 10 GB out per rolling
  7 days; throttling when exceeded; change-stream namespace filters limited to strings and regexes.
- VERIFIED limits (https://www.mongodb.com/docs/atlas/reference/atlas-limits/): **100 database users per project**;
  recommended maximum collections plus indexes: M10 5,000; M20/M30 10,000; M40+ 100,000; new-connection rate 15/s per node on
  M10 and M20.
- Create user: `POST /api/atlas/v2/groups/{id}/databaseUsers` with `roles[{roleName, databaseName}]` and `scopes`.
  **UNVERIFIED**: the Admin API reference page did not render for me; the endpoint comes from memory and from
  `provision_tenant.py`, which was not run in scoped mode (the pilot used shared credentials). Phase 12 must test it
  against a real Atlas project first.
- Credentials from founder: `MONGODB_URI` (operator, readWriteAnyDatabase for API/worker), platform-only URI for the old
  signup API, `ATLAS_PUBLIC_KEY/PRIVATE_KEY/GROUP_ID/CLUSTER` (Project Owner API key) for scoped users.
- Failure: Atlas down -> `/readyz` 503, API routes 503 `database_unavailable`, jobs retry with backoff. Never serve stale auth.
- Upgrade trigger: before the 8th paying firm, and always before a public launch (D10, part 1).

### Cloudflare R2 (documents)
- VERIFIED (https://developers.cloudflare.com/r2/api/s3/presigned-urls/): presigned GET/HEAD/PUT/DELETE, expiry 1 s to 7
  days; POST form uploads unsupported; presigned URLs not usable on custom domains; AWS SigV4; endpoint
  `<ACCOUNT_ID>.r2.cloudflarestorage.com`; Content-Type can be pinned at signing.
- Env: `R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET`. Client: `boto3` with endpoint override.
- Failure: R2 down -> uploads 503, downloads 503, nothing marked `available` without a stored object and matching sha256.
- UNVERIFIED: price, egress fees, object lock/versioning. Founder creates the bucket and a scoped API token.

### Container host for API and worker
- UNVERIFIED. Recommended Fly.io; alternatives Render, Railway, Google Cloud Run (worker needs always-on CPU, which makes
  Cloud Run a poor fit unless min instances = 1). Founder picks; the plan only needs Docker, HTTPS, secrets, two processes.

### Virus scan
- ClamAV (`clamd`) as a sidecar container; client `pyclamd` or raw INSTREAM socket. UNVERIFIED version and memory need
  (ClamAV usually wants about 1 GB RAM; check). When clamd is down the document stays `scanning` and never becomes
  `available` (fail closed).

## 2. Messaging

### Twilio Verify (OTP login), already built
- IN-CODE (`signup-api/signup_api/verify.py`, Verify v2). Env: `TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_VERIFY_SERVICE_SID`.
- Failure: unset -> 503; outage -> 502; only status `approved` verifies (existing tests).

### Twilio SMS (firm number, inbound and outbound)
- Webhook security VERIFIED (https://www.twilio.com/docs/usage/webhooks/webhooks-security): `X-Twilio-Signature`, HMAC-SHA1
  over the exact URL plus sorted form params; use `twilio.request_validator.RequestValidator`; do not re-encode the URL.
  Behind a proxy the validated URL must be the public URL (`PUBLIC_BASE_URL` setting).
- A2P 10DLC VERIFIED (https://www.twilio.com/docs/messaging/compliance/a2p-10dlc): brand and campaign registration are
  required for US 10DLC; standard brands need an EIN; Sole Proprietor brands get one campaign and about 1,000 segments a
  day to T-Mobile (about 3,000 across US carriers). Toll-free and short codes are separate paths (toll-free verification
  details UNVERIFIED).
- Plan: Phase 4 sends from **one toll-free or 10DLC number registered to Manceps** as the platform sender for pilot firms,
  and records `endpoints` per firm only when per-firm numbers are approved. Opt-out: the platform handles STOP, UNSTOP and
  HELP itself (Twilio also acts on standard keywords; exact behavior UNVERIFIED, so we write the ledger either way).
- Env: `TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_MESSAGING_SERVICE_SID, PUBLIC_BASE_URL`.
- Founder: Twilio account upgrade, brand + campaign registration (takes days or weeks, UNVERIFIED), number purchase.
- Failure: unset -> outbox rows go `blocked: integration_not_configured`; the agent is told.

### WhatsApp Cloud API
- VERIFIED partly (https://developers.facebook.com/docs/whatsapp/cloud-api/guides/set-up-webhooks): payload
  `entry[].changes[].value.messages[]` with `from, id, timestamp, type, text.body`, `metadata.phone_number_id`; payloads up to
  3 MB; non-200 responses are retried with decreasing frequency for up to 7 days; duplicates possible.
- LOCAL-DOC (`hermes-agent/.../whatsapp-cloud.md`): GET challenge with verify token; App Secret used to verify inbound
  signatures. The header name `X-Hub-Signature-256` is **UNVERIFIED** against Meta's page.
- UNVERIFIED: 24-hour customer-service window and template-message rules, business verification time, pricing.
- Env: `WHATSAPP_APP_SECRET, WHATSAPP_VERIFY_TOKEN, WHATSAPP_ACCESS_TOKEN`; per firm `phone_number_id`, `waba_id` in `endpoints`.
- Rule: no outbound WhatsApp without consent on file for `whatsapp`. Baileys (unofficial) is **not** used (HANDOFF: ToS).

### Telegram
- UNVERIFIED (docs not opened). Plan: Bot API `setWebhook` with a secret token; verify the header and a secret path segment.
  Optional channel for the dispatcher only (not carriers).

### Email
- Phase 4 baseline: generic SMTP send + IMAP poll (works with any provider). Hermes has its own IMAP adapter
  (LOCAL-DOC `email.md`) but we do not use it (consent and storage live in the platform).
- Phase 6: Gmail API with OAuth. VERIFIED (https://developers.google.com/gmail/api/guides/push): `users.watch` with a Pub/Sub
  topic; must renew at least every 7 days (recommend daily); notification carries `emailAddress` and `historyId`; fetch with
  `history.list`; one notification per second per user; notifications can be delayed or lost, so also poll `history.list`.
  UNVERIFIED: restricted-scope review and verification time (reading mail is a restricted scope; expect a Google security
  assessment before public launch). Until verified, Gmail runs in "testing" mode for up to 100 named test users (UNVERIFIED).
- Magic-link email uses the same SMTP transport. Env: `SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, MAIL_FROM`.
- Founder: sending domain with SPF, DKIM, DMARC set up (otherwise magic links land in spam).

## 3. Voice

### Vapi
- VERIFIED (https://docs.vapi.ai/server-url/events): server message types `assistant-request` (respond within 7.5 s),
  `tool-calls` (request has `call`, `toolCallList[]{id, type, function{name, arguments}}`; response
  `{"results":[{"name","toolCallId","result":"<string>"}]}`), `status-update`, `end-of-call-report` (includes
  `endedReason` and `artifact` with recording, transcript, messages).
- VERIFIED (https://docs.vapi.ai/server-url/setting-server-urls): requests are authenticated by attaching a **Custom
  Credential** (`server.credentialId`) to the server URL; configurable per account, phone number, assistant, or tool.
  The credential's exact scheme (header name or HMAC) was **not** in the page. Phase 5 must open the Vapi
  "server-authentication" page and implement exactly that; until then the webhook rejects everything (fail closed).
- VERIFIED (https://docs.vapi.ai/api-reference/calls/create): outbound `POST https://api.vapi.ai/call`, bearer private key;
  body `assistantId, phoneNumberId, customer.number (E.164), assistantOverrides.variableValues`; 201 returns a Call.
- IN-CODE: live inbound number +16198262038, `vapi/assistant.json` discloses AI and recording. Vapi-bought numbers have a
  daily outbound cap (HANDOFF).
- Server tools exposed to the assistant (Phase 5): `lookup_load_status`, `take_broker_offer` (stores the offer, never accepts
  a rate), `log_driver_issue`. They read through the same core repo; they cannot read other firms (tenant resolved from the
  called number in `endpoints`).
- Env: `VAPI_API_KEY, VAPI_WEBHOOK_CREDENTIAL, VAPI_ASSISTANT_ID, VAPI_PHONE_NUMBER_ID`.
- Outbound rule: only after consent (`voice`) and an `outbound_call` approval, AI disclosure in `firstMessage`, call hours
  limited to 8:00-21:00 recipient local time (**UNVERIFIED legal window; lawyer confirms**).

## 4. Reference and operations data

### FMCSA QCMobile (broker vetting)
- SEARCH-ONLY (https://mobile.fmcsa.dot.gov/QCDevsite/docs/getStarted): free WebKey from a Login.gov account; base
  `https://mobile.fmcsa.dot.gov/qc/services`; key as `webKey` query param; endpoints include `/carriers/{dot}` and
  `/carriers/name/{name}`. A third-party note says insurance fields are missing in responses (matches HANDOFF: bond check
  stays manual/`unknown`). IN-CODE: `broker_check.py` uses it live.
- Env: `FMCSA_WEBKEY`. Failure: unknown, never pass.

### data.transportation.gov (Socrata)
- IN-CODE: datasets `az4n-8mr2` (census) and `qh9u-swkp` (insurance). HANDOFF: insurance data last updated 2023-12-06.
  Phase 9 schedules `reference.sync` weekly and exposes the dataset age; any bond result older than 90 days is `unknown`.

### EIA diesel, NWS weather, Google Routes, OpenRouteService
- IN-CODE (`loads.py`, `weather.py`); HANDOFF reports live tests: Google Routes (DRIVE mode, 783 mi), EIA series
  `EMD_EPD2D_PTE_NUS_DPG`, NWS `api.weather.gov` (11 alerts returned). Docs not re-opened.
- Env: `EIA_API_KEY, GOOGLE_MAPS_API_KEY, ORS_API_KEY, FREIGHT_CONTACT_EMAIL` (NWS User-Agent contact).
- Platform route `POST /v1/loads/{id}/evaluate` reuses the same code via core (moved out of the plugin in Phase 1 with the
  plugin importing it back; the plugin tests stay green).

### Motive and Samsara (ELD, OAuth per carrier)
- Samsara VERIFIED (https://developers.samsara.com/docs/oauth-20): authorize `https://api.samsara.com/oauth2/authorize`
  (`client_id, state > 8 chars, response_type=code`); token `https://api.samsara.com/oauth2/token` with Basic auth; scopes
  `admin:read`, `admin:write`; access token about 1 hour; **refresh tokens are single use** (store the new pair after every
  refresh, never refresh concurrently, re-auth if a refresh fails after the old token is spent); code expires in 10
  minutes; webhooks not covered by that page (UNVERIFIED).
- Motive SEARCH-ONLY (https://developer-docs.gomotive.com/docs/oauth-20, https://developer.gomotive.com/reference/authentication-oauth-20):
  OAuth 2.0 authorization code; token endpoint `https://api.gomotive.com/oauth/token` (from the result snippet); app
  registration requires Motive support to enable a developer account; scopes include Vehicles, Users, HOS, Locations;
  request all scopes at once (re-consent otherwise). Refresh behavior and webhooks UNVERIFIED. My direct fetch of
  `developer.gomotive.com/docs/oauth-authorization` returned 404.
- Per-carrier tokens stored in `platform.secrets` (envelope encrypted, `SECRETS_KEY`). A per-carrier lock serializes refresh.
- Founder: Samsara partner app, Motive developer account approval. Both are slow; start in Phase 9 week 1.
- Failure: token refresh failure -> integration `error`, carrier flagged, no location guessed.

### DocuSeal (e-sign dispatch agreement)
- VERIFIED (https://www.docuseal.com/docs/api): `X-Auth-Token` header; `POST /submissions` from a template to submitters by
  email or phone; webhook events `form.completed`, `submission.completed`, etc.; failed webhook deliveries retried for 48
  hours on production; cloud hosts `api.docuseal.com` and `api.docuseal.eu`, self-host possible.
- UNVERIFIED: how webhook requests are authenticated (page silent). Phase 9 reads the example request or SDK docs.
  Webhook handler refuses requests that do not match the documented scheme.
- Template text must come from a transportation lawyer (HANDOFF). Env: `DOCUSEAL_API_KEY, DOCUSEAL_TEMPLATE_ID, DOCUSEAL_WEBHOOK_SECRET`.

## 5. Money

### Stripe (platform subscription, Phase 7)
- VERIFIED (https://docs.stripe.com/webhooks): verify `Stripe-Signature` against the raw body with the `whsec_` secret; default
  tolerance 5 minutes (never 0); return 2xx fast and process asynchronously; events can be duplicated and arrive out of
  order, so dedupe on event id and fetch current objects; automatic retries for up to 3 days in live mode; up to 16 event
  destinations; thin vs snapshot payloads (we use snapshot, simpler with the Python SDK).
- Objects: Customer, Subscription (trial), Checkout Session, Billing Portal session. Plan limits live in `billing_accounts.limits`.
- Dunning states: `active`, `trialing`, `past_due` (read-only after 7 days, UNVERIFIED policy choice), `canceled`. The agent
  keeps answering the dispatcher in `past_due`; outbound messaging pauses.
- Env: `STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, STRIPE_PRICE_IDS` (JSON map plan->price). Founder creates products in test mode first.

### Stripe Connect + ACH (dispatch fee invoices to carriers, Phase 8)
- VERIFIED (https://docs.stripe.com/payments/ach-direct-debit): settlement up to 4 business days (T+2 optional for eligible
  accounts); confirmation delayed; bank must be verified (Financial Connections or microdeposits, 10 days to finish);
  **mandate required** and Stripe stores it when using hosted Checkout, Payment Element or the hosted invoice page; business
  account debits disputable for 2 business days, personal for 60 days; failed payments can arrive after "succeeded" and
  become disputes with a failure fee; billing retries for ACH max 2 and within 40 days; Connect needs capability
  `us_bank_account_ach_payments`; Invoicing and Billing are supported products.
- UNVERIFIED: which Connect account type and charge type fit; whether the platform needs a money-transmission review;
  Connect onboarding time; fees. Decision gate: lawyer sign-off before any live charge (part 6).
- Webhooks for connected accounts need a second event destination scope (VERIFIED in the same webhooks page).

### Factoring (OTR Solutions) and email fallback
- SEARCH-ONLY (https://docs.otrsolutions.com/docs/carrier-integrations, https://otrsolutions.com/developer-resources):
  three APIs listed: Rate Verification, Document Exchange (invoices, rate cons, PODs), Carrier Setup. Authentication,
  endpoints and access terms UNVERIFIED; access likely needs an OTR account.
- Plan: `FactoringProvider` interface with `EmailFactoring` (works for any factor: PDF package to the factor's submission
  address, firm-configured) and `OtrFactoring` (behind a flag, built only after OTR docs are read). Sending always passes
  the `send_invoice` approval.

## 6. Load sources (legal ones only)

- Inbound broker email and calls: Phases 2, 5, 10. This is the primary source.
- 123Loadboard: SEARCH-ONLY (https://123loadboard.com/api): partner program; endpoints cover search loads/trucks, rate
  checks, bids and bookings; developer portal is behind a login; "begin by becoming a partner". Phase 10 builds the adapter
  interface and a fake only; real calls wait for partner access. Founder applies at the start of Phase 1.
- DAT: not integrated. HANDOFF says DAT's terms ban bots without written approval (UNVERIFIED by me this session). Build only
  with written approval from DAT.
- No scraping, no browser automation of load boards. `browser` is already in `disabled_toolsets`; a CI test greps the
  repo for board domains in automation code.

## 7. Hermes (agent runtime), LOCAL-DOC

- `hermes-agent/website/docs/user-guide/features/api-server.md`: `POST /v1/runs` (202, `run_id`), `GET /v1/runs/{id}` (poll),
  `GET /v1/runs/{id}/events` (SSE with `tool.started`, `tool.completed`, `message.delta`, `run.completed`), `POST
  /v1/runs/{id}/stop`, `Idempotency-Key` (24 h ledger), `X-Hermes-Session-Id`, per-profile `/p/<profile>/` prefix with that
  profile's own `API_SERVER_KEY`, `GET /health`, `GET /v1/capabilities`. Run state is retained only briefly after it ends.
- Env per profile (written by `provision_tenant.py` in Phase 2): `API_SERVER_ENABLED=true`, `API_SERVER_KEY=<random>`.
- UNVERIFIED on the VM: multiplexed routing with 2+ profiles, event names in the pinned commit `1c0cd66774` (docs are from
  the clone; the pin matches), behavior of a plugin `approve` directive over the API. Phase 2 starts with a spike test.
