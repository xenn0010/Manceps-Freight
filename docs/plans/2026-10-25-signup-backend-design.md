# Signup backend design (2026-10-25)

## Decisions

- **Open to anyone**, proven by an **SMS code** (Twilio Verify). One firm per verified phone.
- **Public API + queue.** The API runs on Vercel and only verifies phones and queues requests.
  A worker on the gateway host provisions firms. The gateway host accepts no inbound connections.

## Flow

1. `POST /signup/start {phone, firm_name, accept_terms: true}` sends an SMS code.
2. `POST /signup/verify {..., code}` checks the code, then inserts `platform.signups`
   `{_id: token, phone, firm_name, status: "pending", attempts: 0, terms_version, client_ip}`.
   Returns `202 {token}`.
3. `hermes-freight/deploy/signup_worker.py` claims the oldest pending signup atomically
   (`find_one_and_update`), reserves a unique tenant id from the firm name, runs
   `provision_tenant.provision()`, and sets `ready` or `pending`/`failed` after `MAX_ATTEMPTS`.
4. The page polls `GET /signup/status/{token}`: `pending`, `provisioning`, `ready` (with
   `tenant_id`), or `failed` (generic message; internal errors never leave the database).

## Fail-closed rules

- No Twilio credentials: `/start` and `/verify` return 503. Verification is never skipped.
- Twilio outage: 502. Only Twilio status `approved` verifies; an expired check (404) is a wrong code.
- Unique index on `phone`; a failed signup may be retried, an active one is a 409.
- Rate limits per rolling hour: 3 code sends per phone, 10 per IP, 10 code checks per phone.
- `X-Forwarded-For` is trusted only when `SIGNUP_TRUST_PROXY=1` (set on Vercel).
- A claim left by a crashed worker is retried after 15 minutes; provisioning is idempotent and
  a retried signup keeps its reserved tenant id.

## Configuration

- API (Vercel): `SIGNUP_MONGODB_URI` (should be a database user limited to `platform`),
  `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_VERIFY_SERVICE_SID`, `SIGNUP_TRUST_PROXY=1`.
- Worker (gateway host): operator `MONGODB_URI` in `~/.hermes/.env`.

## Not yet built

- The page itself (frontend).
- Running the worker as a service on the VM.
- Telling the dispatcher how to reach their agent once `ready` (depends on the WhatsApp/SMS number).
