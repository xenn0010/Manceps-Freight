# Manceps platform plan, part 5: phases

Rules for all phases:

- Each phase is shippable alone and ends with the META_PROMPT gates (pytest, ruff, pyright strict, coverage >= 90% on the
  platform package, committed `openapi.json`, security self-check, short end-to-end test).
- Size: S = about 1 day of agent work, M = 2 to 3 days, L = 4 to 6 days. "Agent work" means a build agent session plus review.
- "AC" = acceptance criterion. Each is a testable statement; the execution prompt tells the agent which test proves it.
- Execution prompts: `docs/plans/execution-prompts/phase-NN-<name>.md`.
- Paths are relative to the repo root. New code goes in `backend/` unless stated.

## Phase list

| # | Name | Delivers | Depends on | Size |
|---|---|---|---|---|
| 1 | core | auth, firms, team, carriers, drivers, trucks, brokers, contacts, imports/exports, loads, approvals, events SSE, OpenAPI | none | L (run as 5 work packages) |
| 2 | agent-bridge | bridge on the VM, chat API, approval flow from the agent, memory facts, job system, scheduler, morning brief | 1 | L |
| 3 | documents-portal | R2 vault, scan, parse, expiry reminders, carrier/driver portal, claims | 1, 2 | M |
| 4 | messaging-core | consent ledger, outbox, Twilio SMS, SMTP/IMAP email, inbox API, firm branding and packet | 2, 3 | L |
| 5 | voice-vapi | Vapi webhooks, server tools, call log, consented outbound | 4 | M |
| 6 | channels-extra | WhatsApp Cloud, Telegram, Gmail OAuth + push | 4 | M |
| 7 | billing | Stripe subscription, plan limits, trial, dunning | 1 | M |
| 8 | invoicing-fees | invoices, payments, aging, factoring handoff, dispatch-fee invoices via Connect + ACH | 3, 7 | L |
| 9 | integrations-data | FMCSA sync schedule, Motive and Samsara OAuth, DocuSeal e-sign | 3, 4 | L |
| 10 | load-intake | inbound email load triage, load source adapters (123Loadboard behind a flag) | 4, 6 | M |
| 11 | network-layer | anonymized broker scorecards, fraud alerts | 1, 8 | M |
| 12 | ops-hardening | operator API, flags, observability, backups, firm export/delete, Atlas user and shard scaling, seeds | all | L |

Recommended order: 1, 2, 3, 4, 7, 5, 6, 8, 9, 10, 11, 12. Phases 7 and 5/6 may swap or run in parallel.
Frontend work can start after Phase 1 against `openapi.json`; each later phase only adds routes.

---

## Phase 1: core (L)

**Goal.** A frontend can sign a dispatcher up, log in, manage carriers, drivers, trucks, brokers and loads, import their
spreadsheets, and decide approvals, with live updates, and no agent needed.

**Work packages (each ends in a green gate; commit after each).**
- WP1.1 foundation: `backend/` project, settings, logging, error envelope, `TenantDb`, core repo base, indexes, events,
  audit, idempotency, rate limits, OpenAPI export, CI script.
- WP1.2 auth, firms, team: ported OTP, magic link, JWT, refresh rotation, sessions, memberships, invitations, firm activation
  from `platform.signups`, scoped-link exchange.
- WP1.3 data management: carriers, drivers, trucks, brokers (+ reference search and `broker_check`), contacts, facilities,
  notes, consent ledger (records only, no sending yet).
- WP1.4 imports and exports: CSV, XLSX, vCard, Google Contacts CSV; mapping, preview, report, commit, undo, dedupe.
- WP1.5 loads, approvals, events: load state machine, evaluate, approvals with action registry, SSE stream, tenant matrix
  test, end-to-end test.

