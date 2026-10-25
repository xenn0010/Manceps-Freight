# Manceps platform plan, part 3: API surface

Base path `/v1`. JSON. Tenant comes from the access token (never the path or body).

Auth codes used in the tables:

- **P** public (rate limited), **U** any signed-in user, **V** viewer or above, **D** dispatcher or above,
  **O** owner only, **S** scoped link (carrier or driver), **W** webhook (signature), **OP** operator token.
- Roles are ordered owner > dispatcher > viewer. "D" means dispatcher and owner.
- Every route also returns 401 (no or bad token), 403 (role too low), 404 (not found or other firm), 422 (validation),
  429 (rate limit). Only extra codes are listed.
- `Idem` = accepts `Idempotency-Key`. List routes take `cursor`, `limit` and return `{items, next_cursor}`.
- Operation id = `<resource>_<verb>`, e.g. `carriers_create`.
- Phase = the phase that ships the route (part 5).

## 1. Platform and meta

| Method path | Auth | Summary | Ph |
|---|---|---|---|
| GET `/healthz` | P | liveness | 1 |
| GET `/readyz` | P | Atlas ping; 503 if down | 1 |
| GET `/v1/openapi.json` | P | schema; same file as committed `openapi.json` | 1 |
| GET `/v1/me` | U | user, memberships, current role, feature flags | 1 |
| PATCH `/v1/me` | U | name, locale | 1 |

## 2. Auth and signup

| Method path | Auth | Request / response | Ph |
|---|---|---|---|
| POST `/v1/auth/otp/start` | P | `{phone}` -> `{sent:true}`; 503 if Twilio unset; limits as signup-api | 1 |
| POST `/v1/auth/otp/verify` | P | `{phone, code, firm_name?, accept_terms?}` -> existing user: tokens; new user with `firm_name` + `accept_terms:true`: creates user, queues signup, returns tokens + `signup_token` (202); 400 wrong code; 409 firm exists | 1 |
| POST `/v1/auth/magic-link/start` | P | `{email}` -> 202 always (no account enumeration) | 1 |
| POST `/v1/auth/magic-link/verify` | P | `{token}` -> tokens | 1 |
| POST `/v1/auth/refresh` | P | cookie or `{refresh_token}` -> new pair; reuse -> 401 and family revoked | 1 |
| POST `/v1/auth/logout` | U | revoke current session | 1 |
| POST `/v1/auth/logout-all` | U | revoke all sessions, bump `token_epoch` | 1 |
| POST `/v1/auth/switch-firm` | U | `{tenant_id}` (must be a membership) -> tokens | 1 |
| GET `/v1/signup/status/{token}` | P | pending, provisioning, ready, failed (same contract as today) | 1 |
| GET `/v1/sessions` | U | own sessions | 1 |
| DELETE `/v1/sessions/{id}` | U | revoke one | 1 |
| POST `/v1/auth/scoped/exchange` | P | `{link_token}` -> 1 h token with role C/S; 410 expired | 1 |

## 3. Firm, branding, team, audit

| Method path | Auth | Summary | Ph |
|---|---|---|---|
| GET `/v1/firm` | V | name, slug, status, plan, timezone, numbers, limits and usage | 1 |
| PATCH `/v1/firm` | O | name, timezone, address, MC number | 1 |
| GET `/v1/firm/provisioning` | V | provisioning state (reads signup row / firm status) | 1 |
| GET `/v1/firm/branding` / PATCH | V / O | logo doc id, colors, packet text | 4 |
| GET `/v1/firm/packet` / PUT | D | carrier-packet page content and visibility toggle | 4 |
| GET `/v1/public/packets/{slug}` | P | public page data: firm name, MC, branding, required documents list. No carriers, rates, loads | 4 |
| GET `/v1/members` | V | members and roles | 1 |
| POST `/v1/members/invitations` | O | `{email or phone, role}` -> invitation (token returned once) Idem | 1 |
| GET `/v1/members/invitations` | O | pending | 1 |
| DELETE `/v1/members/invitations/{id}` | O | revoke | 1 |
| POST `/v1/invitations/accept` | U | `{token}`; 410 expired | 1 |
| PATCH `/v1/members/{user_id}` | O | change role; cannot remove last owner (409) | 1 |
| DELETE `/v1/members/{user_id}` | O | remove; revokes that user's sessions for this firm | 1 |
| GET `/v1/audit` | O | filters: actor, ref, kind, date range | 1 |
| GET `/v1/firm/usage` | V | counts against plan limits | 7 |

