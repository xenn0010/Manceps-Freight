# Execution prompt: Phase 1 (core)

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

## 6. Phase 1 brief: core backend

**Goal.** After this phase a frontend can: sign a dispatcher up, log them in, run the firm (carriers, drivers, trucks,
brokers, contacts, facilities, notes), import spreadsheets, manage loads through the lifecycle, decide approvals, and receive
live updates. No agent is needed yet. Everything is covered by tests and a committed `openapi.json`.

Run this phase as five work packages (WP1.1 to WP1.5). Each ends with a green run of gates 1 to 5. If your context is short,
stop after a WP, report, and continue in a new session from the next WP.

### 6.1 What exists (read these files first)

- `hermes-freight/carriers.py` (field rules: `EQUIPMENT_TYPES`, `MAX_FEE_PCT=25.0`, `normalize_phone`, consent shape
  `{sms, voice, whatsapp, method}`), `hermes-freight/brokers.py` (MC digits, tag rule `^[a-z][a-z0-9_]{1,31}$`, max 10 tags,
  note max 1000 chars), `hermes-freight/store.py` (collections `carriers`, `brokers`, `broker_checks`, `audit`; indexes),
  `hermes-freight/tenant.py` (`database_name`: `firm_` + id with `-` replaced by `_`; id regex `^[a-z][a-z0-9-]{1,30}[a-z0-9]$`),
  `hermes-freight/broker_check.py`, `hermes-freight/reference.py`, `hermes-freight/loads.py` (`load_evaluate` math),
  `hermes-freight/policy.py`, `hermes-freight/tests/conftest.py` (mongomock pattern).
- `signup-api/signup_api/{app,store,verify}.py` and its tests: phone normalization, Twilio Verify client, rate-limit store
  (`signup_attempts`), queue insert into `platform.signups`. Port, do not import across projects.
- `hermes-freight/deploy/signup_worker.py`: claims `platform.signups` and provisions; it sets `status="ready"` and `tenant_id`.
  Do not change it in this phase.
- Data written by the plugin (carriers, brokers) must stay readable by the plugin: keep existing field names and the unique
  indexes `carriers.phone` and `brokers.mc_number`. New fields are additive.

### 6.2 Layout to create

```
backend/
  pyproject.toml     name manceps-platform; deps: fastapi, uvicorn[standard], pydantic>=2, pydantic-settings, pymongo>=4.10,<5,
                     PyJWT[crypto], structlog, openpyxl, python-multipart, httpx, phonenumbers is NOT used (reuse the US rule);
                     vCard: pick one maintained parser and pin it, or write a small RFC 6350 reader with tests;
                     dev: pytest, pytest-cov, mongomock, ruff, pyright, httpx
  manceps_core/ manceps_api/ manceps_worker/ tests/ scripts/ openapi.json
```

pyright config: `typeCheckingMode = "strict"`, ruff select `E,F,I,B,UP,BLE,S` (ignore `S101` in tests), line length 120.
mongomock warning filter like `signup-api/pyproject.toml`.

### 6.3 Settings (env vars; all via `manceps_api/settings.py`, `SecretStr` for secrets)