**Files and modules (new).**
- `backend/pyproject.toml`, `backend/manceps_core/{tenancy,ids,phone,money,errors,audit,events,idempotency,indexes,consent}.py`
- `backend/manceps_core/models/{carriers,drivers,trucks,brokers,contacts,loads,approvals,imports}.py`
- `backend/manceps_core/repo/{carriers,brokers,contacts,loads,approvals,imports}.py`
- `backend/manceps_core/approvals/{registry,actions}.py`, `backend/manceps_core/loads/{machine,evaluate}.py`
- `backend/manceps_api/{main,settings,deps,errors,logging}.py`, `auth/{tokens,sessions,otp,magic,scoped}.py`
- `backend/manceps_api/routes/{auth,me,firm,members,carriers,drivers,trucks,brokers,contacts,facilities,notes,imports,exports,loads,approvals,events,integrations,health}.py`
- `backend/manceps_api/imports/{parsers,mapping,validate,dedupe,commit,undo}.py`
- `backend/manceps_worker/{runner,handlers/{import_commit,export,firm_activate}}.py` (minimal; full job system is Phase 2)
- `backend/scripts/{export_openapi,vendor_core}.py`, `backend/openapi.json`
- Modify: `hermes-freight/store.py` is unchanged in Phase 1. Existing `carriers/brokers` field names are kept, so imported
  data is readable by the plugin.

**AC.**
1. `POST /v1/auth/otp/verify` with a fake verifier creates a user, a `signups` row (status pending) and returns tokens; the
   signup worker test fixture then sets `ready` and a job creates `platform.firms` + owner membership.
2. A token for firm A returns 404 for every `/v1` resource id from firm B (generated matrix over the OpenAPI schema).
3. Refresh-token reuse revokes the family; `logout-all` makes existing access tokens fail within one request (epoch check).
4. Access tokens expire at 15 minutes (clock-injected test); wrong `aud` or `kid` is 401.
5. Viewer gets 403 on every write route; dispatcher gets 403 on owner-only routes (matrix test).
6. Carrier phone is unique per firm and normalized; duplicate create is 409.
7. `PATCH /v1/carriers/{id}` of `dispatch_fee_pct` by a dispatcher returns 409 `approval_required`; the owner can change it and
   an audit record exists with before and after hashes.
8. Consent grant without `method` is 422; every grant/revoke appends a `consent_events` row; the carrier cache matches the ledger.
9. A CSV with 1,000 carrier rows (5 invalid, 20 duplicates of existing) previews with correct counts; commit creates
   exactly the valid new rows; re-uploading the same file hash returns the original import and creates nothing.
10. Undo within 24 h restores updated rows byte-for-byte (compared to `before`) and deletes created rows; undo at 25 h is 409.
11. XLSX with merged header cells, dates as Excel serials and phones as floats imports correctly; vCard with 3 phones per
    contact maps the first mobile; Google Contacts CSV maps by header names. Fixtures committed under `backend/tests/fixtures/`.
12. A file larger than 10 MB or over 20,000 rows is rejected 413/422 before parsing completes (streaming limit test).
13. Load transitions follow the table in part 2; illegal ones are 409; `booked` without a carrier is 409; direct transition to
    `approved` or `booked` is 409 `approval_required`.
14. `POST /v1/approvals` of kind `accept_rate`, then decision `approve` with the correct `payload_hash`, moves the load to
    `booked` exactly once even if the decision is retried (idempotent `applied_at`). Wrong hash is 409.
15. `GET /v1/events/stream` delivers `approval.created` within 2 seconds of creation, resumes from `Last-Event-ID`, and never
    delivers another firm's events (two-firm test).
16. `backend/openapi.json` equals the generated schema (CI diff); every operation has an `operationId`; error envelope is
    present in all 4xx responses.
17. Rate limit: 11th OTP verify in an hour for one phone is 429; OTP start with Twilio unset is 503.
18. Pyright strict has 0 errors on `backend/`; the plugin's 73 tests still pass; `vendor_core.py --check` passes.