## 4. Carriers, drivers, trucks, documents (per owner)

| Method path | Auth | Summary | Ph |
|---|---|---|---|
| GET `/v1/carriers` | V | filters: status, equipment, q; cursor | 1 |
| POST `/v1/carriers` | D | create; 409 duplicate phone; Idem | 1 |
| GET `/v1/carriers/{id}` | V | with consent summary, expiring docs, open loads | 1 |
| PATCH `/v1/carriers/{id}` | D | non-sensitive fields. Fee, floor, consent, agreement fields return 409 `approval_required` unless caller is O (owner edits directly; audited) | 1 |
| DELETE `/v1/carriers/{id}` | O | soft delete (offboard); blocked while loads are open (409) | 1 |
| POST `/v1/carriers/{id}/consent` | D | `{channel, method, evidence_doc_id?}` grants; writes ledger | 1 |
| DELETE `/v1/carriers/{id}/consent/{channel}` | D | revoke | 1 |
| POST `/v1/carriers/{id}/links` | D | create scoped link (returns URL token once) | 1 |
| DELETE `/v1/carriers/{id}/links/{link_id}` | D | revoke | 1 |
| GET/POST/PATCH/DELETE `/v1/drivers`, `/v1/drivers/{id}` | V/D | drivers CRUD | 1 |
| GET/POST/PATCH/DELETE `/v1/trucks`, `/v1/trucks/{id}` | V/D | trucks CRUD | 1 |
| POST `/v1/carriers/{id}/agreement/send` | D | start DocuSeal submission (503 if unset) | 9 |
| GET `/v1/carriers/{id}/documents` | V | documents with expiry state | 3 |

## 5. Brokers, contacts, reference

| Method path | Auth | Summary | Ph |
|---|---|---|---|
| GET `/v1/brokers` | V | firm's brokers; q, tag | 1 |
| POST `/v1/brokers` | D | by MC; pulls name from reference; Idem | 1 |
| GET `/v1/brokers/{mc}` | V | notes, tags, last check, firm stats; network scorecard when allowed (Phase 11) | 1 |
| PATCH `/v1/brokers/{mc}` | D | tags, payment terms | 1 |
| POST `/v1/brokers/{mc}/notes` | D | add note | 1 |
| POST `/v1/brokers/{mc}/check` | D | run `broker_check` logic; result stored; 503 if FMCSA key unset (verdict never `pass` on failure) | 1 |
| GET `/v1/brokers/{mc}/checks` | V | history | 1 |
| GET `/v1/reference/brokers` | V | FMCSA reference search (`q`, `mc`, `dot`) | 1 |
| GET/POST/PATCH/DELETE `/v1/contacts`, `/v1/contacts/{id}` | V/D | contacts CRM; tags; consent block | 1 |
| GET/POST/PATCH/DELETE `/v1/facilities`, `/v1/facilities/{id}` | V/D | shippers/facilities | 1 |
| GET `/v1/notes?ref_type=&ref_id=` | V | notes on any entity | 1 |
| POST `/v1/notes` | D | create | 1 |
| GET `/v1/tags` | V | tag vocabulary with counts | 1 |

## 6. Imports and exports

| Method path | Auth | Summary | Ph |
|---|---|---|---|
| GET `/v1/imports/templates/{entity}` | V | CSV template; entity: carriers, drivers, brokers, contacts, loads | 1 |
| POST `/v1/imports` | D | multipart: `entity`, `file` (.csv, .xlsx, .vcf for contacts; max 10 MB, 20,000 rows); Idem | 1 |
| GET `/v1/imports/{id}` | V | status, detected columns, suggested mapping, stats | 1 |
| PUT `/v1/imports/{id}/mapping` | D | `{column: field}`; re-validates | 1 |
| GET `/v1/imports/{id}/preview` | V | first 50 rows with action (create/update/skip/merge) and errors | 1 |
| GET `/v1/imports/{id}/report` | V | full validation report; CSV via `?format=csv` | 1 |
| POST `/v1/imports/{id}/commit` | D | `{duplicate_strategy: skip|update|merge}`; runs in a job; re-import of the same file hash is a no-op (idempotent) | 1 |
| POST `/v1/imports/{id}/undo` | D | within `IMPORT_UNDO_HOURS=24`; restores `before` snapshots, deletes created rows; 409 after window | 1 |
| GET `/v1/imports` | V | history | 1 |
| POST `/v1/exports` | D | `{entity, format: csv|xlsx, filters}` -> 202; Idem | 1 |
| GET `/v1/exports/{id}` | V | status, `download_url` (5 min) | 1 |

