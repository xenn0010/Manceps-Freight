# Manceps platform plan, part 1: decisions and architecture

Status: plan only. No application code was written for this plan.
Date: 2026-10-25. Author: lead architect agent.

This is part 1 of 6. The other parts:

- Part 2: `2026-10-25-manceps-platform-plan-part2-data-model.md` (collections, indexes, retention)
- Part 3: `2026-10-25-manceps-platform-plan-part3-api.md` (every `/v1` route)
- Part 4: `2026-10-25-manceps-platform-plan-part4-integrations.md` (vendor matrix, verified vs not)
- Part 5: `2026-10-25-manceps-platform-plan-part5-phases.md` (phases and acceptance criteria)
- Part 6: `2026-10-25-manceps-platform-plan-part6-risks-founder.md` (risks, guardrails, founder inputs)

Execution prompts: `docs/plans/execution-prompts/phase-NN-<name>.md`.

## 1. Bottom line

- Build **one Python backend** (FastAPI) in a new `backend/` folder, plus a **worker** from the same image.
- Add a small **agent bridge** that runs inside the Lima VM and only makes **outbound** calls.
- Keep the **hermes-freight plugin**. Extend it. Do not rewrite it.
- Atlas is the **only shared state**: the API, worker, bridge and plugin never call each other directly.
- Everything the agent does lands in the firm's MongoDB database. The API reads the same collections.
- Ship in **12 phases**. Phase 1 is a usable core (auth, firms, carriers, brokers, imports, loads, approvals, OpenAPI).

## 2. What exists today (read this session)

- `hermes-freight/` plugin: 10 tools, 1 hook (`pre_tool_call`), 73 tests passing per HANDOFF (not re-run here).
  - `tenant.py`: tenant id and Mongo URI come only from profile secrets. DB name `firm_<tenant>`.
  - `store.py`: collections `carriers`, `brokers`, `broker_checks`, `audit`. Indexes created on first use.
  - `policy.py`: blocks messages to non-consented numbers; sends carrier money/legal edits to the Hermes approval gate.
  - `deploy/provision_tenant.py`: creates Hermes profile, Atlas user (Admin API) or shared credentials, secrets.
  - `deploy/signup_worker.py`: claims `platform.signups`, provisions, sets `ready`.
  - `deploy/load_reference.py`: syncs FMCSA brokers and bonds into `freight_reference`.
- `signup-api/`: FastAPI on Vercel. Twilio Verify OTP, rate limits (`signup_attempts`), queue insert. Pyright is `basic`, not strict.
- `infra/`: systemd unit for the signup worker (VM), launchd plist that starts the Lima VM (Mac).
- Hermes (read in `hermes-agent/website/docs`, not changed):
  - API server on `127.0.0.1:8642` with `POST /v1/runs`, `GET /v1/runs/{id}/events` (SSE), `Idempotency-Key`,
    `session_id`. With multi-profile routing, `/p/<profile>/v1/...` needs that profile's own `API_SERVER_KEY`.
  - Hermes SMS and WhatsApp Cloud adapters need a **public HTTPS URL** to the gateway. Our VM has none. See D11.
  - There is **no agent-callable `send_message` tool** in Hermes (`tools/send_message_tool.py` comment). The plugin must
    supply its own message tool. `policy.check_send_message` therefore guards nothing today.
  - `cronjob` is a toolset (`cronjob_manage`). Firm profiles should not create their own schedules (D7).

## 3. Decisions (each with reason and rejected alternatives)

**D1. Service layout: three deployables.**
- `backend-api`: public REST + SSE + webhooks. `backend-worker`: jobs, scheduler, outbox delivery. Same image, two commands.
- `agent-bridge`: runs in the Lima VM next to the Hermes gateway. Talks to Atlas and `127.0.0.1:8642` only.
- Reason: a solo founder can run two containers and one systemd unit. The VM stays closed to the internet.
- Rejected: Vercel serverless for the API (no long SSE, no background loops); one service per domain (too many parts);
  opening a tunnel into the VM (violates "no inbound ports", adds an attack path to the agent host).

