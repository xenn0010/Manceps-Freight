# Manceps platform plan, part 2: data model

Conventions for every collection:

- `_id` is an ObjectId unless stated. API ids are the hex string. Prefixed public ids are not used.
- Firm collections live in `firm_<tenant>` and never carry `tenant_id` (the database is the scope).
  Platform collections carry `tenant_id` and every query adds it from the principal.
- All dates are tz-aware UTC. Money is integer cents. Phones are E.164 (`+1XXXXXXXXXX`).
- `created_at`, `updated_at`, `created_by` ({kind: user|agent|system|import|carrier_link, id}) on every mutable doc.
- "Writer" = the only code allowed to write the collection (via `manceps_core` repository functions).
- "Existing" marks collections already built. Changes to them are additive only (new fields have defaults on read).

## 1. `platform` database (cluster-wide)

| Collection | Key fields | Indexes | Writer | Retention |
|---|---|---|---|---|
| `signups` (existing) | `_id` token, `phone`, `firm_name`, `status`, `attempts`, `tenant_id`, `terms_version`, `client_ip`, **new** `user_id` | unique `phone`; unique sparse `tenant_id`; `(status, created_at)` | api, signup worker | 1 year |
| `signup_attempts` (existing) | `kind, key, at` | TTL on `at` (24 h); `(kind,key,at)` | api | 24 h |
| `users` | `phone`, `email`, `name`, `status`, `token_epoch`, `locale`, `created_at`, `last_login_at` | unique sparse `phone`; unique sparse `email` | api | until deletion request |
| `memberships` | `user_id`, `tenant_id`, `role` (owner, dispatcher, viewer), `status`, `invited_by` | unique `(user_id, tenant_id)`; `tenant_id` | api | with firm |
| `invitations` | `tenant_id`, `email`/`phone`, `role`, `token_hash`, `expires_at`, `accepted_at` | unique `token_hash`; TTL on `expires_at` +7 d | api | 14 days after expiry |
| `sessions` | `user_id`, `tenant_id`, `family_id`, `token_hash`, `rotated_to`, `expires_at`, `revoked_at`, `ua`, `ip` | unique `token_hash`; `(user_id, revoked_at)`; TTL on `expires_at` +30 d | api | 30 days |
| `magic_links` | `email`, `token_hash`, `expires_at`, `used_at` | unique `token_hash`; TTL | api | 1 hour |
| `scoped_links` | `tenant_id`, `subject` {type: carrier|driver, id}, `scopes[]`, `token_hash`, `expires_at`, `max_uses`, `uses`, `revoked_at` | unique `token_hash`; `(tenant_id, subject.id)` | api | expiry + 30 d |
| `firms` | `_id` = tenant_id string, `name`, `slug`, `status` (provisioning, active, past_due, suspended, deleting), `plan`, `timezone`, `atlas_shard`, `owner_user_id`, `branding`, `created_at`, `deleted_at` | unique `slug`; `status` | api, worker | until deletion |
| `endpoints` | `kind` (sms, whatsapp, voice, email, telegram), `address` (E.164, email, phone_number_id), `tenant_id`, `provider_ref`, `status` | unique `(kind, address)`; `tenant_id` | api, worker | with firm |
| `jobs` | `kind, tenant_id, payload, run_at, status, attempts, max_attempts, locked_until, locked_by, last_error, idempotency_key, result` | `(status, run_at)`; unique sparse `idempotency_key`; `tenant_id`; TTL 14 d on `finished_at` | api, worker | 14 days after finish |
| `schedules` | `tenant_id, kind, cron` or `every_seconds`, `timezone`, `next_run_at`, `enabled`, `quiet_hours`, `last_run_at` | `(enabled, next_run_at)`; unique `(tenant_id, kind)` | api, worker | with firm |
| `agent_commands` | `tenant_id, kind` (chat, inbound_message, scheduled, approval_result, system), `payload`, `status` (queued, claimed, running, done, failed, expired), `attempts`, `claimed_by`, `claimed_at`, `run_id`, `idempotency_key`, `created_at` | `(status, created_at)`; unique `idempotency_key`; `tenant_id` | api, worker, bridge | TTL 14 d |
| `agent_stream` | `command_id, tenant_id, seq, type, data` | `(command_id, seq)`; TTL 1 h | bridge | 1 hour |
| `bridge_heartbeat` | `bridge_id, at, profiles[], version, queue_depth` | TTL 10 min | bridge | 10 min |
| `webhook_events` | `provider, event_id, received_at, tenant_id?, raw_ref, status` | unique `(provider, event_id)`; TTL 30 d | api | 30 days |
| `idempotency_keys` | `tenant_id, key, route, body_hash, response, created_at` | unique `(tenant_id, key, route)`; TTL 24 h | api | 24 hours |
| `rate_limits` | `kind, key, at` | `(kind,key,at)`; TTL 24 h | api | 24 hours |
| `billing_accounts` | `tenant_id, stripe_customer_id, subscription_id, plan, status, trial_end, current_period_end, dunning_state, limits` | unique `tenant_id`; unique `stripe_customer_id` | api, worker | with firm + 7 years (tax) |
| `integrations` | `tenant_id, provider, status, scopes, secret_ref, connected_by, connected_at, last_sync_at, error` | unique `(tenant_id, provider)` | api, worker | with firm |
| `secrets` | `tenant_id, ref, ciphertext, key_id` (envelope-encrypted OAuth tokens; master key from env `SECRETS_KEY`) | unique `(tenant_id, ref)` | api, worker | with firm |
| `network_signals` | `broker_mc, signal` (payment_days, fraud_report, detention_paid), `value`, `cohort_hash` (salted, non-reversible), `week` | `(broker_mc, week)`; no tenant id stored | worker | 2 years |
| `network_alerts` | `kind` (hijacked_mc, double_brokering), `mc`, `evidence_ref`, `status`, `reported_count` | `(mc, kind)` | worker, operator | 2 years |
| `feature_flags` | `key, default, overrides {tenant_id: bool}` | unique `key` | operator | forever |
| `operator_audit` | `who, what, at, target_tenant` | `at` | api | 2 years |
| `schema_migrations` | `version, applied_at` | unique `version` | tooling | forever |