`ENV` (dev|test|production), `MONGODB_URI`, `PLATFORM_DB=platform`, `JWT_ACTIVE_KID`, `JWT_KEYS_JSON` (map kid -> {private_pem?,
public_pem}), `ACCESS_TOKEN_MINUTES=15`, `REFRESH_TOKEN_DAYS=30`, `SCOPED_TOKEN_MINUTES=60`, `PUBLIC_BASE_URL`, `CORS_ORIGINS`,
`COOKIE_DOMAIN`, `TRUST_PROXY=0`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_VERIFY_SERVICE_SID`,
`EMAIL_LOGIN_ENABLED=0`, `SMTP_HOST/PORT/USER/PASSWORD`, `MAIL_FROM`, `FMCSA_WEBKEY`, `EIA_API_KEY`, `GOOGLE_MAPS_API_KEY`,
`ORS_API_KEY`, `FREIGHT_CONTACT_EMAIL`, `SECRETS_KEY`, `IMPORT_MAX_BYTES=10485760`, `IMPORT_MAX_ROWS=20000`,
`IMPORT_UNDO_HOURS=24`, `LOG_LEVEL=INFO`. Add `scripts/gen_keys.py` that prints a new Ed25519 key pair JSON and a
`SECRETS_KEY` (32 random bytes, urlsafe base64) to stdout only.

### 6.4 Tenancy (WP1.1)

- `manceps_core/tenancy.py`: `Principal(user_id, tenant_id, role, session_id, kind)` frozen dataclass; `TenantDb` with
  `for_principal(principal) -> Database` returning `client["firm_" + tenant_id.replace("-", "_")]` after validating the id with
  the same regex as the plugin. There is no function that takes a tenant string from a request.
- `PlatformRepo(db, tenant_id)` wraps platform collections and injects `{"tenant_id": tenant_id}` into every filter and insert.
- `manceps_core/indexes.py`: one spec list per collection; `ensure_firm_indexes(db)` and `ensure_platform_indexes(db)`.
  Include the plugin's existing indexes exactly (names matter: create with `name=` equal to pymongo's default name so
  re-creation by the plugin does not conflict).
- Counters: `next_value(db, name)` uses `find_one_and_update($inc, upsert, return_document=AFTER)`.
- Events: `events.emit(db, type, ref, data)` allocates `seq` from counter `events` and inserts `{seq, type, ref, data, at}`.
  TTL index on `at` 30 days; unique index on `seq`.
- Audit: `audit.write(db, who, what, ref, request_id, session_id, before, after)`; hashes are SHA-256 of canonical JSON.
- Idempotency (platform collection `idempotency_keys`, TTL 24 h): FastAPI dependency; same key + same body hash replays the
  stored response with header `Idempotency-Replayed: true`; same key + different body is 409 `idempotency_conflict`.

### 6.5 Auth design (WP1.2)

- Access JWT: EdDSA, header `kid`, claims `iss="manceps"`, `aud="firm"` (or `"portal"` for scoped), `sub` user id, `tid`,
  `role`, `sid` session id, `epoch` = `users.token_epoch`, `exp`. Verification checks `aud`, `exp`, `kid`, and that the
  session is not revoked and `epoch` equals the user's current epoch (one indexed read per request, cached 5 s per process
  is NOT allowed: logout-all must bite on the next request).
- Refresh: random 32 bytes urlsafe; store SHA-256 in `platform.sessions` with `family_id`. On use: mark old token `rotated_to`
  new id, issue new. If a token already rotated is presented, revoke the family and return 401 `refresh_reuse`.
  Browser clients (no `X-Client: native`) get the refresh in cookie `mc_refresh` (`HttpOnly; Secure; SameSite=Lax; Path=/v1/auth`);
  native clients get it in the body.
- OTP login: port `signup-api` `Verifier` protocol and `TwilioVerifier`, rate limits (3 sends/phone/hour, 10 sends/IP/hour, 10
  checks/phone/hour; reuse the constants). `POST /v1/auth/otp/verify` for an unknown phone requires `firm_name` and
  `accept_terms: true`, creates the user, inserts the signup queue row (same shape as `signup-api/store.enqueue`, plus `user_id`),
  and returns tokens with `role="owner"` and `tid=null` until the firm is active (state `provisioning`; firm routes return
  409 `firm_provisioning`). Switch to the firm token by calling `POST /v1/auth/switch-firm` after `GET /v1/firm/provisioning`
  says `ready`.
- Firm activation: worker handler `firm_activate` (run by a minimal loop in `manceps_worker/runner.py` that polls
  `platform.signups` for `status=ready` without a `firms` row) inserts `platform.firms {_id: tenant_id, name, slug, status: "active",
  plan: "trial", timezone: "America/Chicago", owner_user_id}` and `memberships {role: owner}`, then `ensure_firm_indexes`.
  Idempotent.
- Magic link: only when `EMAIL_LOGIN_ENABLED=1` and SMTP is set; otherwise 503. Token 32 bytes, stored hashed, 15 min, single
  use; `start` always returns 202 and sends only if the email belongs to a user.
- Roles: dependency `require_role("dispatcher")` etc. Viewer < dispatcher < owner. Suspended or provisioning firms are rejected.
- Scoped links: `POST /v1/carriers/{id}/links` creates a token `mcl_<urlsafe32>`, stores SHA-256 in `platform.scoped_links`;
  `POST /v1/auth/scoped/exchange` returns a 60-minute JWT with `aud="portal"`, `role="carrier"` and `sub=carrier id`. In this
  phase the portal audience only works on `GET /v1/portal/me` (stub-free: it returns the carrier name and firm name);
  all other portal routes arrive in Phase 3. A test proves `aud="portal"` tokens get 401 on every `aud="firm"` route.
- Invitations: token hashed; accept requires a signed-in user; email or phone must match when present.

### 6.6 Core data rules (WP1.3)

Implement the repositories in `manceps_core/repo/` with validation ported from the plugin (same constants; add
`test_constants_match_plugin` that imports `hermes-freight/carriers.py` by path and asserts equal `EQUIPMENT_TYPES`,
`MAX_FEE_PCT`, `CONSENT_CHANNELS`, tag regex). Collections and indexes: see section 6.9.

- Carrier PATCH of `SENSITIVE_CARRIER_FIELDS = {dispatch_fee_pct, rate_floor_per_mile, consent, agreement_signed}`: dispatcher gets
  409 `approval_required` with `details.approval_kind="carrier_terms_change"`; owner may write directly (audited). Consent
  must go through `POST /carriers/{id}/consent` (writes `consent_events` ledger row first, then the carrier cache field, both in one
  repo function; the ledger is the truth; a repair function rebuilds the cache from the ledger and is tested).
- Soft delete via `deleted_at`; list endpoints hide deleted rows; unique phone index must still allow re-adding after delete:
  on soft delete set `phone_deleted` and unset `phone` (document the choice), or use a partial unique index on
  `{deleted_at: null}`; mongomock supports neither well, so choose the `phone_deleted` approach.
- Brokers: `POST /v1/brokers/{mc}/check` runs the same checks as `hermes-freight/broker_check.py`. Move the pure logic into
  `manceps_core/brokers/check.py` by copying and adapting (HTTP behind an injectable transport); the plugin keeps its own copy
  until Phase 2 vendoring. Failures return verdict `review` or `do_not_book` with `unknown` items, never `pass`.
- Reference search reads `freight_reference.brokers` (read-only).

### 6.7 Imports (WP1.4)

Pipeline: upload (stream to temp file with byte limit, sniff type by extension and magic: CSV = text, XLSX = zip with
`xl/workbook.xml`, VCF = `BEGIN:VCARD`) -> parse rows (cap `IMPORT_MAX_ROWS`) -> detect header, suggest mapping by normalized
header names and a synonym table per entity (for example "Phone", "Cell", "Mobile", "Tel" -> `phone`; "MC", "MC#", "Docket" ->
`mc_number`) -> `PUT mapping` -> validate each row with the same repo validators -> classify action (`create`, `update` when the
natural key matches: carriers by phone, drivers by phone, brokers by MC, contacts by first email or phone, loads by `ref` or
`(broker_mc, broker_ref)`; `skip` invalid) -> preview -> `commit` job.

- Natural keys are normalized before comparing (phone to E.164, MC to digits, email lowercased).
- Duplicate strategy `skip | update | merge` (merge = fill empty fields only; never overwrite non-empty values).
- Dedupe inside the file: later duplicate rows are `skip` with reason `duplicate_in_file`.
- Idempotency: `idempotency_hash = sha256(entity + file bytes)`; committing or uploading the same hash returns the existing
  import (HTTP 200 with `Idempotency-Replayed: true` and `stats` of the first run).
- Undo: each updated row stores `before`; created rows are recorded; undo deletes created rows (only if not modified since:
  compare `updated_at`, otherwise leave and report `skipped_modified`) and restores `before`; allowed until `undo_until`.
- XLSX: read-only mode via openpyxl, first sheet, header row detection (first row with >= 2 non-empty cells), Excel serial dates
  (convert with the workbook epoch), numeric phones (floats like `2145550199.0`) to digits, merged header cells forward-filled.
- Export: CSV and XLSX of any entity with filters; run as a job; store the file in a local-dir `ExportStore` interface
  (R2 implementation arrives in Phase 3; the interface and a filesystem implementation ship now; production uses it only
  after Phase 3, so `ENV=production` without a configured store returns 503).
- Security: formula injection in exports (prefix cells that start with `= + - @` with a single quote); filename sanitization.
- Fixtures under `backend/tests/fixtures/` (small synthetic files, no real data): carriers.csv, carriers_messy.csv,
  contacts.vcf (3 phones per card), google_contacts.csv, loads.xlsx (merged headers, serial dates, float phones).

### 6.8 Loads, approvals, events (WP1.5)

Load statuses and transitions (code table in `manceps_core/loads/machine.py`, 409 `illegal_transition` otherwise):

```
offered -> evaluating, declined, cancelled
evaluating -> countered, approved*, declined, cancelled
countered -> evaluating, approved*, declined, cancelled
approved* -> booked*, cancelled
booked* -> ratecon_received, cancelled
ratecon_received -> dispatched, cancelled
dispatched -> at_pickup, tonu, cancelled
at_pickup -> in_transit, tonu
in_transit -> at_delivery
at_delivery -> delivered
delivered -> pod_received
pod_received -> invoiced
invoiced -> paid
(* = only through an approval action; direct transition request is 409 approval_required)
```

- `booked` and everything after require `carrier_id` that exists in this firm's `carriers` and is `active` or `onboarding`.
- `ref` is `L-<year>-<counter 5 digits>` from the `loads_<year>` counter.
- Every transition writes `load_events` and an `events` row `load.status_changed`.
- `POST /v1/loads/{id}/evaluate`: port the economics from `hermes-freight/loads.py` (miles via Google Routes/ORS when keys exist,
  EIA diesel, fee, carrier net, floor verdict accept/counter/pass). Missing keys: the corresponding input is `unknown` and the
  verdict cannot be `accept`.

Approvals (`manceps_core/approvals/`):
- Doc fields in section 6.9. `payload_hash = sha256(canonical_json({kind, subject_ref, payload}))`.
- `registry.py`: `KINDS = {accept_rate, approve_ratecon, carrier_terms_change, cancel_load}`; each kind has: pydantic payload model,
  `required_role` (owner for `carrier_terms_change`), `risk`, and an `apply(db, approval) -> dict` function.
- Decision endpoint: validates role, hash equality (else 409 `payload_changed`), status `pending` (else 409 `already_decided`),
  expiry (`expires_at`, default 48 h; expired -> 409 `approval_expired`), sets `approved|denied`, emits `approval.decided`, and for
  approve calls `apply` which is idempotent via `applied_at` set with a conditional update (`{_id, applied_at: None}`); on failure sets
  `apply_failed` with the error and emits `approval.apply_failed`; a retry route is not needed (decision retry re-runs apply).
- `accept_rate` apply: sets `rate_cents`, moves the load to `approved` then `booked` if `carrier_id` is valid (else `apply_failed`).
- `carrier_terms_change` apply: writes the listed sensitive fields through the repo with `created_by={kind:"approval"}`.

Events SSE:
- `GET /v1/events/stream`: auth via bearer header or `?access_token=` query param ONLY for this route (EventSource cannot set
  headers; document it; the token is a normal access token; log redaction must strip the query param).
- Implementation: per-process `EventHub` holds one asyncio poller per active tenant (poll `events` where `seq > last_seq`
  every `EVENTS_POLL_SECONDS=1` while subscribers exist, stop 30 s after the last subscriber leaves). Each connection has a
  bounded queue (100); overflow closes the stream with `event: reset` so the client reconnects with `Last-Event-ID`.
  Send `: keepalive` every 15 s. Max `SSE_MAX_CONNECTIONS_PER_USER=5`.
- Tests use an injectable clock and a manual `hub.tick()` to stay deterministic.

### 6.9 Collections for this phase (platform and firm)

Platform: `signups` (existing shape, add `user_id`), `signup_attempts` (existing), `users`, `memberships`, `invitations`,
`sessions`, `magic_links`, `scoped_links`, `firms`, `idempotency_keys`, `rate_limits` (same shape as `signup_attempts`, TTL 24 h).
Firm: `carriers`, `drivers`, `trucks`, `brokers`, `broker_checks`, `contacts`, `facilities`, `notes`, `consent_events`, `loads`,
`load_events`, `approvals`, `imports`, `import_rows`, `exports`, `events`, `counters`, `audit`.

Key fields (see the plugin for existing ones):
- `users`: `phone` (unique sparse), `email` (unique sparse, lowercased), `name`, `status`, `token_epoch` (int), `created_at`, `last_login_at`.
- `memberships`: `user_id`, `tenant_id`, `role`, `status`; unique `(user_id, tenant_id)`.
- `sessions`: `user_id`, `tenant_id`, `family_id`, `token_hash` (unique), `rotated_to`, `expires_at`, `revoked_at`, `ua`, `ip`.
- `carriers` additions: `status` (onboarding|active|paused|offboarded, default onboarding), `email`, `tags[]`, `deleted_at`,
  `created_at`, `updated_at`, `created_by`. `drivers`: `carrier_id`, `name`, `phone` (unique sparse), `email`, `status`,
  `consent`. `trucks`: `carrier_id`, `unit`, `equipment`, `vin` (unique sparse), `plate`, `plate_state`.
- `contacts`: `kind`, `name`, `company`, `phones[]`, `emails[]`, `tags[]`, `consent`, `source`; text index on name and company.
- `consent_events`: `subject {type, id, phone}`, `channel`, `action`, `method`, `evidence_ref`, `at`, `by`; append-only.
- `loads`: see the load statuses above; fields `ref, status, carrier_id, driver_id, truck_id, broker_mc, source, stops[], equipment,
  weight_lbs, commodity, loaded_miles, deadhead_miles, rate_cents, accessorials[], evaluation{}, cancelled_reason`.
- `approvals`: `kind, status, subject_ref{type,id}, payload, payload_hash, summary, risk, requested_by{kind,id}, decided_by,
  decided_at, note, applied_at, apply_result, expires_at, created_at`.
- `imports`: `entity, source_filename, status, mapping, stats, idempotency_hash (unique), undo_until, created_by`.

### 6.10 Routes to ship in Phase 1

Implement exactly the following operations (path, method; role in brackets; O owner, D dispatcher+, V viewer+, P public):
- Meta: `GET /healthz` P, `GET /readyz` P, `GET /v1/openapi.json` P, `GET /v1/me` U, `PATCH /v1/me` U.
- Auth: `POST /v1/auth/otp/start|verify`, `/magic-link/start|verify`, `/refresh`, `/logout`, `/logout-all`, `/switch-firm`,
  `/scoped/exchange`; `GET /v1/signup/status/{token}`; `GET|DELETE /v1/sessions[/{id}]`.
- Firm and team: `GET /v1/firm` V, `PATCH /v1/firm` O, `GET /v1/firm/provisioning` U, `GET /v1/members` V,
  `POST|GET /v1/members/invitations` O, `DELETE /v1/members/invitations/{id}` O, `POST /v1/invitations/accept` U,
  `PATCH|DELETE /v1/members/{user_id}` O, `GET /v1/audit` O.
- Data: carriers, drivers, trucks, brokers (+ notes, check, checks), `GET /v1/reference/brokers`, contacts, facilities, notes, tags,
  `POST|DELETE /v1/carriers/{id}/consent[/{channel}]`, `POST|DELETE /v1/carriers/{id}/links[/{link_id}]`.
- Imports and exports: all routes in the plan section "Imports and exports" (templates, create, get, mapping, preview, report,
  commit, undo, list), `POST /v1/exports`, `GET /v1/exports/{id}`.
- Loads: list, create, get, patch, transition, evaluate, stops (add, patch, delete), events, board.
- Approvals: list, get, create, decision, stats.
- Events: `GET /v1/events/stream`, `GET /v1/events?after=`.
- Integrations: `GET /v1/integrations` V (status of twilio_verify, smtp, fmcsa, eia, google_routes, ors: `not_configured|ready`).
- Portal stub: `GET /v1/portal/me` S.

### 6.11 Tests to write first, by work package

- WP1.1: `test_settings_secrets_are_secretstr`, `test_error_envelope_shape`, `test_tenantdb_has_no_string_tenant_api`,
  `test_platform_repo_injects_tenant`, `test_indexes_idempotent`, `test_events_seq_monotonic_under_threads`,
  `test_idempotency_replay_and_conflict`, `test_rate_limit_window`, `test_logs_redact_secrets_and_access_token_query`,
  `test_openapi_export_check_fails_when_stale`.
- WP1.2: `test_otp_new_user_creates_signup_and_tokens`, `test_otp_wrong_code_400`, `test_twilio_unset_503`,
  `test_refresh_rotation`, `test_refresh_reuse_revokes_family`, `test_logout_all_bites_next_request`,
  `test_token_expiry_clock`, `test_wrong_aud_kid_401`, `test_roles_matrix`, `test_firm_activate_idempotent`,
  `test_invitation_flow`, `test_last_owner_cannot_be_removed`, `test_scoped_exchange_and_aud_isolation`, `test_magic_link_disabled_503`.
- WP1.3: `test_constants_match_plugin`, `test_carrier_crud_and_unique_phone`, `test_sensitive_field_requires_approval_for_dispatcher`,
  `test_owner_direct_edit_audited`, `test_consent_ledger_and_cache`, `test_consent_requires_method`, `test_soft_delete_phone_reuse`,
  `test_broker_check_failure_is_unknown_not_pass`, `test_reference_search`, `test_contacts_tags_notes`, `test_wrong_tenant_matrix_data_routes`.
- WP1.4: tests 9 to 12 from the acceptance list below plus `test_formula_injection_escaped`, `test_merge_never_overwrites`,
  `test_duplicate_in_file_skipped`, `test_import_progress_events`.
- WP1.5: tests 13 to 17 below plus `test_every_route_has_tenant_matrix_entry` (fails if a route is added without a rule),
  `test_sse_two_firms_isolated`, `test_sse_reset_on_overflow`, `test_e2e_main_flow`.

### 6.12 Acceptance criteria (each must be proved by a named test)

1. OTP verify (fake verifier) for a new phone creates user, signup row `pending`, returns tokens; the activation handler turns a `ready` signup into an active firm with an owner membership.
2. A firm A token gets 404 for every `/v1` resource id from firm B (generated from the OpenAPI schema).
3. Refresh reuse revokes the family; `logout-all` invalidates access tokens on the next request.
4. Access tokens expire at 15 minutes; wrong `aud` or `kid` is 401; portal tokens fail on firm routes.
5. Viewer gets 403 on every write route; dispatcher gets 403 on owner-only routes.
6. Carrier phone is unique per firm and normalized; duplicate create is 409.
7. Dispatcher PATCH of `dispatch_fee_pct` is 409 `approval_required`; owner can change it with an audit record holding before and after hashes.
8. Consent grant without `method` is 422; each grant or revoke appends a ledger row; cache equals ledger.
9. 1,000-row carrier CSV (5 invalid, 20 existing): preview counts correct; commit creates exactly the valid new rows; same file again creates nothing.
10. Undo within 24 h restores updated rows and removes created rows; at 25 h is 409.
11. XLSX (merged headers, serial dates, float phones), vCard (3 phones), Google Contacts CSV import correctly.
12. Over 10 MB or over 20,000 rows is rejected before full parsing.
13. Load transitions follow the table; illegal is 409; `booked` without a valid carrier is 409; direct `approved|booked` is 409 `approval_required`.
14. `accept_rate` approval with correct hash books the load exactly once even if the decision is retried; wrong hash is 409.
15. SSE delivers `approval.created` within 2 s, resumes with `Last-Event-ID`, never leaks across firms.
16. `openapi.json` equals the generated schema; all operations have `operationId`; 4xx responses use the envelope.
17. The 11th OTP check for a phone in an hour is 429; Twilio unset is 503.
18. Pyright strict clean; plugin tests still pass; vendor check passes (create `scripts/vendor_core.py` now: it copies
    `manceps_core` to `hermes-freight/_vendor/manceps_core/`, `--check` compares; do not wire the plugin to it yet).

### 6.13 Do not do in this phase

No agent bridge, no document storage, no messaging sends, no billing, no webhooks beyond none. Do not delete `signup-api/`.
Do not change `hermes-freight` code except adding `_vendor/` via the script (and nothing imports it yet).

### 6.14 Security self-check items to include in the report

Authz per route (list generated from OpenAPI), tenant scoping per query (grep for raw `client[` use outside `tenancy.py`),
size limits, rate limits, no secrets in logs/responses (tests named above), SSE token-in-query redaction, CORS origin list.

## 7. Finish

End your run with the report format in section 5: status first, then exact gate outputs, files changed, decisions, what was not verified, and founder actions.