**D2. Where it runs.**
- API and worker on a container host with long-lived processes. Recommended Fly.io. **UNVERIFIED** (pricing, static
  egress IPs, regions not checked). Any host that runs Docker and gives HTTPS works. Domain: `api.<founder domain>`.
- Atlas Network Access: replace `0.0.0.0/0` (set for Colab, per HANDOFF) with the host egress IPs plus the Mac IP once
  the host is chosen. If the host has no stable egress IP, keep `0.0.0.0/0` and rely on credentials plus TLS (state this
  as an accepted risk in the phase gate report).
- Signup API on Vercel is retired after Phase 1 cutover; its code is ported (D5).

**D3. How the platform and the plugin share data.**
- A pure-Python package `backend/manceps_core` holds models, constants, index specs, consent and approval logic, event
  and audit writers. The API, worker and bridge import it. The plugin gets a **vendored copy** in
  `hermes-freight/_vendor/manceps_core/` (script `backend/scripts/vendor_core.py`; a test fails if the copies differ).
- Firm data is canonical in `firm_<tenant>`. One code path writes each entity (the core repository functions), so the
  API and the agent cannot drift.
- API and worker connect with one operator-level Atlas user (`readWriteAnyDatabase` on the cluster) through a
  `TenantDb` accessor that takes the tenant from the authenticated principal. The plugin keeps its per-firm Atlas user.
- Rejected: plugin calls the HTTP API (rewrites working tested code, couples the agent to API uptime); separate schemas
  for plugin and API (drift).
- Accepted risk: a stolen operator credential reads all firms. Mitigation: the credential lives only in API/worker
  secrets, never in the VM; the VM uses per-firm users.

**D4. Platform to agent and back: an Atlas command queue, pulled by the bridge.**
- Platform writes `platform.agent_commands`. The bridge claims them (atomic `find_one_and_update`), calls the Hermes
  API server for that profile, and writes results back. Same pattern as the existing signup queue.
- Rejected: webhook into the VM; polling Hermes from the API host (needs an inbound path).

**D5. Auth.**
- Login: phone OTP (Twilio Verify, ported from `signup-api/verify.py`) and email magic link.
- Access token: JWT signed with EdDSA, 15 minutes, claims `sub, tid, role, sid, aud`. Keys in env with `kid` for rotation.
- Refresh token: 256-bit opaque string, stored as SHA-256 hash in `platform.sessions`, rotated on every use, with a
  `family_id`. Reuse of a rotated token revokes the whole family. Browser gets it in an `HttpOnly; Secure; SameSite=Lax`
  cookie; native clients get it in the body when they send `X-Client: native`.
- Logout everywhere = revoke all sessions for the user (and bump `users.token_epoch`; access tokens carry `epoch`).
- Carriers and drivers: **scoped links**, not accounts. Opaque token, stored hashed in `platform.scoped_links` with
  `tenant_id, subject, scopes, expires_at, max_uses`. Exchange yields a 1-hour token with role `carrier` or `driver`
  that only works on `/v1/portal/*`.
- Rejected: sessions only (hard for native/SSE across origins); long-lived JWTs; carrier accounts with firm access
  (violates the META rule that carriers get scoped links).

**D6. Jobs: MongoDB collection with leases. No Redis.**
- `platform.jobs`: `kind, tenant_id, payload, run_at, status, attempts, locked_until, idempotency_key (unique)`.
  Claim with `find_one_and_update`; exponential backoff; dead-letter status after `max_attempts`.
- One platform-level collection means one poll query regardless of firm count. Idle workers back off to 5 seconds.
- Reason: Atlas Free allows 100 operations per second (verified, part 4). A second datastore is another secret, another
  bill and another failure mode for one founder.
