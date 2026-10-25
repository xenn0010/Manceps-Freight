# Handoff: Hermes FreightOS project

Context handoff from a previous Claude Code session (2026-10-24). Read this first, then
`docs/gemini-conversation.txt` for the full original brainstorm with Gemini.

## 1. What we are building

An agentic "Shopify + personal agent" platform for **independent freight dispatchers**
(owner-operator trucks, 1 to 12 trucks per dispatcher).

- **The Firm (Shopify layer):** each dispatcher gets a firm in a box: name, dedicated phone line,
  agent inbox, carrier roster with signed per-carrier dispatch agreements, document vault
  (W-9, COI, authority), shareable carrier packet page, automatic dispatch-fee collection,
  installable skills.
- **The Agent (personal-agent layer):** one persistent AI dispatcher per firm with its own phone,
  inbox, browser, memory (carrier lanes and rate floors, broker habits), and 24/7 background jobs.
  The dispatcher talks to it on WhatsApp/Telegram.
- **Approval rules (trust layer):** agent acts alone on search, broker vetting, check calls, and
  negotiating up to the carrier's floor; one-tap approval to accept a rate or sign a Rate Con;
  money movement always needs approval; messaging non-consented contacts is blocked.

Example flow the user wants: "Start my firm Apex Freight, add Carlos 214-555-0199 dry van 8%"
-> agent texts agreement + ELD link -> finds reload -> calls brokers -> "[Approve $2,500]" ->
checks Rate Con against the call -> texts driver pickup -> handles check calls.

## 2. Decisions made

- **Base runtime: NousResearch/hermes-agent**, cloned at `./hermes-agent` (MIT, latest commit at
  clone time `1c0cd66774`). Not installed yet.
- **Do NOT fork/modify Hermes core.** Hermes's own rules (`hermes-agent/AGENTS.md`,
  `hermes-agent/plugins/AGENTS.md`): "Plugins never touch core"; new capability ships as skills,
  service-gated tools, or a **standalone plugin repo** (`~/.hermes/plugins/`). Third-party
  product integrations must be standalone plugins. So build a separate `hermes-freight` plugin
  repo plus skills.
- **VM / sandbox: Google Colab runtime**, reached with the `colab` CLI (not `colabctl`; its tunnel
  is dead). Runtime: Ubuntu 24.04.5, 2 CPU, 12 GB RAM, ~206 GB disk, Python 3.13.
- **Persistence plan:** Colab runtimes always die (idle timeout + max lifetime, ~12 h free,
  ~24 h Pro+). Keep Hermes data (`HERMES_HOME`) on Google Drive at
  `/content/drive/MyDrive/hermes-home`, plus a one-command rebuild script stored on Drive.
  Long training runs must checkpoint to Drive and auto-resume. No keep-alive hacks.
- **Always-on gateway:** Colab cannot host 24/7. Use the Mac (16 GB, Intel i7, macOS 12.7) for the
  always-on Hermes gateway; later Oracle Always Free (needs card) or another server.
- **Voice provider: Vapi** (`VAPI_API_KEY` is set in the env; account has a Twilio number and
  assistants). AgentPhone was dropped and its MCP server removed. No calls have been placed.

## 3. Build order (agreed)

1. Get Hermes running (model via `hermes model`, Telegram or WhatsApp connected).
2. Find one real test partner: one dispatcher + one owner-operator truck. Dispatch agreement
   template must come from a transportation lawyer, not from the Gemini text.
3. Build freight tools one at a time:
   1. Carrier profile (skill + memory)
   2. Broker check: FMCSA QCMobile API (free key), L&I bond filings via browser, RDAP domain age,
      DNS MX/SPF/DMARC
   3. Rate Con reader: PyMuPDF/pdfplumber + model vision; compare to agreed rate, flag penalties
   4. Load finder: Hermes browser on a board the dispatcher is logged into (check each board's
      ToS); also email load lists via inbox (Hermes `skills/email/himalaya`)
   5. Driver dispatch card via the Hermes gateway
   6. Broker caller via Vapi (hold-time grinding first, human closes)
   7. ELD (Samsara/Motive) later, mock data until a real truck
   8. Fee collection last (Stripe test mode / Plaid sandbox first)
4. Milestone: first real dispatch of one load with the agent doing back-office work.
5. Then automate calls, then money.

Free APIs list: FMCSA QCMobile, data.transportation.gov, RDAP, OpenRouteService (HGV profile),
Nominatim, US Census Geocoder, EIA (diesel prices), api.weather.gov, Telegram Bot API, Gmail/IMAP,
faster-whisper, Piper/Kokoro TTS, DocuSeal/Documenso, Stripe test mode, Plaid sandbox.
Hosted model needed (Mac too slow for local): Gemini free tier, Groq, OpenRouter, or Nous Portal.

## 4. Known problems in the Gemini plan (do not copy blindly)