**Founder provides.** Twilio Verify (already have), Atlas operator URI, JWT signing keys generated by a script (agent writes
the script; founder stores output), SMTP credentials for magic links (or skip email login in Phase 1: flag `EMAIL_LOGIN_ENABLED`).
Apply to 123Loadboard partner program now (long lead time). Decide the container host.

---

## Phase 2: agent-bridge (L)

**Goal.** The dispatcher chats with Manceps through the API, the agent raises approvals that appear in the inbox, decisions
flow back, and scheduled jobs run, with all traffic outbound from the VM.

**Files.**
- New: `agent-bridge/{pyproject.toml, manceps_bridge/{main,claim,runner,hermes_client,profiles,heartbeat,settings}.py, tests/}`
- New: `infra/vm/manceps-agent-bridge.service`
- New: `backend/manceps_core/{commands,memory,jobs}.py`, `backend/manceps_worker/{scheduler,jobs,handlers/{brief,approval_apply,command_ttl}}.py`
- New routes: agent, conversations, commands, memory, schedules, briefs (part 3 section 10).
- Plugin: new tools `approval_request`, `approval_status`, `fact_remember`, `fact_recall`, `load_propose`, `load_get` (modules
  `hermes-freight/approvals.py`, `memory.py`, `loadtools.py`), schemas in `schemas.py`, `plugin.yaml` updated, core vendored.
- Modify `hermes-freight/policy.py` (platform mode blocks sensitive carrier edits), `deploy/provision_tenant.py` (writes
  `API_SERVER_ENABLED`, `API_SERVER_KEY`, `FREIGHT_APPROVAL_MODE=platform`), `deploy/managed-config.yaml` (add `cronjob`),
  `profile/SOUL.md` (approval protocol, memory protocol).

**AC.**
1. Spike (first task, before design lock): on the VM, two profiles served by the multiplexed gateway answer `POST
   /p/<profile>/v1/runs` with their own keys; a wrong key is 401; run ids from profile A are 404 for profile B. If this fails,
   the report says so and the phase stops (fallback: one API port per profile).
2. Bridge claims a queued `chat` command exactly once under 5 concurrent bridge instances (atomic claim test).
3. A chat command produces `agent_stream` rows in order and a final assistant message in the firm DB; killing the bridge
   mid-run leaves the command `claimed`; after `CLAIM_TTL=120s` another bridge retries using the same `Idempotency-Key`
   and does not run the agent twice (fake Hermes records calls).
4. `GET /v1/agent/status` reports `offline` after 90 s without heartbeat; sending a chat then is 503 `agent_offline`.
5. Agent tool `approval_request(kind=accept_rate, ...)` creates one pending approval with `payload_hash`; the same call twice
   within the same run returns the same approval (idempotent on `command_id + payload_hash`).
6. After approve, an `approval_result` command is created and the load is `booked` before the agent is told.
7. The agent cannot write loads past `evaluating` by any tool (tool inventory test: no tool sets `approved/booked/paid`).
8. `policy.py` in platform mode blocks `carrier_upsert` of sensitive fields with a message naming `approval_request`.
9. Scheduler: a schedule due at T runs once even with 3 worker instances; a missed tick catches up once, not N times.
10. Quiet hours suppress agent-initiated outbound jobs but not deterministic jobs.
11. Morning brief job writes a `briefs` doc and an `agent_commands` row; with the agent offline the brief falls back to a
    deterministic summary (no LLM) and is marked `fallback`.
12. Memory: `fact_remember` creates a fact, API edit changes it, `fact_recall` returns the edited text.
13. Unknown profile in a command is `failed` with `profile_not_found`, not retried forever.

**Founder provides.** Access to the VM for deploy (or approval to run `limactl shell`), Anthropic and DeepSeek keys already in
profiles, decision on gateway restart window.

---

## Phase 3: documents-portal (M)

**Goal.** Documents are stored, scanned, parsed, tracked for expiry, and carriers or drivers can upload and update status
through scoped links.