## 7. Loads

| Method path | Auth | Summary | Ph |
|---|---|---|---|
| GET `/v1/loads` | V | status, carrier, broker, date range; cursor | 1 |
| POST `/v1/loads` | D | create in `offered`; Idem | 1 |
| GET `/v1/loads/{id}` | V | with stops, events, docs, claims | 1 |
| PATCH `/v1/loads/{id}` | D | non-status fields | 1 |
| POST `/v1/loads/{id}/transition` | D | `{to, reason?}`; illegal -> 409 `illegal_transition`. `approved`/`booked` -> 409 `approval_required` | 1 |
| POST `/v1/loads/{id}/evaluate` | D | runs `load_evaluate` logic (miles, diesel, fee, net, floor); 503 pieces degrade to `unknown` | 1 |
| POST `/v1/loads/{id}/stops` / PATCH / DELETE | D | stop edits | 1 |
| GET `/v1/loads/{id}/events` | V | timeline | 1 |
| GET/POST `/v1/loads/{id}/claims` | V/D | detention, layover, TONU | 3 |
| POST `/v1/loads/{id}/documents` | D | attach document (see section 8) | 3 |
| GET `/v1/loads/board` | V | grouped by status for a kanban view | 1 |

## 8. Documents

| Method path | Auth | Summary | Ph |
|---|---|---|---|
| POST `/v1/documents` | D | multipart upload through API: PDF, PNG, JPG, XLSX, CSV; max 15 MB; magic-byte check; status `scanning` -> `available` or `quarantined`; 503 if R2 unset | 3 |
| GET `/v1/documents` | V | filter by owner_ref, kind, expiring_before | 3 |
| GET `/v1/documents/{id}` | V | metadata | 3 |
| GET `/v1/documents/{id}/download-url` | V | 5-minute presigned GET; audited | 3 |
| POST `/v1/documents/{id}/parse` | D | Claude parse (W-9, COI, Rate Con); returns structured fields; Idem | 3 |
| DELETE `/v1/documents/{id}` | D | soft delete; blocked inside retention (409) | 3 |

## 9. Approvals

| Method path | Auth | Summary | Ph |
|---|---|---|---|
| GET `/v1/approvals` | V | status, kind, subject; cursor | 1 |
| GET `/v1/approvals/{id}` | V | full payload, summary, risk, history | 1 |
| POST `/v1/approvals` | D | human-created proposal (same machinery; used by UI and tests) Idem | 1 |
| POST `/v1/approvals/{id}/decision` | D (O for `terms`, `bill_carrier`) | `{decision: approve|deny, note?, payload_hash}`; hash must match or 409 `payload_changed`; once decided -> 409 `already_decided`; Idem | 1 |
| GET `/v1/approvals/stats` | V | pending count, median decision time | 1 |

Approval kinds (Phase 1 ships the first four; the rest ship with their phase): `accept_rate`, `approve_ratecon`,
`carrier_terms_change`, `cancel_load`, `send_invoice` (8), `bill_carrier` (8), `outbound_call` (5), `esign_agreement` (9).

## 10. Agent, conversations, memory, schedules