## 2. `freight_reference` database (existing, read-only for tenants)

- `brokers`: FMCSA broker census rows (from `deploy/load_reference.py`). Unchanged.
- `broker_bonds`: BMC-84/85 filings. Unchanged. Socrata insurance data is stale (2023-12-06 per HANDOFF), so bond status
  stays `unknown` unless the filing is present. This must remain fail-closed.
- Phase 9 adds a scheduled refresh job (`reference.sync`) that runs `load_reference.sync` logic from the worker.

## 3. `firm_<tenant>` database (one per firm)

Roughly 27 collections. Cost per firm on Atlas: about 27 collections and 70 indexes (see D10 in part 1).

### 3.1 People and companies

| Collection | Key fields | Indexes | Writer |
|---|---|---|---|
| `carriers` (existing) | `phone` (key), `name`, `company`, `mc_number`, `dot_number`, `equipment[]`, `dispatch_fee_pct`, `rate_floor_per_mile`, `home_base`, `preferred_lanes[]`, `avoid[]`, `notes`, `agreement_signed`, `consent {sms, voice, whatsapp, method, at}`; **new** `status` (onboarding, active, paused, offboarded), `email`, `authority_status`, `insurance_expires_at`, `agreement_doc_id`, `eld {provider, ref}`, `tags[]`, `deleted_at` | existing: unique `phone`, sparse `mc_number`; **new** `(status)`, `(insurance_expires_at)` | core repo (API, agent, import) |
| `drivers` | `carrier_id`, `name`, `phone`, `email`, `license_state`, `license_expires_at`, `consent {...}`, `status` | unique sparse `phone`; `carrier_id` | core repo |
| `trucks` | `carrier_id`, `unit`, `equipment`, `vin`, `plate`, `plate_state`, `max_weight_lbs`, `eld_vehicle_ref` | `carrier_id`; unique sparse `vin` | core repo |
| `brokers` (existing) | `mc_number` (unique), `company`, `notes[]`, `tags[]`, `last_check`; **new** `contacts[]` (embedded refs), `payment_terms`, `credit_notes`, `deleted_at` | existing unique `mc_number` | core repo |
| `broker_checks` (existing) | `mc_number, dot_number, checked_at, verdict, checks{}` | existing two indexes | agent tool, API |
| `contacts` | `kind` (broker_contact, shipper, receiver, facility, other), `name`, `company_ref` {type, id}, `phones[]`, `emails[]`, `tags[]`, `consent {...}`, `source` | `(kind)`; `phones`; `emails`; text index on `name, company` | core repo |
| `facilities` | `name`, `address`, `city`, `state`, `zip`, `geo`, `hours`, `detention_notes`, `contact_ids[]` | `geo` 2dsphere; `(state, city)` | core repo |
| `notes` | `ref {type, id}`, `text`, `author`, `pinned` | `(ref.type, ref.id, created_at)` | core repo |
| `consent_events` | `subject {type, id, phone}`, `channel`, `action` (granted, revoked), `method`, `evidence_ref`, `at`, `by` | `(subject.phone, channel, at)` append-only | `manceps_core.consent` only |

