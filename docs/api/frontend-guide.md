# Manceps API: frontend guide

The contract is `backend/openapi.json` (served live at `GET /v1/openapi.json`). This guide covers what the schema
cannot say: how auth, refresh, errors, pagination, idempotency and imports behave, and how to run the stack locally.

## Run it locally

All commands run with the working directory `backend/`.

### 1. MongoDB

Use the single-node replica set (MongoDB 8.0, set `rs0`) that runs in the Lima VM and is forwarded to the Mac:

```
mongodb://127.0.0.1:27017/?directConnection=true
```

Check it answers before starting anything:

```sh
uv run python -c "from pymongo import MongoClient; print(MongoClient('mongodb://127.0.0.1:27017/?directConnection=true', serverSelectionTimeoutMS=3000).admin.command('ping'))"
```

### 2. Environment

Settings come only from the process environment; no `.env` file is read automatically.

```sh
cp .env.example .env            # git-ignored; holds dev values only
set -a; source .env; set +a
```

`.env.example` sets `ENV=dev`, the local `MONGODB_URI`, `CORS_ORIGINS=http://localhost:3000`,
`PUBLIC_BASE_URL=http://localhost:3000` and a `DEV_OTP_CODE`.

### 3. Signing keys

`scripts/gen_keys.py` prints a fresh Ed25519 JWT key pair and a `SECRETS_KEY` as one JSON object on stdout
(`JWT_ACTIVE_KID`, `JWT_KEYS_JSON`, `SECRETS_KEY`). It writes nothing to disk. Keep the output outside the repo and
export it into the same shell:

```sh
mkdir -p ~/.manceps && chmod 700 ~/.manceps
uv run python scripts/gen_keys.py > ~/.manceps/dev-keys.json && chmod 600 ~/.manceps/dev-keys.json
eval "$(uv run python -c 'import json, shlex, sys; print("\n".join(f"export {k}={shlex.quote(v)}" for k, v in json.load(open(sys.argv[1])).items()))' ~/.manceps/dev-keys.json)"
```

Without the JWT keys every sign-in route answers 503 `auth_not_configured`.

### 4. Phone sign-in without Twilio (`DEV_OTP_CODE`)

- With `ENV=dev` and `DEV_OTP_CODE` set to exactly 6 digits, `POST /v1/auth/otp/start` sends no SMS and
  `POST /v1/auth/otp/verify` accepts only that code, for any phone. The comparison is constant time.
- Settings refuse to load when `DEV_OTP_CODE` is set and `ENV` is anything but `dev` (`test`, `production`, or an
  unknown value), so the API cannot start that way. The code never appears in logs or validation errors.
- If the three `TWILIO_*` values are also set, Twilio wins and the dev code is ignored (a `verify.dev_code_ignored`
  warning is logged). Unset Twilio to use the dev code.
- Every OTP rate limit still applies: 3 sends per phone and 10 per IP per hour; 10 checks per phone and 60 per IP
  per hour.

### 5. Start the API and the worker

Two shells, both with the environment above:

```sh
uv run python -m manceps_api.serve          # http://127.0.0.1:8000 (API_HOST, API_PORT)
uv run python -m manceps_worker.runner      # polls every 5 s; add --once for a single pass
```

`GET /healthz` is liveness; `GET /readyz` checks the database and indexes.

### 6. Firm provisioning needs the hermes-freight signup worker

A new signup is only queued by the API (`platform.signups`, status `pending`). Two workers finish it:

1. `hermes-freight/deploy/signup_worker.py` claims the signup, provisions the Hermes tenant and marks it `ready` with
   a `tenant_id`. It runs inside the Lima VM (`python3 signup_worker.py --shared-credentials`, `--once` to drain the
   queue once) and reads `MONGODB_URI` from its environment or the Hermes `.env`. It must point at the same MongoDB.
   It always uses the database named `platform`, so keep `PLATFORM_DB=platform` when you want firms provisioned.
2. `manceps_worker.runner` (above) then activates the firm: firm record, owner membership, firm database.

Without the signup worker, signup still works but the firm stays `pending` and `/v1/firm/provisioning` never
reaches `ready`.

### 7. Browser specifics at http://localhost:3000

- CORS: `CORS_ORIGINS=http://localhost:3000` allows credentialed requests and preflights for `Authorization`,
  `Content-Type` and `Idempotency-Key`. Exposed response headers: `X-Request-ID`, `Idempotency-Replayed`.
- Call the API with `credentials: "include"` so the refresh cookie is stored and sent.
- The refresh cookie is `Secure`. Chromium and Firefox accept `Secure` cookies on `http://localhost`; Safari may not,
  so test refresh in Chrome or Firefox locally. `localhost:3000` and `localhost:8000` are the same site, so
  `SameSite=Lax` does not block it.

## Auth flow

### Phone OTP (primary)

1. `POST /v1/auth/otp/start` `{"phone": "+12145550199"}` returns 202 `{"sent": true}`. US numbers in common formats
   are normalized to E.164.
2. `POST /v1/auth/otp/verify` `{"phone", "code"}`:
   - Existing user: 200 with tokens (`state` is `active` with a `tenant_id`, or `no_firm`).
   - New phone without signup fields: 422 `signup_details_required` with `details.signup_ticket` (single use,
     `details.expires_in` seconds, bound to the phone). Ask for the firm name and terms, then call verify again with
     `{"phone", "signup_ticket", "firm_name", "accept_terms": true}` (no `code`; the code is already spent).
   - New phone with `firm_name` and `accept_terms: true` sent with the code: signs up directly.
   - A new signup returns 200 with `state: "provisioning"`, `tenant_id: null`, `role: "owner"` and a `signup_token`.
