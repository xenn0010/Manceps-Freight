# One-shot plan: backend complete, manceps-app connected, Stripe billing, landing page

Date: 2026-10-25. Owner: backend session. Goal from the founder: finish the platform so the web app
(`manceps-app/`) runs on the real backend end to end, payments work through Stripe, the landing page
connects to sign-up and pricing, and everything is committed.

## Founder decisions this plan encodes

- **Booking and signing always need the owner's tap.** `accept_rate` and `approve_ratecon` are
  `always_human`; no autonomy setting, preset or agent action can bypass them.
- **4 agent personas** (default names Manceps, Arjun, Maya, Leo). The firm picks one and can rename it.
  Every outward call or message still says it is an AI.
- **Stripe:** the Aule Industrial Technologies Stripe account (keys copied from ARDA into the
  gitignored `backend/.env`; LIVE keys). Manceps gets its own products and prices in that account.
- **The real frontend is `manceps-app/`**, not the older Emergent `frontend/`.

## Work packages and order

| # | Package | Where | Depends on | State |
|---|---|---|---|---|
| A | WP1.5: loads, approvals (`always_human`), events SSE, `/v1/board`, `/v1/dashboard/summary`, loads import | `backend/` | Phase 1 WP1.1-1.4 | running |
| B1 | manceps-app wave 1: API client, sign-in, firm/profile, trucks, drivers, imports, empty states, personas, Demo tags | `manceps-app/` | existing API | running |
| C | Billing (Phase 7 brief): trial, plans, Checkout, Billing Portal, verified + deduped webhooks, limits (402), dunning | `backend/` | A | next |
| D | Agent bridge (Phase 2 brief, cut to what the app needs): chat API to the firm's Hermes profile, agent settings (persona, name, autonomy with locked book/sign), agent status, agent-raised approvals | `backend/` + `hermes-freight/` | A | next |
| B2 | manceps-app wave 2: loads sheet, needs-your-yes card, live SSE toasts, board, dashboard, permissions panel, persona settings, chat, billing page (Checkout + Portal), plan-limit messages | `manceps-app/` | A, C, D | after C and D |
| L | Landing page: pricing section matching the Stripe plans, CTAs into manceps-app sign-in | other session (mercepes-95) | C plan table | coordinated |
| R | Independent review of A, C, D (code only), fix every confirmed finding with a regression test | all | A, C, D | after each |
| G | Gates, live end-to-end smoke, commit and push | repo | all | last |

C and D both touch `backend/` routing, settings and `openapi.json`. They run one after the other, or in
separate git worktrees with `openapi.json` regenerated after the merge. Never two agents in the same tree.

## A. WP1.5 (spec: `execution-prompts/phase-01-core.md` 6.8 to 6.14)

- Load state machine with approval-only transitions into `approved` and `booked`; `booked` and later
  need a valid carrier of this firm.
- Approvals registry with payload hash, expiry, idempotent `apply`, and `always_human` kinds.
- Events stream per firm over SSE with a bounded queue, `Last-Event-ID` resume and keepalives.
- Read models for the dispatch screen: `/v1/board` (trucks with driver and current load, derived status
  and tone; position and HOS are null until ELD) and `/v1/dashboard/summary` (cents, firm timezone).
- `PATCH /v1/loads/{id}` for sheet cell edits refuses approval-gated fields with the planned 409 codes.

## C. Billing (spec: `execution-prompts/phase-07-billing.md`, plus the facts below)

- SDK: `stripe==13.2.0` (pinned API version `2025-10-29.clover`), installed with `uv add`.
- Settings: `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_IDS`
  (JSON plan to price id), `TRIAL_DAYS=14`, `DUNNING_GRACE_DAYS=7`, success and cancel URLs.
- `deploy`-style script `backend/scripts/stripe_setup.py`: creates or reuses the Manceps products and
  monthly prices (lookup keys `manceps_solo_monthly`, `manceps_team_monthly`, `manceps_fleet_monthly`),
  idempotent, dry run by default, `--apply` to write, prints the price ids for `STRIPE_PRICE_IDS`.
  Prices come from a founder-set table; nothing is created until the founder confirms the amounts.
- Webhook endpoint `/v1/webhooks/stripe`: `construct_event` with the raw body, 5-minute tolerance,
  dedupe by event id, re-fetch the subscription, converge regardless of event order.
- Registering the webhook endpoint in Stripe needs a public URL, so it happens at deploy time. Locally,
  `stripe listen --forward-to` supplies a temporary `whsec_` secret.
- Live-key safety: tests use a fake Stripe client only. The setup script refuses `--apply` with a live
  key unless `--live` is also passed.

## D. Agent bridge (spec: `execution-prompts/phase-02-agent-bridge.md`, scoped)

- The platform never calls into the VM. The bridge in the VM pulls `agent_commands` from MongoDB, runs
  them on the firm's Hermes profile (OpenAI-compatible API server, local to the VM), and writes
  replies back as messages and events (outbound connections only).
- `POST /v1/agent/chat`, `GET /v1/agent/conversations/{id}` with SSE deltas over the events stream,
  `GET /v1/agent/status` (heartbeat; offline after 90 s, chat returns 503 `agent_offline`).
- `GET/PUT /v1/agent/settings`: `persona_id` (one of 4), `name`, autonomy per action
  (`negotiate`, `brokers`, `drivers`, `reroute`: `auto|ask|off`; `book` and `sign`: always `ask`,
  any other value is 422), quiet hours. Owner-only for autonomy changes.
- The persona name flows into the Hermes profile SOUL as the display name, with "an AI dispatcher with
  Manceps" disclosure kept.

## B2. manceps-app wave 2

Replace each remaining `src/demo/` surface with its endpoint: loads sheet (list, inline PATCH,
create, import), needs-your-yes card (approvals list and decide), toasts from SSE, board and map
markers from `/v1/board`, dashboard from `/v1/dashboard/summary`, permissions panel from agent
settings (book and sign locked), persona picker and rename, chat from the agent bridge, and a Billing
tab (plan, trial days left, Checkout, Portal, `plan_limit_reached` messages). Agent calls stay a demo
until outbound voice (Phase 5) ships, still tagged Demo.

## Gates (every package)

- Backend: pytest with coverage >= 90%, real-MongoDB suite, ruff, pyright strict, `openapi.json` and
  vendored core checks, plugin suite.
- manceps-app: `npm run typecheck`, `npm run build`, `npm test`.
- Independent review (code only) after A, C and D; findings recorded in `docs/reviews/`.
- Final live smoke: local API + worker + VM signup worker on the VM MongoDB; sign up in the browser,
  add a truck and driver, import a sheet, create a load, approve it from the card, see the SSE update,
  open Checkout in Stripe test of the flow up to the hosted page (no real payment).

## Commit

One commit per package, authored as xenn0010, no Claude co-author trailer, secret scan before each
commit, `manceps-app/` added to git (its `node_modules/` and `dist/` stay ignored), pushed to
`manceps` (`xenn0010/Manceps-Freight`) main.

## Founder inputs still needed

- **Prices** for solo, team and fleet (monthly, USD), and their limits (carriers, members).
- **Webhook URL** at deploy time (needs a host for the backend).
- **Avatar images** for the 3 personas that don't have one yet.