| Method path | Auth | Summary | Ph |
|---|---|---|---|
| GET `/v1/agent/status` | V | bridge heartbeat age, queue depth, last run; `offline` when heartbeat older than 90 s | 2 |
| GET/PUT `/v1/agent/settings` | V / O | autonomy toggles, quiet hours, enabled jobs, daily message cap | 2 |
| POST `/v1/conversations` | D | create web conversation | 2 |
| GET `/v1/conversations` | V | list | 2 |
| GET `/v1/conversations/{id}/messages` | V | history | 2 |
| POST `/v1/conversations/{id}/messages` | D | `{text, attachments[]}` -> 202 `{message_id, command_id}`; 503 `agent_offline` when no heartbeat; Idem | 2 |
| GET `/v1/conversations/{id}/stream` | V | SSE of agent tokens and tool progress for the latest command; `Last-Event-ID` | 2 |
| POST `/v1/commands/{id}/cancel` | D | stop a run (bridge calls Hermes `stop`) | 2 |
| GET `/v1/memory/facts` | V | filter by entity | 2 |
| POST `/v1/memory/facts` | D | add a fact | 2 |
| PATCH/DELETE `/v1/memory/facts/{id}` | D | edit or forget | 2 |
| GET `/v1/schedules` | V | morning brief, triage, check calls, doc expiry, payment chase | 2 |
| PATCH `/v1/schedules/{kind}` | O | enable, time, timezone, quiet hours (plan limits enforced) | 2 |
| POST `/v1/schedules/{kind}/run` | D | run now (rate limited) | 2 |
| GET `/v1/briefs` | V | stored morning briefs | 2 |

## 11. Events

| Method path | Auth | Summary | Ph |
|---|---|---|---|
| GET `/v1/events/stream` | V | SSE per firm: `approval.created|decided|applied`, `message.created`, `load.status_changed`, `document.available|expiring`, `agent.status`, `import.progress`, `invoice.updated`; `: keepalive` every 15 s; `Last-Event-ID` resume | 1 |
| GET `/v1/events?after=<seq>` | V | catch-up for clients that cannot use SSE | 1 |

## 12. Messaging and voice

| Method path | Auth | Summary | Ph |
|---|---|---|---|
| GET `/v1/messages` | V | unified inbox; filter channel, unread, subject | 4 |
| POST `/v1/messages/send` | D | `{channel, to, body}`; consent check; 422 `no_consent` (blocked, not queued); Idem | 4 |
| GET `/v1/messages/threads/{id}` | V | thread | 4 |
| GET `/v1/endpoints` | V | firm numbers and inboxes | 4 |
| POST `/v1/endpoints/sms/assign` | O | buy or assign a Twilio number (503 if unset) | 4 |
| POST `/v1/endpoints/email/connect` | O | SMTP/IMAP credentials, validated by a test login | 4 |
| GET `/v1/integrations/gmail/connect` | O | OAuth start (URL) | 6 |
| GET `/v1/integrations/gmail/callback` | W | OAuth callback; state verified | 6 |
| POST `/v1/endpoints/whatsapp/connect` | O | WABA ids (embedded signup not planned) | 6 |
| GET `/v1/calls` | V | call log with summaries | 5 |
| POST `/v1/calls/outbound` | D | creates `outbound_call` approval unless pre-approved policy; consent + AI disclosure enforced | 5 |

## 13. Invoices, payments, billing

| Method path | Auth | Summary | Ph |
|---|---|---|---|
| GET/POST `/v1/invoices`, GET/PATCH `/v1/invoices/{id}` | V/D | CRUD; POST from delivered load with POD | 8 |
| POST `/v1/invoices/{id}/send` | D | creates `send_invoice` approval (or direct for owner if setting allows) | 8 |
| POST `/v1/invoices/{id}/payments` | D | record payment | 8 |
| GET `/v1/receivables/aging` | V | buckets 0-30, 31-60, 61-90, 90+ | 8 |
| POST `/v1/invoices/{id}/factor` | D | OTR API if connected, else email package to factor | 8 |
| POST `/v1/dispatch-fee-invoices` | O | build fee invoices for delivered loads; creates `bill_carrier` approval | 8 |
| GET `/v1/billing` | O | plan, trial, status, limits | 7 |
| POST `/v1/billing/checkout` | O | Stripe Checkout session URL | 7 |
| POST `/v1/billing/portal` | O | Stripe billing portal URL | 7 |
| POST `/v1/billing/connect/onboard` | O | Stripe Connect onboarding link for fee collection | 8 |

## 14. Integrations and webhooks