- Rejected: Redis/RQ/Celery (extra infra); Hermes cron (D7); Atlas Triggers (not portable, hard to test).

**D7. Scheduler: platform-owned (`platform.schedules`), not Hermes cron.**
- The worker ticks every 15 seconds, claims due schedules, enqueues jobs. LLM work becomes an `agent_command`;
  deterministic work (document expiry, invoice aging) runs in the worker with no LLM.
- Reason: schedules must be visible and editable from the API, respect plan limits and quiet hours, and survive a VM
  rebuild. Hermes cron state lives in profile files on the VM.
- Firm profiles get `cronjob` added to `disabled_toolsets` in `deploy/managed-config.yaml`.

**D8. Object storage: Cloudflare R2 (S3 API).**
- Verified: presigned GET/PUT up to 7 days; **POST form uploads are not supported**; presigned URLs do not work on custom
  domains (part 4). So uploads go **through the API** (size cap, magic-byte check, virus scan, then PUT to R2), and
  downloads use 5-minute presigned GET URLs.
- Key layout: `t/<tenant_id>/<doc_id>/<sha256>`. Object versioning is not assumed (UNVERIFIED).
- Rejected: GridFS on Atlas (512 MB Free cap, bills storage at database prices); direct browser PUT (cannot enforce a
  size limit with presigned PUT: UNVERIFIED, so we do not rely on it).

**D9. Real-time: SSE over an `events` collection.**
- Every state change appends `firm_<t>.events {seq, type, ref, at}` (seq from a per-firm counter). `GET /v1/events/stream`
  tails by `seq` and supports `Last-Event-ID` resume. One poller per tenant per API process fans out to all connections.
- Upgrade path on dedicated clusters: change streams. On Free tier, change-stream namespace filters are restricted
  (verified, part 4), so polling is the baseline.
- Rejected: WebSockets (not needed, one-way push); a message broker.

**D10. Per-firm Atlas users and Free tier limits.**
- Verified limits (part 4): Free = 512 MB, 100 ops/s, 500 connections, **100 databases and 500 collections total**,
  10 GB in/out per rolling 7 days. Atlas allows **100 database users per project**.
- Collections per firm in this plan: about 27, indexes about 70. Free tier fits roughly **15 firms** (500 collections
  minus about 40 for `platform` and `freight_reference`). So the real trigger is collections, not users.
- On M10 the recommended maximum is 5,000 collections and indexes combined (verified): about **50 firms**. M20/M30
  (10,000): about 100 firms. M40+ (100,000): about 1,000 firms.
- The 100-user cap is the next wall: about 90 firms per project. Plan: `firms.atlas_shard` field and a shard registry so a
  second Atlas project and cluster can take new firms. Built in Phase 12; the field exists from Phase 1.
- **Upgrade rule:** move off Free before the 8th paying firm. State in Phase 1 founder inputs.

**D11. Messaging goes through the platform, not Hermes gateway adapters.**
- Twilio, WhatsApp Cloud, Telegram and email webhooks hit `backend-api` (public). The API verifies signatures, dedupes by
  provider message id, writes `messages`, then enqueues routing.
- Outbound is one path: agent tool `message_send` (plugin) or human `POST /v1/messages/send` both write `outbox` and the
  worker sends after the **shared consent check** (`manceps_core.consent.can_contact`).
- Reason: consent enforcement in one place; the VM needs no public URL; Hermes SMS/WhatsApp adapters cannot receive
  webhooks without one (docs in `hermes-agent/website/docs/user-guide/messaging/sms.md`, `whatsapp-cloud.md`).
- Telegram and the dispatcher's own chat are optional extras; the main dispatcher channel is the web app plus SMS.

**D12. Approvals are executable proposals, enforced in code.**
- Agent calls tool `approval_request(kind, subject_ref, payload, summary)`. The platform stores `approvals` with a
  `payload_hash`. A human decides through `POST /v1/approvals/{id}/decision`.