**Files.** `backend/manceps_api/{storage/{r2,fake}.py, documents/{upload,scan,parse}.py, routes/{documents,portal,claims}.py}`,
`backend/manceps_core/{repo/documents,repo/claims}.py`, worker handlers `document_scan`, `document_parse`, `expiry_scan`,
`ratecon_attach`. Plugin: `document_list`, `document_parse_result` tools; bridge downloads inbound attachments to the
profile's `cache/documents/` so existing `ratecon_read` keeps its path lock.

**AC.**
1. A `.exe` renamed `.pdf` is rejected (magic bytes); a 16 MB file is 413; allowed types only.
2. EICAR test string uploaded -> `quarantined`, never downloadable; clamd unavailable -> stays `scanning`.
3. Download URL expires in 300 s (signature check with injected clock); every URL issuance is audited.
4. COI parse extracts expiry date; `expires_at` set; a reminder row is created at T-30 and T-7 days; reminder text goes to the
   outbox only if consent exists, otherwise to the dispatcher task list (event `document.expiring`).
5. Scoped link token for carrier A cannot see carrier B's loads or documents (matrix test); link revoked -> 401 within one request.
6. Driver status `delivered` without POD document is allowed but load stays `at_delivery` until POD is attached.
7. Detention claim math: free time hours + rate come from `claims` payload; amount computed in cents; over cap (`MAX_CLAIM_CENTS`) -> 422.
8. Fake R2 and real boto3 client both pass the same contract tests.

**Founder provides.** R2 bucket and API token; ClamAV host sizing; legal retention periods (part 6).

---

## Phase 4: messaging-core (L)

**Goal.** One consent-checked outbound path and a unified inbox: SMS (Twilio) and email, plus firm branding and the public
carrier packet data.

**Files.** `backend/manceps_core/{consent,outbox}.py` (extend), `backend/manceps_api/integrations/{twilio,smtp,imap}/`,
`routes/{messages,endpoints,webhooks_twilio,branding,packet}.py`, worker `outbox_deliver`, `message_route`, `email_poll`,
`reminders_send`. Plugin: tool `message_send` (writes outbox), `message_history`. Remove vestigial reliance on
`policy.check_send_message` by keeping it as a second guard.

**AC.**
1. Twilio webhook with a bad signature is 403; same `MessageSid` twice stores one message.
2. Outbound to a number without consent: outbox status `blocked`, `consent_check.reason = no_consent`, no HTTP call to Twilio
   (fake transport asserts zero calls). Public FMCSA phone numbers never count.
3. Inbound `STOP` writes a revoke event before routing; subsequent send is blocked; `START`/`UNSTOP` does not re-grant
   (re-grant requires a human consent record).
4. First message to any new contact contains the AI disclosure string (template test); messages from the agent carry it,
   human-sent messages do not.
5. Daily cap `agent_settings.daily_message_cap` blocks the (cap+1)th agent message with a visible reason.
6. Quiet hours hold agent messages until the window opens (`send_after`).
7. Email: SMTP send via fake; IMAP poll creates `messages`, dedupes by Message-ID, attachments become documents (Phase 3).
8. Unknown sender SMS is stored and flagged `unknown_sender`; no agent reply is sent (no consent).
9. Public packet endpoint returns no carrier, load or rate data (schema test with a fully populated firm).
10. Twilio 429/5xx are retried with backoff up to `OUTBOX_MAX_ATTEMPTS`; permanent errors (21610 unsubscribed) set `failed` with no retry.

**Founder provides.** Twilio brand/campaign registration, number, messaging service; SMTP/IMAP; sending-domain DNS.

---

## Phase 5: voice-vapi (M)

**Files.** `backend/manceps_api/integrations/vapi/{client,webhook,tools}.py`, `routes/{calls,webhooks_vapi}.py`,
`calls` collection handlers; update `hermes-freight/vapi/assistant.json` and a `deploy/vapi_sync.py` that pushes it.