| Method path | Auth | Summary | Ph |
|---|---|---|---|
| GET `/v1/integrations` | V | each provider: `not_configured`, `disconnected`, `connected`, `error` | 1 |
| POST `/v1/integrations/{provider}/connect` | O | OAuth start for motive, samsara, gmail | 9 |
| DELETE `/v1/integrations/{provider}` | O | disconnect, delete stored tokens | 9 |
| POST `/v1/webhooks/twilio/sms` | W | `X-Twilio-Signature` | 4 |
| POST `/v1/webhooks/twilio/status` | W | delivery receipts | 4 |
| GET/POST `/v1/webhooks/whatsapp` | W | Meta verify challenge; `X-Hub-Signature-256` | 6 |
| POST `/v1/webhooks/telegram/{secret}` | W | secret path token + `X-Telegram-Bot-Api-Secret-Token` header (UNVERIFIED header name, check at build) | 6 |
| POST `/v1/webhooks/vapi` | W | server messages (`tool-calls`, `end-of-call-report`, `assistant-request`, `status-update`) | 5 |
| POST `/v1/webhooks/stripe` | W | `Stripe-Signature` | 7 |
| POST `/v1/webhooks/docuseal` | W | secret header (scheme UNVERIFIED) | 9 |
| POST `/v1/webhooks/motive`, `/v1/webhooks/samsara` | W | ELD events (scheme UNVERIFIED) | 9 |
| POST `/v1/webhooks/gmail` | W | Pub/Sub push (OIDC token verify) | 6 |
| POST `/v1/webhooks/email/inbound` | W | optional inbound parse provider; HMAC | 4 |

## 15. Carrier and driver portal (scoped links)

| Method path | Auth | Summary | Ph |
|---|---|---|---|
| GET `/v1/portal/me` | S | carrier name, firm name (Phase 1); required documents and expiries (Phase 3) | 1 |
| POST `/v1/portal/documents` | S | carrier uploads W-9, COI, authority; same scan pipeline | 3 |
| GET `/v1/portal/loads` | S | only that carrier's loads, no rates beyond their own net, no other carriers | 3 |
| POST `/v1/portal/loads/{id}/status` | S (driver) | arrived, loaded, departed, delivered + geo + POD upload | 3 |
| POST `/v1/portal/consent` | S | carrier grants or revokes SMS/WhatsApp/voice consent themself (evidence = timestamp, IP, UA) | 3 |
| GET/POST `/v1/portal/agreement` | S | view and e-sign the dispatch agreement | 9 |

## 16. Network layer

| Method path | Auth | Summary | Ph |
|---|---|---|---|
| GET `/v1/network/brokers/{mc}` | V | scorecard, only when cohort >= 5 firms; else `{insufficient_data:true}` | 11 |
| POST `/v1/network/reports` | D | fraud report (`hijacked_mc`, `double_brokering`) with evidence; reviewed before broadcast | 11 |
| GET `/v1/network/alerts` | V | active alerts matching brokers/carriers the firm touches | 11 |
| PUT `/v1/network/participation` | O | opt in or out of contributing signals (default opt-in, stated in terms) | 11 |

## 17. Operator (founder only)

Separate audience (`aud=operator`), separate signing key, IP allowlist optional. Never enabled for firm tokens.

| Method path | Auth | Summary | Ph |
|---|---|---|---|
| GET `/v1/admin/firms` / `{id}` | OP | firms, status, plan, usage, last agent heartbeat | 12 |
| POST `/v1/admin/firms/{id}/suspend` / `resume` | OP | status flip; suspended firms get 403 `firm_suspended` | 12 |
| GET `/v1/admin/queues` | OP | job counts by status/kind, oldest queued, dead letters | 12 |
| POST `/v1/admin/jobs/{id}/retry` | OP | requeue dead letter | 12 |
| GET/PUT `/v1/admin/flags` | OP | feature flags with per-firm overrides | 12 |
| GET `/v1/admin/health` | OP | Atlas, R2, bridge, vendor statuses, Atlas collection count vs limit | 12 |
| POST `/v1/admin/firms/{id}/export` | OP | start data export | 12 |
| POST `/v1/admin/firms/{id}/delete` | OP | schedule deletion (30-day grace) | 12 |
| POST `/v1/admin/seed` | OP | seed demo firm (refused when `ENV=production` unless flag) | 12 |

## 18. Route-count summary and the test matrix

About 190 operations. Every operation gets four tests by rule (META): happy path, validation error, auth failure,
wrong-tenant. The wrong-tenant test is generated from the OpenAPI schema (`tests/test_tenant_matrix.py`), so a new route
without a rule fails the build.