Consent rule: `carriers.consent` and `drivers.consent` are a cache. The ledger `consent_events` is the truth. A grant needs
`method` and a date. A STOP keyword writes a revoke event in the webhook handler before any other processing.

### 3.2 Loads

| Collection | Key fields | Indexes | Writer |
|---|---|---|---|
| `loads` | `ref` (human number, per-firm sequence), `status`, `carrier_id`, `driver_id`, `truck_id`, `broker_mc`, `broker_contact_id`, `source` (email, call, sms, board, manual, import), `stops[]` {seq, type pickup/delivery, facility_id, address, window_start, window_end, appt, arrived_at, departed_at}, `equipment`, `weight_lbs`, `commodity`, `loaded_miles`, `deadhead_miles`, `rate_cents`, `fuel_surcharge_cents`, `accessorials[]`, `dispatch_fee_cents`, `evaluation {verdict, net_cents, per_mile, at}`, `ratecon_doc_id`, `pod_doc_id`, `invoice_id`, `cancelled_reason`, `tonu_cents` | unique `ref`; `(status, updated_at)`; `(carrier_id, status)`; `(broker_mc)`; `(stops.window_start)` | core repo |
| `load_events` | `load_id`, `type`, `from`, `to`, `at`, `by`, `data` (append-only timeline) | `(load_id, at)` | core repo |
| `claims` | `load_id`, `kind` (detention, layover, tonu, lumper, damage), `amount_cents`, `status`, `evidence_doc_ids[]`, `submitted_at`, `paid_at` | `(load_id)`; `(status)` | core repo |
| `lane_stats` | `origin_state, dest_state, equipment, week, loads, avg_rate_per_mile_cents` (firm's own history only) | `(origin_state, dest_state, equipment, week)` | worker |

Load status machine (code enum + transition table in `manceps_core.loads`; illegal transitions are 409):

```
offered -> evaluating -> countered -> approved -> booked -> ratecon_received -> dispatched
-> at_pickup -> in_transit -> at_delivery -> delivered -> pod_received -> invoiced -> paid
Any pre-dispatched state -> cancelled.  dispatched/at_pickup -> tonu (truck ordered not used).
offered/evaluating/countered -> declined.
```

- `approved` and `booked` are set only by the approval action `accept_rate`, never by a direct API write.
- `booked` requires `carrier_id` (product rule 1). Creating a load without a carrier is allowed only in `offered`,
  `evaluating`, `countered`, `declined`.

### 3.3 Documents, invoices, payments

| Collection | Key fields | Indexes | Writer |
|---|---|---|---|
| `documents` | `kind` (w9, coi, authority, agreement, ratecon, pod, bol, invoice, lumper, other), `owner_ref {type, id}`, `filename`, `content_type`, `size`, `sha256`, `storage_key`, `status` (uploading, scanning, available, quarantined, deleted), `expires_at`, `parsed {...}`, `parse_status`, `version`, `supersedes` | `(owner_ref.type, owner_ref.id, kind)`; `(expires_at)`; unique sparse `(sha256, owner_ref.id, kind)` | API upload, worker |
| `invoices` | `number`, `kind` (broker_invoice, dispatch_fee), `load_ids[]`, `bill_to {type, id}`, `amount_cents`, `status` (draft, pending_approval, sent, partial, paid, void, overdue), `issued_at`, `due_at`, `factoring {provider, submitted_at, advance_cents, status}`, `stripe_invoice_id`, `doc_id` | unique `number`; `(status, due_at)` | core repo, worker |
| `payments` | `invoice_id`, `amount_cents`, `method`, `received_at`, `source` (manual, stripe, factor), `ref` | `(invoice_id)` | core repo |
| `reminders` | `kind` (doc_expiry, payment, check_call, pod), `ref`, `due_at`, `sent_at`, `channel`, `status` | `(status, due_at)` | worker |

### 3.4 Agent, approvals, messaging

| Collection | Key fields | Indexes | Writer |
|---|---|---|---|
| `approvals` | `kind`, `status` (pending, approved, denied, expired, applied, apply_failed), `subject_ref`, `payload`, `payload_hash`, `summary`, `risk` (money, contract, terms), `requested_by` {agent|user}, `requested_in` {conversation_id|command_id}, `decided_by`, `decided_at`, `note`, `applied_at`, `apply_result`, `expires_at` | `(status, created_at)`; `(subject_ref.type, subject_ref.id)`; TTL none | core approvals |
| `conversations` | `title`, `channel` (web, sms, whatsapp, telegram), `participant_ref`, `last_message_at`, `hermes_session_id` | `(last_message_at)` | API, bridge |
| `messages` | `conversation_id`, `direction`, `channel`, `role` (user, assistant, system, contact), `from`, `to`, `text`, `attachments[]` (document ids), `provider_id`, `status`, `command_id`, `consent_check {ok, reason}` | `(conversation_id, created_at)`; unique sparse `(channel, provider_id)` | API, worker, bridge |
| `outbox` | `channel`, `to`, `body`, `template`, `subject_ref`, `consent_check`, `status` (queued, blocked, sending, sent, delivered, failed), `approval_id?`, `provider_id`, `attempts`, `error`, `send_after` | `(status, send_after)`; unique sparse `idempotency_key` | core (API, agent) enqueue; worker sends |
| `memory_facts` | `entity {type, id}`, `text`, `kind` (preference, behavior, deal, lane, warning), `source` {tool, message_id, date}, `confidence`, `pinned`, `deleted_at` | `(entity.type, entity.id)`; text index on `text` | agent tools, API |
| `agent_settings` | single doc: `autonomy` {auto_vet_brokers, auto_check_calls, quiet_hours}, `enabled_jobs[]`, `daily_message_cap`, `language` | none | API |
| `calls` | `provider_call_id`, `direction`, `with {phone, ref}`, `started_at`, `duration_s`, `ended_reason`, `summary`, `structured {...}`, `transcript_doc_id`, `ai_disclosed`, `consent_ref` | unique `provider_call_id`; `(started_at)` | webhook handler |

### 3.5 Platform-in-firm utilities

| Collection | Key fields | Indexes | Writer |
|---|---|---|---|
| `imports` | `entity`, `source_filename`, `doc_id`, `status` (uploaded, mapped, previewed, committing, committed, undone, failed), `mapping {column->field}`, `stats {rows, valid, invalid, created, updated, skipped}`, `idempotency_hash`, `undo_until`, `created_by` | `(status, created_at)`; unique `idempotency_hash` | API, worker |
| `import_rows` | `import_id`, `row_no`, `raw`, `normalized`, `errors[]`, `action` (create, update, skip, merge), `target_id`, `before` (for undo) | `(import_id, row_no)`; TTL 30 d after import commit | worker |
| `exports` | `entity`, `format`, `filters`, `status`, `doc_id`, `expires_at` | TTL on `expires_at` | worker |
| `events` | `seq`, `type`, `ref`, `data` (small), `at` | unique `seq`; TTL 30 d on `at` | `manceps_core.events` only |
| `counters` | `_id` name, `value` | none | core (loads ref, events seq, invoice number) |
| `audit` (existing) | `event, at, who, request_id, session_id, ref, before_hash, after_hash` + free fields | existing `at` desc; **new** `(ref.type, ref.id, at)` | all writers |

## 4. Tenant scoping rules (enforced in code, tested)

1. `TenantDb.for_principal(principal)` is the only way the API gets a firm database. It reads `principal.tenant_id`.
   The function has no string parameter for a tenant. Request bodies and query strings are never read for it.
2. Platform collection queries go through `PlatformRepo`, which injects `tenant_id` into the filter.
3. A test enumerates every route in the OpenAPI schema and calls it with a token of firm A against a resource id from firm B.
   Expected result is 404 for every route (not 403, so ids are not confirmed).
4. The plugin keeps `tenant.current()`; `FREIGHT_TENANT_ID` and `MONGODB_URI` come only from profile secrets.
5. Network data (`network_signals`) never stores a tenant id, a carrier id, a rate, or a load id (part 6, guardrail G6).

## 5. Retention and deletion

- Firm deletion (Phase 12): export bundle to R2, 30-day grace, then drop `firm_<tenant>`, drop Atlas user, delete R2
  prefix `t/<tenant>/`, delete platform rows keyed by tenant (keep `billing_accounts` for tax retention, `operator_audit`).
- Documents default retention: carrier documents until the carrier is offboarded plus 3 years; load documents 7 years.
  These numbers are placeholders for a lawyer to confirm (**UNVERIFIED**, part 6).
- Audit records: never deleted while the firm exists.

## 6. Migrations and index management

- `manceps_core.indexes` holds the index spec per collection (name, keys, options). `ensure_indexes(db)` is idempotent and
  runs on firm creation, on worker start for all active firms (bounded concurrency), and via
  `backend/scripts/migrate.py --all`.
- Schema changes: additive fields are read with defaults. Breaking changes use `platform.schema_migrations` with a numbered
  function per version and a dry-run mode. The plugin's `store.ensure_indexes` is replaced by the core version in Phase 2.
- Index creation on Free tier counts toward the 500-collection cap only for collections, not indexes (verified limit
  wording is collections; indexes count toward the M10 recommended maximum).
