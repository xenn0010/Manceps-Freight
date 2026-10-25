# Manceps build meta prompt (the bar every build task must clear)

This file governs every agent or engineer that writes Manceps backend code. A task is done
only when every gate below passes with evidence. The planner copies the relevant parts into
each phase's execution prompt; nobody may lower the bar.

## Product in one paragraph

Manceps is "Shopify + a persistent personal agent" for independent US freight dispatchers
(1 to 12+ owner-operator trucks). A dispatcher opens a firm in minutes (the Shopify part) and
gets an always-on AI dispatcher named Manceps that remembers every carrier, broker, lane and
deal (the persistent-agent part). The human approves money and contracts; Manceps does the
back office. The backend must be complete enough that the only remaining work is a frontend.

## Non-negotiable product rules (encode them in code and tests, not only docs)

1. **Bring-your-own-carrier only.** A firm dispatches its own contracted carriers. No shared
   truck pool, no assigning one load across carriers of different firms, no booking a load
   before a carrier is chosen. The platform never handles freight money between shipper/broker
   and carrier; the dispatch fee is billed to the carrier separately.
2. **Consent before contact (TCPA).** No SMS, WhatsApp, or voice to a number without consent on
   file for that channel. Public FMCSA phone numbers are not consent. Every AI call and first
   message discloses that it is an AI.
3. **Human approval for money and contracts.** Accepting a rate, signing or approving a Rate Con,
   moving money, changing a carrier's fee/floor/consent/agreement: always an approval request.
4. **Fail closed.** A failed lookup is `unknown`, never `pass`. A policy crash blocks. Missing
   credentials disable a feature with a clear 503, never skip a check.
5. **Tenant isolation.** One firm = one MongoDB database (`firm_<tenant>`). The tenant comes from
   the authenticated principal, never from request bodies or model output. Cross-tenant reads
   are impossible by construction and covered by tests.
6. **No antitrust leakage.** Network features (broker scorecards, lane rates) only expose
   aggregated, anonymized data with a minimum cohort size. No firm ever sees another firm's
   rates, floors, carriers or loads.

## Engineering standards

- Python 3.11+, FastAPI, Pydantic v2, pymongo, uv for packaging, pytest, ruff, pyright **strict**.
- Type hints on every signature. Docstrings: one-line summary, then Args/Returns/Raises.
- Max 50 lines per function, 500 lines per file. No magic numbers: named constants or config.
- Config from environment through one typed settings object. Secrets never logged, never
  committed, never returned by an API.
- Logging through one structured logger; every request and agent action carries a request id
  and tenant id.
- No placeholders, no TODOs, no stubs, no `...` bodies, no commented-out code, no pseudo-code.
  An integration whose credentials are absent is still fully implemented: it reports
  "not configured" (503) and its client is tested against a fake transport.
- External HTTP calls: timeouts, bounded retries with backoff for idempotent calls, and a fake
  transport seam for tests. Webhooks verify signatures and are idempotent (dedupe by event id).
- Every write to firm data appends an audit record (who, what, when, request/session id).
- Imports at the top of files. Match the style of existing code in the repo.
- Don't change Hermes core (`hermes-agent/`). Agent features go in the `hermes-freight`
  plugin; platform features go in the platform service.

## API contract for the frontend

- REST under `/v1`, JSON, OpenAPI schema generated and committed (`openapi.json`), stable
  operation ids, typed request/response models, cursor pagination, consistent error envelope
  `{"error": {"code", "message", "details"}}`, idempotency keys on create/payment endpoints.
- Auth: phone OTP and email magic link -> short-lived access token + rotating refresh token;
  roles per firm (owner, dispatcher, viewer); carriers and drivers get scoped links, not
  accounts with firm access.
- Real-time: Server-Sent Events stream per firm for approvals, messages, load status changes.
- Every endpoint has tests for: happy path, validation error, auth failure, wrong-tenant access.

## Quality gates (all must pass, with the command output shown in the report)

1. `uv run pytest -q`: all pass, no skips without a written reason, no warnings from our code.
2. `uv run ruff check .`: clean.
3. `uv run pyright`: 0 errors in strict mode for platform code.
4. Coverage at least 90% lines for the platform package (`pytest --cov`).
5. `openapi.json` regenerated and matches the app.
6. Security self-check written in the report: authz on every route, tenant scoping on every
   query, input size limits, upload type/size limits, rate limits on auth and public routes,
   no secrets in logs or responses.
7. A short end-to-end test drives the main flow through the HTTP API against mongomock and fake
   integrations.
8. **Real database.** The same suite also passes against a real MongoDB (7.x) when
   `MONGODB_TEST_URI` is set (`uv run pytest -q -m "not mongomock_only"`). Tests that rely on
   real behavior mongomock lacks (atomic `find_one_and_update` under concurrency, TTL indexes,
   unique index conflicts, 2dsphere, text search) are marked `realdb` and run only there. CI
   runs this gate on every push with a MongoDB service container.
9. **Property-based tests** (Hypothesis) for every state machine, parser, normalizer and money
   calculation: no input may crash it or produce an invalid state.
10. **Independent review.** After each work package, a separate reviewer agent that receives only
   the code (not the builder's report) audits correctness, security, tenant isolation and
   failure handling. Every CONFIRMED finding is fixed with a regression test before the next
   package starts. The review findings and fixes are recorded in `docs/reviews/<wp>.md`.

## Production-readiness bar (top-notch, applies to the platform as a whole)

- **Deployable:** a Dockerfile (non-root, pinned base, healthcheck), a process definition for
  api and worker, and a documented deploy for the chosen host. Config only by environment.
- **CI on GitHub Actions:** all gates, real-MongoDB gate included, on every push and PR.
- **Observability:** structured logs, request and job metrics, error reporting hook (Sentry
  DSN optional, `not_configured` when unset), `/readyz` that checks the database and indexes.
- **Security:** a written threat model (`docs/security/threat-model.md`) kept current; OWASP
  API Top 10 addressed per route family; dependency audit (`uv run pip-audit` or equivalent) clean.
- **Performance:** list routes indexed (no collection scans on tenant data, checked with
  `explain` in the real-DB suite); SSE fan-out tested at 200 concurrent subscribers per firm.
- **Docs for the frontend:** `openapi.json` with examples on every request and response model,
  plus `docs/api/frontend-guide.md` (auth flow, token refresh, SSE, errors, pagination,
  idempotency).

## Report format (every task)

- **Done / partial / blocked**, then evidence: the exact gate outputs.
- Files changed. Decisions made and why. Anything not verified, said plainly.
