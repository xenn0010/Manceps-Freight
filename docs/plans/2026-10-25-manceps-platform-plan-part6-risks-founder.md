# Manceps platform plan, part 6: risks, guardrails, founder inputs

## 1. Legal guardrails mapped to enforcing code

Each guardrail has one module that enforces it and one test that proves it. Legal conclusions are **UNVERIFIED**; they
come from HANDOFF and the META rules, not from a lawyer. A transportation lawyer must review before public launch.

| ID | Rule | Enforcing code | Proving test |
|---|---|---|---|
| G1 | Bring-your-own-carrier only (no pool, no booking before a carrier) | `manceps_core.loads.machine` (booked needs `carrier_id` from this firm's `carriers`); no API takes a carrier id from another firm; plugin tool inventory has no "find a truck" tool | `test_booked_requires_carrier`, `test_no_cross_firm_carrier`, `test_agent_tool_inventory` |
| G2 | Consent before contact (TCPA) | `manceps_core.consent.can_contact` is the only gate; outbox delivery and `calls/outbound` call it; the ledger `consent_events` is the truth; STOP handled before routing | `test_outbox_blocks_without_consent` (zero vendor calls), `test_stop_precedes_routing`, `test_fmcsa_phone_not_consent` |
| G3 | AI disclosure on every call and first message | `outbox.render_first_contact` adds the disclosure; Vapi `firstMessage` pinned by `vapi_sync.py`; Vapi webhook rejects calls whose assistant lacks it | `test_first_message_discloses_ai`, `test_assistant_config_has_disclosure` |
| G4 | Human approval for money and contracts | approval kinds + action registry; no agent tool performs these actions; `load` writes past `evaluating` are API-owner-only through approvals | `test_tool_inventory_has_no_money_tools`, `test_accept_rate_only_via_approval` |
| G5 | Fail closed | lookups return `unknown`; policy crash blocks; missing credentials return 503; webhook with unverifiable credential is rejected; scanner down keeps documents `scanning` | `test_unknown_not_pass`, `test_policy_crash_blocks`, `test_not_configured_503`, `test_scan_down_not_available` |
| G6 | Tenant isolation | `TenantDb.for_principal`, `PlatformRepo` injects tenant, per-firm Atlas user for the agent, vendored core | generated cross-tenant matrix, `test_two_firm_events`, `test_scoped_link_cannot_cross` |
| G7 | No antitrust leakage | `manceps_core.network` is the only writer of `network_signals`; cohort >= 5; bucketed values; no tenant ids stored; never exposes counts | `test_signals_have_no_tenant_fields`, `test_cohort_floor`, `test_diff_attack_bucketed` |
| G8 | Platform never handles freight money between broker and carrier | no Stripe charge code path for load revenue; fee invoices only on the firm's connected account | `test_no_load_revenue_charge` (grep + route inventory) |
| G9 | No scraping or automation of load boards | `browser` toolset disabled in `managed-config.yaml`; adapters only talk to official APIs | `test_no_loadboard_automation` (repo scan) |
| G10 | Secrets never leak | Settings `SecretStr`; log redaction processor; API response models exclude secret fields; secrets encrypted at rest | `test_logs_redact`, `test_responses_have_no_secret_fields` |
| G11 | Untrusted content is data | inbound email, SMS, PDFs, call transcripts are wrapped in a delimited block in agent commands; injection fixtures change no state | `test_injection_fixtures_no_state_change` |

## 2. Risk register

| # | Risk | Likelihood / impact | Mitigation | Owner phase |
|---|---|---|---|---|
| R1 | Atlas Free cap of 500 collections reached at about 15 firms; throttling at 100 ops/s | high / high | upgrade before the 8th paying firm; `GET /v1/admin/health` shows collections used vs 500; worker poll backoff; SSE fan-out shares one poller per tenant | 1, 12 |
| R2 | 100 Atlas users per project caps per-firm users at about 90 | medium / medium | `atlas_shard`, second project, soft limit 90 | 12 |
| R3 | Operator Atlas credential in API/worker can read all firms | medium / high | secrets only on API host; rotate quarterly; IP allowlist; audit access; consider per-request least privilege later | 1, 12 |
| R4 | Hermes approval gate behavior over API is untested | medium / medium | design avoids it (D12); Phase 2 spike | 2 |
| R5 | Multi-profile gateway routing untested with 2+ profiles | medium / high | Phase 2 spike is the first task; fallback is one API port per profile | 2 |
| R6 | VM or Mac down means agent offline | high / medium | heartbeat + `agent_offline` 503; deterministic fallbacks for briefs and reminders; commands expire after `COMMAND_TTL=24h` with a visible status; long-term move to a Linux server (Oracle/other, per HANDOFF) | 2, 12 |
| R7 | Prompt injection through email, PDFs, SMS | high / high | G11; agent has no money tools; approvals show raw payload | 2, 10 |
| R8 | SMS registration delays (A2P/toll-free) block messaging launch | high / medium | start registration in Phase 1; web app and email work without SMS | 4 |
| R9 | TCPA liability from mistaken contact | medium / very high | G2, daily caps, quiet hours, ledger evidence, lawyer review of consent flow | 4, 5 |
| R10 | Gmail restricted-scope review blocks public Gmail | medium / medium | SMTP/IMAP baseline in Phase 4; Gmail optional | 6 |
| R11 | FMCSA 2023 dispatch-service guidance and brokering risk | medium / high | G1; lawyer on the dispatch agreement template and on any network feature | all |
| R12 | Stripe Connect and ACH risk for fee collection (disputes, returns) | medium / high | owner approval, mandate via hosted pages, alerts on `charge.dispute.created`; lawyer gate | 8 |
| R13 | Free-tier egress cap (10 GB per 7 days) with documents in Mongo | low / medium | documents are in R2, not Atlas | 3 |
| R14 | Founder bandwidth: 12 phases, many vendor approvals | high / medium | order puts approvals with long lead times (Twilio campaign, Motive, Samsara, Meta, Google) at the start of the phase before they are needed | all |
| R15 | Vendor facts drift (APIs change) | medium / low | every client has a contract test against recorded fixtures; unverified items listed in part 4 | all |
| R16 | Pyright strict on the plugin is not enforced today (basic) | low / low | Phase 2 raises the plugin to strict for new files only | 2 |

## 3. What I could not verify (full list)

1. Atlas Admin API create-user request shape (page did not render). Scoped users were never run in this repo.
2. Fly.io or any specific container host: pricing, static egress IPs, regions.
3. Whether Atlas Free change streams are enough (not needed; polling is the baseline).
4. ClamAV memory needs and Python client choice.
5. Cloudflare R2 pricing, egress fees, versioning or object lock.
6. Presigned PUT cannot enforce a size limit (assumed; avoided by uploading through the API).
7. Twilio: toll-free verification process, STOP keyword handling details, per-firm number approval, Verify docs (code works).
8. Meta WhatsApp: signature header name, template and 24-hour window rules, business verification, pricing.
9. Telegram Bot API webhook secret header name.
10. Vapi custom credential scheme (header vs HMAC) for server URLs; rate limits; outbound daily caps.
11. Gmail: restricted-scope review process and test-user limits.
12. Motive: token endpoint (search snippet only), refresh behavior, webhooks; Samsara webhooks.
13. DocuSeal webhook authentication scheme.
14. OTR Solutions: authentication, endpoints, access terms.
15. 123Loadboard partner API terms and specs (gated). DAT terms (from HANDOFF only).
16. Stripe Connect account type, charge type and regulatory fit for collecting a firm's dispatch fees.
17. Legal items: retention periods, calling hours, consent wording, state-specific rules (e.g. state mini-TCPA laws),
    dispatch-agreement text, whether the network features raise antitrust concerns, terms and privacy policy.
18. Hermes: behavior of the plugin `approve` directive over the API; multiplexed routing with 2+ profiles; event names are
    from the local docs for the pinned commit (not run).
19. The 73 passing plugin tests and live E2E claims come from HANDOFF; I did not run any tests (read-only planning task).
20. Windows or Linux differences: none expected; the Mac is Intel macOS 12 with a qemu Lima VM (4 GiB RAM). Capacity of that
    VM for many profiles is unmeasured.

## 4. Founder inputs, per phase

Legend: **Block** = the phase cannot pass its gate without it. **Lead** = start early, long wait.

### Before Phase 1 starts
- Decide the product domain and API host name (`api.<domain>`). Block.
- Choose the container host and create an account (Fly.io recommended, unverified). Block for deployment, not for tests.
- Apply to the 123Loadboard partner program. Lead.
- Start Twilio A2P 10DLC brand and campaign registration, or toll-free verification. Lead.
- Start the Meta business verification and WhatsApp Business setup. Lead.
- Find the transportation lawyer (dispatch agreement, consent text, terms, privacy policy). Lead.

### Phase 1
- Atlas operator connection string with `readWriteAnyDatabase`. Block.
- Twilio Verify credentials (already exist). Block for phone login.
- JWT signing key pair and `SECRETS_KEY` (generated by `scripts/gen_keys.py`; store in the host secret manager). Block.
- SMTP account and sending-domain DNS for magic links (optional, flag-off otherwise).
- Decision to upgrade Atlas off Free before real users (D10). Block for public signup.

### Phase 2
- Approve deploying the bridge to the Lima VM and restarting the gateway. Block.
- Confirm the pinned Hermes commit stays `1c0cd66774` (or approve a bump). Block.

### Phase 3
- R2 bucket + API token; ClamAV container allowance. Block.
- Lawyer: document retention periods. Lead.

### Phase 4
- Twilio number(s), messaging service, registered campaign. Block for live SMS (tests pass without).
- SMTP/IMAP credentials for the firm inbox. Block for live email.
- Lawyer: consent wording and AI-disclosure wording. Block for live sending.

### Phase 5
- Vapi private key, webhook credential, phone number ids (account already exists). Block for live calls.
- Lawyer: outbound-call policy (hours, state laws). Block for outbound.

### Phase 6
- Meta app, WhatsApp number, access token; Google Cloud project and OAuth consent screen; Telegram bot token. Block each.

### Phase 7
- Stripe account (test mode first), products, prices, plan limits, webhook endpoint. Block.

### Phase 8
- Lawyer sign-off on fee collection and Connect structure. Block.
- Stripe Connect enabled; firm onboarding flow test account. Block.
- Factor contact(s) for the email package; OTR account for the API path. Lead.

### Phase 9
- Samsara partner app credentials, Motive developer account approval, DocuSeal account and template. Block each.

### Phase 10
- 123Loadboard partner credentials (if approved). Optional.

### Phase 11
- Lawyer review of the network terms (opt-in language, antitrust). Block for launch.

### Phase 12
- Atlas Project Owner API key (`ATLAS_*`); a second Atlas project for sharding tests; backup destination (R2 bucket).
  Block.

## 5. Costs to expect (all **UNVERIFIED**, check before committing)

- Atlas dedicated tier (M10+), container host for 2 processes, R2 storage, Twilio numbers and messages, Vapi minutes,
  Stripe fees, Anthropic and DeepSeek tokens. The plan does not state numbers because none were verified.