- **Legal:** the shared truck pool, 4%/4% overflow, and "book the load first then text truckers"
  look like allocating traffic between carriers, i.e. brokering, which the 49 CFR 371.2
  bona fide agent exemption does not cover. Only the bring-your-own-carrier path is defensible.
  Needs a transportation lawyer.
- **TCPA:** public FMCSA phone numbers are not consent. AI voices count as "artificial" (FCC 2024).
  $500 to $1,500 per call/text. Agent must disclose it is an AI on every call.
- **Unverified "facts":** broker bond doubled to $150K in July 2026, 24-hour ELD edit lockout,
  75-mile personal conveyance cap. Verify against FMCSA before use.
- **"1% instant factoring"** is lending; needs capital or a factoring partner. Not near-zero risk.
- **Gemini's code is unsafe:** FMCSA lookup returns `verified: True, active: True` on error;
  voice swarm is `asyncio.sleep`; SMS is `print`; directory layout does not match the real repo.
- **"Meta Muse"** product details are unverified; treat "Muse" as the persistent personal-agent
  concept the user described.

## 5. Current state (end of previous session)

- Colab: **two CPU runtimes are running** (one was created by accident). Sessions:
  - Original, unnamed: `m-s-usc1a7-1nodjpbepq1s1`
  - Named `m-s-usc1a7-1nodjpbepq1s1` (runtime `m-s-kkb-usw1b2-3relojimbgogm`): the one in use.
  - Ask the user which to stop before stopping either.
- Connect non-interactively:
  `ssh -o ProxyCommand="colab ssh --proxy-mode -s %h" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null root@<SESSION_NAME> '<cmd>'`
  Note `-s` is a session **name**; an unknown name creates a new runtime.
  `~/.ssh/config` already has `Host colab` (session name `colab`, `--auth adc`, multiplexed);
  left unchanged.
- **Drive mount: FAILED (timed out).** `colab drivemount -s <session> /content/drive` needs the
  user to approve Google's consent screen ("Google Drive for desktop", full Drive scope) and then
  press Enter within ~2 minutes. The user must run it in their own terminal; the agent is not
  permitted to click the consent grant.
- Hermes is **not installed** anywhere yet. Dev setup is `source ./activate` from the repo root
  (Python 3.14 pin managed by Hermes "PM"; see `website/docs/reference/package-management.md`).
  The user interrupted the first install attempt; confirm before running.

### Update (2026-10-24, later session)

- The old runtime died (lifetime limit) and its install was lost, since Atlas blocked snapshots.
  Current session name: `hermes` (runtime `m-s-kkb-usc1b1-1z40spayaykje`, created 2026-10-24).
- **Hermes installed on the VM** at pinned commit `1c0cd66774` (`hermes --version` = v0.22.5+671).
  Model: `anthropic` / `claude-sonnet-5-5`, fallback `deepseek` / `deepseek-v4-flash`. Keys not set yet.
- **Drive dropped.** Drive consent is per VM (ephemeral), so it blocks automatic revival.
  Persistence is now **MongoDB Atlas GridFS** (db `hermes_persist`, bucket `snapshots`) via
  `colab-persist/` : `hermes_persist.py` (snapshot/restore/loop/list, tested end-to-end against
  Atlas), `rebuild.sh` (VM side), `colab-up.sh` (Mac side: pushes scripts + secrets, runs rebuild).
  The 3.6 GB install is not snapshotted (Atlas free tier is 512 MB); it is reinstalled from the pin.
- Atlas blocks Colab IPs (TLS alert). User chose to allow `0.0.0.0/0` in Atlas Network Access.
- Model keys go in `hermes-secrets.env` (ANTHROPIC_API_KEY, DEEPSEEK_API_KEY), never in chat.
- Messaging: **WhatsApp** (Baileys bridge, QR pairing, use a dedicated number). Gateway autostarts
  on rebuild when `~/.hermes/.autostart-gateway` exists.
- Hermes has no MongoDB backend for its own state (SQLite); Mongo also hosts the freight data
  for the `hermes-freight` plugin.

### Tenant isolation design (2026-10-24)

`hermes-freight/` plugin (56 tests passing, ruff + pyright basic clean; not yet run inside Hermes).
Tenant = one Hermes profile = one firm. Four layers:
1. Profile: memory, sessions, SOUL.md, WhatsApp pairing, `.env` are per profile (Hermes built-in).
2. `plugins.isolation: host`: per-profile plugin process holding only that profile's secrets.
3. `agent.disabled_toolsets: [terminal, file, code_execution]` because profiles do NOT sandbox the
   agent (docs: profiles/sandboxing). Layers 2 and 3 pinned in `/etc/hermes/config.yaml`
   (`deploy/managed-config.yaml`); enforcement is file permission, so production must run Hermes as
   non-root (Colab runs as root: not enforced there).
