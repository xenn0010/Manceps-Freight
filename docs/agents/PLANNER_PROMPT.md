# Planner prompt: Manceps production backend

You are the lead architect for Manceps. Produce the complete, buildable plan for a
production-ready backend, so that after it is executed the only remaining work is a frontend.
You write the plan and the per-phase execution prompts. You do not write application code.

## Read first (all of it)

- `docs/agents/META_PROMPT.md`: the quality bar and product rules. Your plan must satisfy it.
- `HANDOFF.md`: history and earlier decisions (some are superseded; this prompt wins).
- `docs/plans/2026-10-25-signup-backend-design.md`: the signup queue already built.
- `hermes-freight/`: the agent plugin (tenancy, carriers, brokers, broker_check, reference data,
  ratecon reader, load evaluator, weather, policy hook, provisioning, signup worker, SOUL.md).
- `signup-api/`: FastAPI phone-OTP signup + Atlas queue.
- `infra/`: VM service unit and Mac launch agent.
- Skim `hermes-agent/` only to learn the plugin API, profiles, gateway, cron, and messaging
  platforms (do not plan changes to it).

## Current runtime facts

- Agent runtime: Hermes (pinned commit 1c0cd66774) in a Lima Ubuntu VM on the founder's Mac,
  one host gateway serving all firm profiles, systemd user services, no inbound ports.
- Data: MongoDB Atlas (free tier today). Per-firm DB `firm_<tenant>`, shared `freight_reference`
  (FMCSA brokers + bonds), `platform` (signup queue).
- Models: Claude Sonnet 5.5 main, DeepSeek V4 Pro fallback/chores. Agent is named Manceps.
- Voice: Vapi (inbound live on a Vapi number). SMS/WhatsApp: not yet. Email: not yet.

## Scope: the whole platform (plan all of it, phased)

**Accounts and firms (Shopify "store")**
- Signup (phone OTP, email magic link), login, sessions, refresh tokens, logout everywhere.
- Firm creation and provisioning (wraps the existing queue/worker), firm settings, branding,
  public carrier-packet page data, firm phone number and inbox assignment.
- Team members and roles, invitations, audit log viewer.
- Subscription billing for the firm (Stripe Billing), plan limits, trial, dunning states.

**Data management (Shopify "admin")**
- Carriers (owner-operators), drivers, trucks/equipment, carrier documents (W-9, COI,
  authority, agreement) with expiry tracking and reminders.
- Contacts/CRM: brokers, shippers/facilities, broker contacts, notes, tags, broker memory.
- **Imports:** CSV and Excel (.xlsx) import for carriers, drivers, brokers, contacts and past
  loads, with column mapping, preview, validation report, dedupe/merge, idempotent re-import,
  and an undo window. Contact import from vCard and Google Contacts CSV. Exports to CSV/XLSX.
- Loads: full lifecycle (offered, evaluating, countered, approved, booked, rate con received,
  dispatched, at pickup, in transit, delivered, POD received, invoiced, paid, cancelled/TONU),
  stops, documents, events timeline, detention/layover/TONU claims.
- Documents vault: uploads to object storage, virus/type checks, OCR/parse via Claude,
  signed URLs, retention.
- Invoices and payment tracking (factoring handoff by email/API, aging, reminders), dispatch fee
  invoices to carriers via Stripe Invoicing + ACH.

**The agent (Muse-style persistent personal agent)**
- Per-firm Manceps agent with long-term memory (carriers, brokers, lanes, preferences, deals).
- Approval inbox: every approval request the agent raises, approve/deny from the API, with the
  decision fed back to the agent; full history.
- Conversation API: the frontend can chat with the firm's agent and stream replies.
- Autonomous loop: scheduled jobs (morning brief, load-email triage, check-call cadence,
  document expiry, payment chasing) driven by Hermes cron or the platform scheduler.
- Bridge between platform and agent: how platform events reach the agent and how agent tool
  results land in platform data (single source of truth per entity, no drift).

**Integrations (each with a fake transport for tests and a "not configured" state)**
- Messaging: Twilio SMS (A2P/toll-free aware), WhatsApp Cloud API, Telegram, email (Gmail API
  OAuth and/or IMAP/SMTP), inbound webhooks for each.
- Voice: Vapi (inbound assistant, server tool calls, end-of-call reports, outbound with consent).
- Data: FMCSA QCMobile + data.transportation.gov reference sync (existing), EIA, NWS weather,
  Google Routes / OpenRouteService, Motive and Samsara ELD (OAuth per carrier), DocuSeal
  e-signature, Stripe (billing, invoicing, webhooks), factoring (OTR API; email fallback).
- Load sources that are legal: inbound broker email/calls, 123Loadboard partner API, DAT API
  only with written approval. No scraping or browser automation of load boards.

**Network layer (the "legion")**
- Broker scorecards from anonymized cross-firm signals (payment speed, fraud reports,
  detention behavior) with minimum cohort size and no firm-identifying data.
- Fraud alerts (hijacked MC, double-brokering reports) shared across firms.

**Platform operations**
- Admin/operator API (firms, health, queues, feature flags), rate limiting, observability
  (structured logs, metrics, traces), backups, data export and deletion per firm,
  background job system, idempotent webhooks, migrations/index management, seed/demo data.

## Decisions you must make (state each with the reason and the rejected alternatives)

- Service layout: one platform API service vs several; where it runs (it must not require
  opening the agent VM to the internet); how it shares data with the hermes-freight plugin.
- Auth design (token format, storage, rotation), and how carriers/drivers access their slice.
- Job/queue system on Atlas vs Redis vs other, and the scheduler.
- Object storage choice for documents.
- How the frontend gets real-time updates.
- How per-firm Atlas database users are created at scale (Admin API) and the free-tier limits
  that force an upgrade (state them; verify from MongoDB docs).

## Output (write these files; do not write application code)

1. `docs/plans/2026-10-25-manceps-platform-plan.md` containing:
   - Architecture diagram (ASCII), service boundaries, data ownership per collection.
   - Data model: every collection, fields, indexes, tenant scoping, retention.
   - API surface: every `/v1` route with method, auth/role, request/response summary.
   - Integration matrix: each vendor, endpoints used, auth, webhooks, credentials needed from
     the founder, failure behavior, and what is verified vs unverified (cite official docs URLs
     you actually opened; mark anything else UNVERIFIED).
   - Phases (ordered, each shippable): goal, files/modules, acceptance criteria as testable
     statements, dependencies, rough size. Phase 1 must deliver a usable core (auth, firms,
     carriers, brokers, imports, loads, approvals, OpenAPI) on its own.
   - Risks and legal guardrails mapped to the code that enforces them.
   - Exactly what the founder must provide (accounts, keys, approvals), per phase.
2. `docs/plans/execution-prompts/phase-NN-<name>.md`, one per phase: a self-contained prompt a
   build agent can execute without other context, embedding the relevant parts of
   META_PROMPT.md, the exact files to create/modify, the tests to write first, and the gate
   commands to run. Each prompt must end with the report format from META_PROMPT.md.

Be concrete: names of modules, collections, routes, env vars. Keep files under 500 lines each
(split the plan into `-plan-partN.md` files if needed). Report back with a short summary: the
phase list, the key decisions, and anything you could not verify.
