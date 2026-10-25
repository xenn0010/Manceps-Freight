# Execution prompt: Phase 3 (documents-portal)

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

## 6. Phase 3 brief: documents, scanning, parsing, expiry, carrier and driver portal

**Prerequisites.** Phases 1 and 2 merged. Collections `documents`, `claims`, `reminders` are new (plan part 2 section 3.3).

**Goal.** Documents are uploaded through the API, type-checked, virus-scanned, stored in Cloudflare R2, parsed by Claude when
asked, tracked for expiry with reminders; carriers and drivers use scoped links to upload documents, set consent, and update
load status.

### 6.1 Verified vendor facts (https://developers.cloudflare.com/r2/api/s3/presigned-urls/)

- Presigned GET, HEAD, PUT, DELETE work; expiry 1 s to 7 days; POST form uploads are NOT supported; presigned URLs do not work with
  custom domains; SigV4 against `<ACCOUNT_ID>.r2.cloudflarestorage.com`; Content-Type can be pinned at signing time.
- UNVERIFIED: object versioning/lock, pricing. UNVERIFIED: ClamAV memory needs and the best Python client. Verify, then pin.

### 6.2 Design

- Storage interface `ObjectStore` in `manceps_api/storage/`: `put(key, data_stream, content_type, sha256)`, `presign_get(key, ttl)`, `delete(key)`,
  `exists(key)`. Implementations: `R2Store` (boto3 S3 client with `endpoint_url`, `region_name="auto"`, SigV4), `FakeStore` (in memory).
  Both run the same contract tests. Env: `R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET`. Unset -> 503
  `integration_not_configured` on upload and download routes.
- Keys: `t/<tenant_id>/<doc_id>/<sha256>`; never user filenames in keys. Original filename sanitized (strip path, control chars, limit 120).
- Upload route streams to a temp file with `DOCUMENT_MAX_BYTES=15728640` limit (413), computes sha256, checks magic bytes against the
  allowed set (PDF `%PDF-`, PNG, JPEG, XLSX zip with `xl/`, CSV text), rejects mismatch between declared type and sniffed type (415),
  inserts `documents {status:"scanning"}`, enqueues job `document_scan`.
- `document_scan`: ClamAV over the INSTREAM protocol (socket client; host/port from `CLAMD_HOST`, `CLAMD_PORT`). Result OK -> put to
  R2, verify `exists`, set `available`, emit `document.available`. Infected -> `quarantined`, emit event, never stored in the main
  prefix. Scanner unreachable -> job retries with backoff and the document stays `scanning` (fail closed).
- Download: `GET /v1/documents/{id}/download-url` returns a 300 s presigned GET only for `available` documents; every issuance is audited.
- Parse: `POST /v1/documents/{id}/parse` (Idempotency-Key) runs a Claude call (model name from setting `PARSE_MODEL`, default the model
  used by `hermes-freight/ratecon.py`; read that file for how it calls the API with structured output and PDF input; reuse its
  schema ideas, injectable HTTP transport for tests). Kinds: `w9` (legal name, EIN last4 only: never store a full EIN),
  `coi` (insurer, policy number, coverage amounts, effective and expiry dates), `ratecon` (reuse the Rate Con fields). The model
  output is data: validated by Pydantic; unknown fields dropped. Setting `expires_at` from a COI parse requires the parse
  confidence flag and is shown to a human in the response; it is stored on the document and mirrored to
  `carriers.insurance_expires_at`.
- Expiry scan (worker, daily): for documents with `expires_at` within 30 and 7 days (`EXPIRY_REMINDER_DAYS = (30, 7)`) create
  `reminders` rows once each (unique on `(ref, due_at)`) and emit `document.expiring`. Sending the reminder to the carrier is
  Phase 4; now the reminder goes to the dispatcher task list (event + `GET /v1/reminders`).
- Claims: `GET|POST /v1/loads/{id}/claims`. Amount math in integer cents: detention = ceil minutes over free time / 60 * hourly rate,
  capped by `MAX_CLAIM_CENTS` setting; test with boundaries.
- Portal (scoped JWT `aud=portal`): routes in plan part 3 section 15 (except agreement). Role `carrier` sees only its own
  `carrier_id` data; role `driver` only loads assigned to its driver id. Responses never include rates other than the
  carrier's own `rate_cents * (1 - fee_pct/100)` net, and never include other carriers, broker contacts' private notes, or the floor
  of anyone. Status updates write `load_events` and may move the load among `dispatched -> at_pickup -> in_transit -> at_delivery ->
  delivered` only; `pod_received` needs a POD document.
- Portal consent route: carrier grants or revokes `sms`, `whatsapp`, `voice` themselves; the ledger records IP, user agent, timestamp
  and the exact consent text version `CONSENT_TEXT_VERSION` (setting; the text itself comes from a lawyer and is loaded from a
  file `backend/manceps_api/consent_text.md` that ships with a clearly marked draft the founder replaces; the API returns the text
  so the frontend shows it).

### 6.3 Tests first

`test_upload_rejects_renamed_exe`, `test_upload_413_over_limit_streaming`, `test_upload_type_allowlist`, `test_eicar_quarantined`
(EICAR string constructed in code, not stored in the repo as a file), `test_scanner_down_stays_scanning`, `test_download_url_ttl_300`,
`test_download_audited`, `test_store_contract_fake_and_r2_stubbed` (botocore Stubber), `test_parse_coi_sets_expiry_and_reminders`,
`test_parse_output_is_validated_data`, `test_no_full_ein_stored`, `test_expiry_reminders_created_once`,
`test_claim_math_boundaries`, `test_claim_cap`, `test_portal_carrier_isolation_matrix`, `test_portal_driver_sees_only_assigned_loads`,
`test_portal_response_has_no_other_rates`, `test_driver_delivered_needs_pod_for_pod_received`, `test_portal_consent_ledger_evidence`,
`test_link_revoked_401_next_request`, `test_wrong_tenant_matrix_new_routes`.

### 6.4 Acceptance criteria

1. Renamed executables, wrong types, and files over 15 MB are rejected before storage.
2. EICAR -> `quarantined`; scanner outage -> `scanning` forever, never `available`.
3. Download URLs expire in 300 s and are audited.
4. A COI parse sets an expiry date; reminders at 30 and 7 days exist once each.
5. Carrier A's link cannot read carrier B's documents or loads; revoked link fails on the next request.
6. Driver delivery updates cannot skip statuses; POD needed for `pod_received`.
7. Claim math is exact in cents with boundaries tested.
8. Fake and R2 stores pass identical contract tests.
9. Full gate set green; `openapi.json` updated; plugin suite green.

### 6.5 Do not do

No outbound reminders to carriers (Phase 4). No invoices. No e-sign (Phase 9).

## 7. Finish

End your run with the report format in section 5: status first, then exact gate outputs, files changed, decisions, what was not verified, and founder actions.