4. MongoDB: database `firm_<tenant>` per firm, plus Atlas user per firm with readWrite on only that
   DB (`deploy/provision_tenant.py`, needs Atlas Admin API key; `--shared-credentials` fallback).
Tenant id + URI come only from profile-scoped secrets (`FREIGHT_TENANT_ID`, `MONGODB_URI`), never
tool args; missing tenant fails closed. Freight memory: `brokers` collection (notes/tags per MC);
carrier lanes/floors on `carriers`. Vapi: live line +16198262038 in the login org (see
`hermes-freight/vapi/deployed.json`); Vapi-bought numbers have a daily outbound cap.

### Tools added (2026-10-24, evening)

- `ratecon_read` (Claude PDF + structured outputs, path locked to the profile's `cache/documents`;
  live-tested: caught a $50 short pay and both penalty clauses), `weather_alerts` (NWS),
  `load_evaluate` (miles via ORS HGV or given, EIA diesel, fee, carrier net, floor -> accept/counter/pass).
  73 tests, ruff + pyright clean. Socrata FMCSA insurance datasets are stale (2023-12-06): bond check
  stays manual.
- API research summary: no self-serve load board API (DAT ToS bans bots without written approval);
  FMCSA 2023 dispatch-service guidance is the main legal risk; Baileys WhatsApp violates WhatsApp ToS
  for business use.
- Colab VM `hermes` died after ~1 h; second install lost (Atlas still blocks Colab). Hermes is not
  running anywhere. Recommendation: run Hermes on the Mac (Atlas already allows the Mac IP).

### Local VM (2026-10-24, night) - current runtime

- Colab abandoned for runtime. Hermes now runs in a Lima VM on the Mac: `limactl shell hermes`
  (Ubuntu 24.04, qemu driver since macOS 12 has no `vz`, 2 CPU / 4 GiB / 30 GiB, `--mount-none` so
  the agent cannot read Mac files, non-root user). Atlas reachable (Mac public IP 50.175.245.62).
- Hermes pinned 1c0cd66774 installed; models set with no Hermes process running (Sonnet 5.5 main,
  DeepSeek V4 Pro fallback + aux). Keys in VM `~/.hermes/.env`: Anthropic, DeepSeek, FMCSA webKey,
  EIA, MONGODB_URI (operator). Missing: ORS_API_KEY, FREIGHT_CONTACT_EMAIL.
- `hermes-freight` copied to `~/.hermes/plugins/hermes-freight` and enabled; `hermes plugins doctor`:
  9 tools, 1 hook. E2E: agent called broker_check on C.H. Robinson (MC 384859) -> looks_ok, bond
  unknown, not saved (no tenant yet: fails closed). Dev deps moved to `requirements-dev.txt` because
  Hermes resolves plugin dependency groups (pytest pin conflict).
- Not done: provision first firm (needs firm id + dispatcher phone), SOUL.md, /etc/hermes managed
  config, WhatsApp pairing, gateway autostart, snapshot backups from the VM.

### First firm live (2026-10-24, night)

- `pilot-firm` provisioned in the Lima VM (shared Atlas credentials; db `firm_pilot_firm`;
  dispatcher phone +12403537825). Profile has SOUL.md, all API keys, plugin installed in the
  profile's own `plugins/` (profiles do not share plugins), isolation config, DeepSeek aux.
- `/etc/hermes/config.yaml` (root-owned) pins `plugins.isolation: host` + disabled terminal/file/
  code_execution; verified: `hermes config set plugins.isolation` refused, file not writable by user.
- E2E in `hermes -p pilot-firm chat -q`: carrier added; fee/floor change blocked by approval gate
  (non-interactive run, nothing saved); broker_check saved (looks_ok); load_evaluate used Google
  Routes (783 mi) + EIA diesel; weather_alerts returned 11 alerts. Atlas shows data only in
  firm_pilot_firm.
- Mileage: Google Routes API key works (DRIVE mode; Geocoding API needs billing, not used).
- Next: interactive approval test, WhatsApp pairing + gateway as a systemd service, backups.

## 6. Next steps

1. User re-runs the Drive mount and approves it.
2. Create `/content/drive/MyDrive/hermes-home` and a rebuild script on Drive (install Hermes,
   point `HERMES_HOME` at Drive, health check).
3. Install Hermes in the Colab runtime; verify `hermes --version` and `hermes doctor`.
4. Start the `hermes-freight` plugin repo with tool 1 (carrier profile) and tool 2 (broker check).

## 7. Working with this user

- Wants direct, honest answers; pushes for speed ("just do it").
- Confirm before installs, state changes, or anything outward-facing; the user has interrupted
  installs that were not explicitly requested.
- Secrets: `atlas-credentials.env` (MongoDB Atlas) sits in this folder in plain text. Never print
  it or commit it. Never put API keys in chat.
