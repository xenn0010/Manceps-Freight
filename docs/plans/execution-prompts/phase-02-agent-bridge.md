# Execution prompt: Phase 2 (agent-bridge)

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

## 6. Phase 2 brief: agent bridge, chat, approvals from the agent, scheduler

**Prerequisite.** Phase 1 is merged and green (`backend/` exists with auth, firms, loads, approvals, events).

**Goal.** The dispatcher chats with Manceps through the API; the agent raises approvals that appear in the inbox; decisions
flow back; scheduled jobs run. All traffic from the Lima VM is outbound. The VM gets no inbound port.

### 6.1 Facts about Hermes (from `hermes-agent/website/docs/user-guide/features/api-server.md`, pinned commit 1c0cd66774)

- Enable per profile in `~/.hermes/profiles/<p>/.env`: `API_SERVER_ENABLED=true`, `API_SERVER_KEY=<random>`. Listens on `127.0.0.1:8642`.
- With the multiplexing gateway, profile routes are `/p/<profile>/v1/...` and need that profile's own key (`Authorization: Bearer`).
  A default-profile key on a named-profile prefix is rejected. Run ids are profile-scoped (other profile's id is 404).
- `POST /v1/runs` with JSON `{input, session_id?, instructions?}` returns `{run_id, status}`; header `Idempotency-Key` (1-255 chars)
  makes retries safe for 24 h (same body returns the same run id with `Idempotency-Replayed: true`; different body is 409
  `idempotency_key_conflict`). `GET /v1/runs/{id}` polls (`status` completed|failed|cancelled|interrupted; `output`).
  `GET /v1/runs/{id}/events` is SSE: `message.delta`, `message.interim`, `tool.started`, `tool.completed`, `run.completed`; keepalive
  comment lines every 10 s. `POST /v1/runs/{id}/stop`. 503 `runtime_draining` / `storage_unavailable` with `Retry-After`.
- API sessions are their own: `session_id` cannot bind a session owned by another surface (409 `permission_denied`).
- UNVERIFIED on the VM: multiplexed routing with two profiles, exact event payloads. The first task is a spike (below).

### 6.2 Design to implement

Command queue (`platform.agent_commands`, plan part 2): the API and worker insert; `agent-bridge` claims with
`find_one_and_update({status:"queued"} or {status:"claimed", claimed_at < now-CLAIM_TTL}, {$set:{status:"claimed", claimed_by, claimed_at}, $inc:{attempts:1}})`
ordered by `created_at`, max `MAX_COMMAND_ATTEMPTS=3`. Commands expire after `COMMAND_TTL=24h` (worker handler marks `expired`).
Kinds now: `chat`, `scheduled`, `approval_result`. Payload always includes `conversation_id`, `profile` (derived from tenant:
profile name = tenant id), and the text `input`.

Bridge (`agent-bridge/manceps_bridge/`): Python 3.11 asyncio, httpx, pymongo. Components: `claim.py` (atomic claim loop; poll 1 s
when busy, back off to 5 s idle), `profiles.py` (reads `~/.hermes/profiles/<p>/.env` to get `API_SERVER_KEY`; never logs it),
`hermes_client.py` (create run with `Idempotency-Key=<command id>`, stream events, stop), `runner.py` (per command: create run,
forward events to `platform.agent_stream` with `seq`, on `run.completed` write the assistant `messages` doc to the firm DB and
emit `message.created`; on failure set command `failed` with a safe error code), `heartbeat.py` (every 15 s upsert
`bridge_heartbeat` with profiles and queue depth), `settings.py`. Concurrency: `BRIDGE_MAX_CONCURRENT_RUNS=3`. One run per
conversation at a time (second command for the same conversation waits).

The bridge uses `PLATFORM_MONGODB_URI` (platform DB read/write on `agent_commands`, `agent_stream`, `bridge_heartbeat`, and
read/write on firm DBs for `messages`). Systemd user unit `infra/vm/manceps-agent-bridge.service` (like
`infra/vm/hermes-signup-worker.service`: restart always). The bridge opens no listening socket.

Agent-facing plugin tools (new modules in `hermes-freight/`, schemas in `schemas.py`, registered in `__init__.py`, listed in
`plugin.yaml`). They use the vendored core (`hermes-freight/_vendor/manceps_core`, produced by `backend/scripts/vendor_core.py`;
switch the plugin's imports for carriers/brokers storage to core repos only where the tests stay green; otherwise keep
existing modules and use core only for the new tools):
- `approval_request(kind, subject, payload, summary)`: creates a pending approval via core. Hermes tools do not receive the command id, so idempotency is on `payload_hash`: if a pending approval with the same hash already exists for the same subject, return it instead of creating another. Returns `{approval_id, status:"pending"}` and tells the model to wait for the human decision.
- `approval_status(approval_id)`; `fact_remember(entity, text, kind)`, `fact_recall(entity)`;
  `load_propose(fields)` (creates a load in `offered` or `evaluating` only), `load_get(ref)`.
- No tool may set load status beyond `evaluating`, change money fields, or send messages (messaging arrives in Phase 4).
  `tests/test_tool_inventory.py` asserts the registered tool names and that none maps to a forbidden operation.
- `policy.py`: if `tenant.secret("FREIGHT_APPROVAL_MODE") == "platform"`, `check_carrier_upsert` returns a **block** with the message
  "Changes to fee, floor, consent or agreement need dispatcher approval: call approval_request with kind carrier_terms_change."
  Keep the old `approve` behaviour when the variable is unset. Keep fail-closed crash handling.
- `profile/SOUL.md`: add the approval protocol (always include numbers; never claim approval before status `approved`; after
  `approved` the platform already applied the change) and memory protocol (`fact_remember` for durable facts).
- `deploy/provision_tenant.py`: write `API_SERVER_ENABLED`, `API_SERVER_KEY` (random 32 bytes), `FREIGHT_APPROVAL_MODE=platform`
  into the profile `.env`; idempotent re-run keeps the existing key. `deploy/managed-config.yaml`: add `cronjob` to
  `disabled_toolsets`. Update `tests/test_provision.py`.

Approval result flow (worker): when an approval is decided, handler `approval_apply` runs the registered action (Phase 1 code),
then inserts `agent_commands {kind:"approval_result", payload:{approval_id, status, apply_result}, idempotency_key:"approval:<id>"}`
so the agent can tell the dispatcher what happened. If the agent is offline the command waits (24 h TTL).

Job system and scheduler (`backend/manceps_worker/`): `platform.jobs` and `platform.schedules` as in plan part 2. Claim with
`find_one_and_update` on `{status:"queued", run_at<=now}` setting `locked_until=now+JOB_LEASE_SECONDS(60)`; expired leases are
reclaimable; retries use `min(2**attempts * 5 s, 15 min)` backoff; after `max_attempts` status `dead`. Handlers register in a
dict by kind. Scheduler tick every 15 s: `find_one_and_update({enabled:true, next_run_at<=now}, {$set:{next_run_at: next occurrence after now, last_run_at: now}})`
so a missed tick yields one run. Cron parsing: use `croniter` with the firm timezone (verify the library is maintained; pin it).
Default schedules created at firm activation: `morning_brief` (07:00 local), `doc_expiry` (daily 06:00), `payment_chase`
(weekdays 10:00, disabled until Phase 8), `check_calls` (disabled until Phase 4), `email_triage` (disabled until Phase 4).
Quiet hours (`agent_settings.autonomy.quiet_hours`) suppress `scheduled` agent commands, not deterministic jobs.
Morning brief handler: builds a deterministic summary (open loads by status, approvals pending, docs expiring in 30 days);
tries to enqueue a `scheduled` agent command asking Manceps to write the brief; if the agent is offline (heartbeat older than
`AGENT_OFFLINE_SECONDS=90`) stores the deterministic summary with `fallback=true`.

New firm collections: `conversations`, `messages`, `memory_facts`, `agent_settings`, `briefs`. New routes: part 3 section 10
(agent status/settings, conversations, messages, stream, commands cancel, memory facts, schedules, briefs).
Conversation stream (SSE): tails `agent_stream` for the latest command of the conversation, supports `Last-Event-ID` as `seq`.

### 6.3 Tests to write first

Backend: `test_command_claim_exactly_once_under_race`, `test_claim_retry_after_ttl`, `test_command_expires`,
`test_chat_post_503_when_agent_offline`, `test_chat_creates_message_and_command`, `test_conversation_stream_resume`,
`test_agent_status_offline_after_90s`, `test_approval_result_command_created_after_apply`, `test_job_lease_reclaim`,
`test_job_backoff_and_dead_letter`, `test_scheduler_runs_once_with_three_workers`, `test_missed_tick_catches_up_once`,
`test_quiet_hours_suppress_agent_jobs_only`, `test_brief_fallback_when_agent_offline`, `test_memory_fact_crud`,
`test_wrong_tenant_matrix_new_routes`.
Bridge (`agent-bridge/tests/`, fake Hermes server using aiohttp or httpx MockTransport): `test_run_created_with_idempotency_key`,
`test_events_forwarded_in_order`, `test_crash_midrun_retry_does_not_double_run`, `test_unknown_profile_fails_command`,
`test_key_never_logged`, `test_heartbeat_written`, `test_one_run_per_conversation`.
Plugin: `test_tool_inventory_no_forbidden_tools`, `test_approval_request_idempotent_on_hash`, `test_policy_platform_mode_blocks_sensitive_carrier_edit`,
`test_policy_crash_still_blocks`, `test_provision_writes_api_server_env`, plus the existing suite.

### 6.4 Spike (do first, report result before building the rest)

On the VM through `limactl shell hermes` (ask the founder before touching it; if not approved, build against fakes and report
the spike as NOT RUN): enable the API server for the profile `pilot-firm`, call `GET /health`, `POST /p/pilot-firm/v1/runs`
with `input:"say ok"`, read `/events`. If multiplex routing needs a second profile for a meaningful test, create `spike-b`, test
cross-profile 404, then delete it. Record observed event names; adapt `hermes_client.py` to what you observe.

### 6.5 Acceptance criteria

1. Bridge claims a queued chat command exactly once with 5 concurrent claimers.
2. Chat produces ordered `agent_stream` rows and a final assistant message; killing the bridge mid-run and restarting retries after the claim TTL with the same Idempotency-Key and does not run the agent twice.
3. `GET /v1/agent/status` says offline after 90 s without heartbeat; chat then returns 503 `agent_offline`.
4. `approval_request` creates one pending approval with a payload hash; repeating the same call returns the same approval.
5. Approving an `accept_rate` approval books the load before the agent is told (command created after apply).
6. No agent tool can set `approved`, `booked`, or later load statuses, change `rate_cents`, or send a message (inventory test).
7. In platform mode the policy blocks sensitive carrier edits and names `approval_request`.
8. A schedule due at T runs once with three workers; a missed tick catches up once.
9. Quiet hours suppress agent-initiated jobs but not deterministic ones; the morning brief falls back deterministically when the agent is offline.
10. Fact edited through the API is what `fact_recall` returns.
11. Unknown profile -> command `failed` with `profile_not_found`, no infinite retry.
12. Plugin tests, backend gates, bridge tests all green; `openapi.json` regenerated; vendor check passes.

### 6.6 Do not do

No messaging sends, no document storage, no Stripe. Do not edit `hermes-agent/`. Do not restart the production gateway without founder approval.

## 7. Finish

End your run with the report format in section 5: status first, then exact gate outputs, files changed, decisions, what was not verified, and founder actions.