**AC.**
1. Webhook without the correct credential is 401 (until the scheme is verified from Vapi docs, all requests are rejected).
2. `tool-calls` response matches the verified shape `{"results":[{"name","toolCallId","result"}]}`.
3. `take_broker_offer` stores an offer as a `loads` row in `offered` and never changes status past `evaluating`.
4. `end-of-call-report` creates a `calls` row, summary and structured data, and an event; duplicate report is a no-op.
5. `POST /v1/calls/outbound` without `voice` consent is 422; with consent it creates an `outbound_call` approval; after
   approval the worker posts `POST /call` once (fake), with `firstMessage` containing the AI disclosure.
6. Calls outside the allowed local hours are held (`send_after`).
7. `assistant-request` answers within 7.5 s in a latency test with a slow DB fake (timeout returns a safe default).

**Founder provides.** Vapi private key, webhook credential, phone number ids, call-hour policy from a lawyer.

---

## Phase 6: channels-extra (M)

**Files.** `integrations/{whatsapp,telegram,gmail}/`, routes `webhooks_whatsapp`, `webhooks_telegram`, `webhooks_gmail`, Gmail OAuth routes,
worker `gmail_watch_renew`, `gmail_history_sync`.

**AC.** WhatsApp GET challenge echoes only with the right verify token; POST needs a valid signature; duplicates deduped; no
outbound WhatsApp without `whatsapp` consent; free-form send outside the service window is refused unless a template is
named (rule confirmed from Meta docs first). Gmail `watch` renewed daily by a schedule, a lost notification is recovered by
`history.list` polling, OAuth `state` is verified, tokens are stored encrypted and never returned. Telegram webhook rejects a
wrong secret. Each integration is `not_configured` without credentials (503).

**Founder provides.** Meta app + business verification, WhatsApp number, Google Cloud project, OAuth consent screen (and
restricted-scope review before public launch), Telegram bot token.

---

## Phase 7: billing (M)

**Files.** `integrations/stripe/{client,webhook,plans}.py`, `routes/{billing,webhooks_stripe}.py`, `manceps_core/limits.py`.

**AC.**
1. Stripe webhook with a stale timestamp (> 5 min) or bad signature is 400; the same event id twice is processed once.
2. Out-of-order `invoice.paid` before `customer.subscription.created` ends with the correct final state (handler re-fetches objects).
3. Trial: a firm created without payment has `trialing` for `TRIAL_DAYS` and plan limits of the trial plan.
4. Limit enforcement: creating the (limit+1)th carrier returns 402 `plan_limit_reached` with the limit name.
5. `past_due` for more than `DUNNING_GRACE_DAYS` pauses agent-initiated outbound and schedules; reads and approvals still work.
6. Checkout and portal routes return 503 without Stripe keys; no route silently succeeds.

**Founder provides.** Stripe account, products and prices (test first), webhook secret, plan limits and prices.

---

## Phase 8: invoicing-fees (L)

**Files.** `manceps_core/{repo/invoices,money,aging}.py`, `integrations/{stripe_connect,factoring/{email,otr}}`, routes `invoices`,
`receivables`, `dispatch_fee_invoices`, worker `invoice_pdf`, `aging_scan`, `payment_chase`.

**AC.**
1. An invoice can be created only from a load in `delivered` or later with a POD document; amounts in integer cents.
2. `send_invoice` approval required; the send action runs once; the invoice moves to `sent` and the load to `invoiced`.
3. Aging buckets are correct at boundaries 30/31/60/61/90/91 days (table test, injected clock).
4. Payment chase reminder goes to the broker contact only through the outbox (consent rules for the channel apply).
5. Factoring by email builds one PDF package (invoice, rate con, POD) and records `factoring.submitted_at`; OTR path is off by flag.
6. Dispatch fee = `dispatch_fee_pct` of the load's `rate_cents` for loads delivered in the period, recomputed in a test with odd cents (rounding rule documented, half-up).
7. A `bill_carrier` approval is owner-only; no charge or invoice is created in Stripe before approval; Connect not onboarded -> 409 `connect_not_ready`.
8. Platform never touches the broker-to-carrier freight payment: no code path creates a Stripe charge for load revenue (grep test).