- On approve, the **worker applies the action itself** through a registry (`manceps_core.approvals.actions`), idempotent
  by `applied_at`. The agent is then told the result with an `agent_command`.
- The model never gets the power to "just do it": tools that accept a rate, approve a Rate Con, bill a carrier or send an
  invoice do not exist for the agent. They exist only as approval kinds.
- `policy.py` changes: in platform mode (`FREIGHT_APPROVAL_MODE=platform`) a sensitive carrier edit is **blocked** with
  the message "use approval_request". This avoids relying on the Hermes gate in non-interactive runs. HANDOFF shows the
  gate blocked in a non-interactive run and an interactive test was never done.
- Rejected: Hermes `approve` directive as the primary path (UNVERIFIED over the API for plugin directives; fine as extra).

**D13. Dispatch-fee money.**
- The dispatch fee is the **firm's** revenue from its carriers. The platform must not collect it into its own balance.
- Plan: Stripe Connect with Standard connected accounts and **direct charges** (invoice lives on the firm's account), ACH
  Direct Debit for carriers. Platform subscription uses the platform's own Stripe account.
- **UNVERIFIED:** Connect account type, whether this is lawful without a money transmitter analysis, and ACH risk for the
  firm. Needs a lawyer before Phase 8 ships (part 6). Verified from Stripe docs: ACH settles in up to 4 business days,
  business-account debits can be disputed for up to 2 business days, consumer for 60 days, mandate required (part 4).

**D14. Chat with the agent.**
- Conversations and messages are stored in the firm DB. `POST /v1/conversations/{id}/messages` stores the user message and
  enqueues a `chat` command. The bridge runs it via `POST /p/<profile>/v1/runs` with `session_id = conversation id` and
  `Idempotency-Key = command id`, streams events to `platform.agent_stream` (TTL 1 hour), and writes the final assistant
  message to the firm DB. `GET /v1/conversations/{id}/stream` is SSE over that collection.

**D15. Agent memory is visible and editable.**
- Structured memory goes in `memory_facts` (entity ref, text, source, confidence). The agent writes it with
  `fact_remember` and reads it with `fact_recall`. Humans can edit or delete it from the API.
- Hermes built-in memory stays for style preferences only. Its internals are not queryable from outside (UNVERIFIED API).

**D16. Network layer is a separate pipeline.**
- A nightly job derives anonymized signals into `platform.network_signals` (no tenant id, no rates). A scorecard is
  served only when at least `NETWORK_MIN_COHORT = 5` distinct firms contributed. Enforced in `manceps_core.network`.

## 4. Architecture

```
                         Internet
   Browser/app (later)    Twilio  Meta  Vapi  Stripe  Motive  Samsara  DocuSeal  Gmail
          |                  |      |     |      |       |       |        |       |
          +------ HTTPS -----+------+-----+------+-------+-------+--------+-------+
                                   |
                       +-----------v------------+
                       |  backend-api (FastAPI)  |  REST /v1, SSE, webhooks, OpenAPI
                       |  auth, tenancy, limits  |
                       +-----------+------------+
                                   |                      +-------------------+
        +--------------------------+---------------+      | Cloudflare R2      |
        |                                          |      | documents          |
+-------v--------+                        +--------v---+  +---------^---------+
| backend-worker |------ S3 API ----------> (same code)  |            |
| jobs, schedule |----------------------------------------------------+
| outbox, sync   |
+-------+--------+
        |
        |  MongoDB Atlas (only shared state)
        |  platform | firm_<tenant> x N | freight_reference
        |
========|=================== no inbound path ====================== outbound only
        |
+-------v------------------------------ Lima VM (Mac) ----------------------------+
|  agent-bridge  --127.0.0.1:8642-->  Hermes gateway (one host, profile per firm)    |
|  (systemd user)                      plugin hermes-freight + vendored core         |
|                                      per-firm Atlas user, model keys, Vapi tools   |
+-----------------------------------------------------------------------------------+
```

Data flow, one example (inbound broker SMS):
1. Twilio posts to `/v1/webhooks/twilio/sms`. API verifies `X-Twilio-Signature`, dedupes by `MessageSid`.
2. API resolves the firm from `platform.endpoints` (the called number), writes `messages`, enqueues `message.route`.
3. Worker classifies the sender: dispatcher, carrier, driver, broker contact, or unknown. STOP/HELP handled here.
4. Worker writes `agent_commands {kind: "inbound_message"}`. Bridge runs the agent. Agent calls `message_send` or
   `approval_request`. Both write to the firm DB. SSE pushes `message.created` and `approval.created` to the browser.

## 5. Service boundaries and data ownership

| Component | Owns (writes) | Reads | Never does |
|---|---|---|---|
| backend-api | `platform.users/sessions/firms/endpoints/...`, firm CRUD collections, `approvals` decisions | everything per tenant | call Hermes, send messages directly |
| backend-worker | `jobs`, `schedules`, `outbox` state, sync tables, apply approvals | everything per tenant | serve public traffic |
| agent-bridge | `agent_commands` state, `agent_stream`, `bridge_heartbeat`, assistant `messages` | `agent_commands`, firm profile keys on VM | accept inbound connections, call vendors |
| hermes-freight plugin | via core: `carriers`, `brokers`, `broker_checks`, `loads` (proposals only), `approvals` (requests), `memory_facts`, `outbox`, `audit` | its firm DB, `freight_reference` | write another firm's DB, accept a rate, send directly |
| signup worker (existing) | `platform.signups`, creates Hermes profile | `platform.signups` | change in Phase 1 except the `firms` hand-off |

Per-collection ownership is listed in part 2.

## 6. Repository layout after Phase 1

```
backend/
  pyproject.toml            uv, Python 3.11+, pyright strict, ruff, pytest-cov
  manceps_core/             shared (also vendored into the plugin)
  manceps_api/              app factory, deps, errors, routes/, auth/, integrations/<vendor>/
  manceps_worker/           runner, scheduler, handlers/
  tests/                    unit + e2e (mongomock + fake transports)
  scripts/                  vendor_core.py, export_openapi.py
  openapi.json              committed, checked in CI
agent-bridge/               arrives in Phase 2
hermes-freight/             existing plugin, extended
signup-api/                 frozen after Phase 1, deleted after cutover
infra/                      adds container host files, bridge unit
```

## 7. Cross-cutting rules every phase follows

- Settings: one `Settings` class (pydantic-settings) in `manceps_api/settings.py`. Missing vendor credentials set that
  integration to `not_configured`; its routes answer 503 with code `integration_not_configured`.
- Error envelope `{"error": {"code", "message", "details"}}`; stable `operationId` = `<resource>_<verb>`.
- Pagination: opaque cursor (`?cursor=&limit=`), default 50, max 200; response `{items, next_cursor}`.
- Idempotency: `Idempotency-Key` header on every POST that creates or moves money; stored in `platform.idempotency_keys`
  for 24 hours; same key plus same body hash replays; different body is 409.
- Rate limits: per IP and per principal, stored in `platform.rate_limits` (reuse the `signup_attempts` pattern).
- Audit: every write appends `firm_<t>.audit {who, what, when, request_id, session_id, before_hash, after_hash}`.
- Webhooks: verify signature, store raw event in `platform.webhook_events` (unique on `provider+event_id`), return 2xx fast,
  process in a job.
- Logging: structlog JSON, fields `request_id, tenant_id, user_id, job_id`. Secrets are redacted by a processor.
- Time: all datetimes timezone-aware UTC; firm timezone stored on the firm for schedules and quiet hours.
- Money: integer cents in `*_cents` fields. Never floats for stored money.