3. While provisioning, poll `GET /v1/firm/provisioning` (authenticated) or `GET /v1/signup/status/{signup_token}`
   (public). On `ready`, call `POST /v1/auth/switch-firm` `{}` to get a firm-scoped access token.

Errors: 400 `invalid_code` or `invalid_ticket`, 409 `already_signed_up`, 429 `rate_limited` with `Retry-After`,
502 `verify_unavailable`, 503 `twilio_not_configured` (no Twilio and no dev code).

### Email magic link (optional)

Only with `EMAIL_LOGIN_ENABLED`, SMTP and `PUBLIC_BASE_URL`; otherwise 503. `POST /v1/auth/magic-link/start`
`{"email"}` mails `{PUBLIC_BASE_URL}/auth/magic-link?token=...`; the page posts the token to
`POST /v1/auth/magic-link/verify`. Links expire after 15 minutes and work once.

### Carriers and drivers

They never get firm accounts. A firm creates a scoped link (`POST /v1/carriers/{id}/links`); the portal exchanges it
at `POST /v1/auth/scoped/exchange` for a portal token usable only on `/v1/portal/*`.

## Tokens, refresh and rotation

- Access token: Ed25519 JWT, `Authorization: Bearer <token>`, 15 minutes (`expires_in` in seconds).
- Refresh token: 30 days. Browsers get it only in the `mc_refresh` cookie (HttpOnly, Secure, SameSite=Lax,
  Path=/v1/auth); the body field is `null`. Native apps send `X-Client: native` and receive it in the body.
- `POST /v1/auth/refresh` (cookie, or `{"refresh_token"}` for native) returns new tokens and a new refresh token.
  Every refresh token works once.
- Reusing a spent refresh token is 401 `refresh_reuse` and revokes the whole session family: sign in again. Run one
  refresh at a time per session (share a single in-flight promise across tabs or requests).
- 401 `invalid_refresh`: unknown, expired or revoked token, or `logout-all` ran. Send the user to sign in.
- `POST /v1/auth/logout` ends this session; `POST /v1/auth/logout-all` ends every session and invalidates all access
  tokens on their next use. `GET /v1/sessions` and `DELETE /v1/sessions/{id}` manage devices.
- Refresh is limited to 300 per IP per hour.

## Real-time (SSE)

Not implemented yet. No server-sent events route exists in the current API; poll the relevant `GET` routes.

## Errors

Every non-2xx body is `{"error": {"code", "message", "details"}}`.

- Branch on `code`, never on `message`. `message` is safe to show.
- 422 `validation_error` puts the field problems in `details.errors` (a list of `loc`, `msg`, `type`).
- 429 `rate_limited` carries `Retry-After` (seconds).
- 503 `*_not_configured` means a feature is switched off on this deployment, not a transient failure.
- Quote `X-Request-ID` (on every response) in bug reports.

## Pagination

List routes take `limit` (1 to 200, default 50) and `cursor`, and return `{"items": [...], "next_cursor": ...}`.
Pass `next_cursor` back as `cursor` until it is `null`. Cursors are opaque; do not build or parse them.

## Idempotency

Create routes accept an optional `Idempotency-Key` header (8 to 128 chars of `[A-Za-z0-9_.:-]`, kept 24 hours).

- Retrying with the same key and body replays the stored response with `Idempotency-Replayed: true`.
- Same key, different body: 409 `idempotency_conflict`. Same key still running: 409 `idempotency_in_progress`.
- Generate one key per user action (for example a UUID when the form opens) and reuse it for retries of that action.

## Imports

1. Optional: `GET /v1/imports/templates/{entity}` returns a CSV header template (`carriers`, `drivers`, `brokers`,
   `contacts`).
2. `POST /v1/imports` multipart with `entity` and `file` (`.csv` or `.xlsx`, or `.vcf` for contacts; limited by
   `IMPORT_MAX_BYTES` and `IMPORT_MAX_ROWS`). 201 with the import; uploading the same file again returns the first
   import with 200 and `Idempotency-Replayed: true`. Errors: 413 `file_too_large`, 415 `unsupported_file_type`, 422.
3. If `status` is `uploaded`, required columns still need a mapping: `PUT /v1/imports/{id}/mapping`
   `{"mapping": {"Column header": "field" | null}}`. The import then becomes `mapped`.
4. `GET /v1/imports/{id}/preview` shows rows and their planned actions; `GET /v1/imports/{id}/report` (`format=json`
   or `csv`) lists every row's errors.
5. `POST /v1/imports/{id}/commit` `{"duplicate_strategy": "skip" | "update" | "merge"}` returns 202 and the worker
   writes the rows. Poll `GET /v1/imports/{id}` until `committed` or `failed`. Fee, floor and agreement values are
   written only when the owner commits; for a dispatcher those rows get `approval_required`.
6. `POST /v1/imports/{id}/undo` within `IMPORT_UNDO_HOURS` (default 24) restores updated records and removes created
   ones nothing has changed since.

Statuses: `uploaded`, `validating`, `mapped`, `committing`, `committed`, `failed`, `undoing`, `undone`.