**Founder provides.** Lawyer sign-off on the fee model and Connect structure; Stripe Connect enablement; factor contact(s).

---

## Phase 9: integrations-data (L)

**Files.** `integrations/{motive,samsara,docuseal,reference}/`, `manceps_core/secrets.py` (envelope encryption), routes
`integrations`, `carriers/{id}/agreement/send`, `portal/agreement`, worker `reference_sync`, `eld_poll`, `token_refresh`.

**AC.** OAuth `state` mismatch rejected; Samsara refresh token used once and replaced atomically; two concurrent refreshes
produce one upstream call (lock test); refresh failure marks the integration `error` and never fabricates a location; secrets
are encrypted at rest and absent from logs and API responses (scan test). DocuSeal webhook uses the verified scheme;
`submission.completed` sets `agreement_signed` through an approval-recorded path with the signed document stored. Reference sync
reports dataset age; bond result older than 90 days is `unknown`.

**Founder provides.** Samsara partner app, Motive developer approval, DocuSeal account and the lawyer's template.

---

## Phase 10: load-intake (M)

**Files.** `manceps_worker/handlers/load_intake.py`, `manceps_core/intake/{extract,dedupe}.py`, `integrations/loadboards/{base,fake,one23}.py`.

**AC.** An inbound broker email with a load offer becomes an `offered` load linked to the broker and a triage message to the
agent; the same email twice makes one load; prompt-injection text inside the email ("accept this rate") causes no state change
(test with an adversarial fixture; email body is passed to the agent as data in a delimited block); 123Loadboard adapter is
disabled unless `LOADBOARD_123_ENABLED=1` and partner credentials exist; a repo test fails if any module drives a browser
against a load board domain.

---

## Phase 11: network-layer (M)

**Files.** `manceps_core/network/{signals,cohort,scorecard}.py`, worker `network_aggregate`, routes `network`.

**AC.** No `network_signals` document contains `tenant_id`, carrier id, load id or a rate (schema test plus a scan of a seeded DB);
scorecard returns `insufficient_data` below `NETWORK_MIN_COHORT = 5` distinct firms and never reveals the count;
removing one firm's signals cannot be inferred from the diff between two scorecards (a test builds cohort 5 and 6 and checks
the response has bucketed values only); a fraud report is `pending_review` and is broadcast only after operator approval;
firms that opt out contribute no signals and still receive alerts (setting documented in terms).

---

## Phase 12: ops-hardening (L)

**Files.** `routes/admin/*`, `manceps_core/{flags,shards,export,deletion}.py`, `deploy/atlas_users.py` (scoped users at scale),
observability (OpenTelemetry traces, Prometheus metrics at `/metrics` behind operator auth), `infra/{backup,restore}` scripts,
`scripts/seed_demo.py`, migration runner.

**AC.** Operator token never works on firm routes and vice versa; suspended firm gets 403 on all `/v1` firm routes and its
agent commands are not claimed; export bundle contains every firm collection with counts matching the DB; deletion removes the
database, the Atlas user and the R2 prefix and leaves `billing_accounts` and `operator_audit`; `atlas_users.py` creates a user whose
connection can read/write only its database (integration test against a real Atlas project, run by the founder once);
shard allocation picks a project with fewer than `ATLAS_USERS_SOFT_LIMIT = 90` firms; backups restore into a scratch cluster
and the restore script verifies counts; metrics include job lag, command queue depth, SSE connections, webhook failures; seed
creates a demo firm with 10 carriers, 40 loads and refuses to run when `ENV=production` without `--force-demo`.
