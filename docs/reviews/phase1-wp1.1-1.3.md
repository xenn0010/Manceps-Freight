# Independent review: Phase 1, WP1.1 to WP1.3 (backend/)

Reviewer: independent agent, code only (no builder report). Date: 2026-10-25.
Scope: `backend/manceps_core`, `manceps_api`, `manceps_worker`, `scripts`, `tests`, checked against
`docs/agents/META_PROMPT.md` and section 6 of `docs/plans/execution-prompts/phase-01-core.md`.

## Bottom line

- **16 findings.** 2 high, 10 medium, 4 low.
- **12 CONFIRMED** (10 reproduced by a throwaway test, 2 traced line by line), **4 PLAUSIBLE**.
- **Tenant isolation held** everywhere I looked. No path from firm A to firm B data was found.
- The worst problems are **product-rule breaks**: consent follows a carrier to a new phone number, and broker
  vetting can say `looks_ok` for an identity it never checked.

Baseline: `uv run --offline pytest -q` gives `220 passed in 13.76s`.

Proof file (not in the repo):
`/private/tmp/claude-501/-Users-yeabsirateshome-Documents-Mercepes/62d8fa9a-a13d-4436-bd45-b9a80bf280c5/scratchpad/test_review_proofs.py`.
Run it from `backend/` with
`PYTHONPATH=tests uv run --offline pytest -q -p conftest --rootdir=. -c pyproject.toml <that file>`.
Result: `10 passed`. Every passing proof asserts the **wrong** behavior.

## Findings, ranked

### F1. Consent stays on a carrier after its phone number changes (TCPA)

- **Severity:** high. **Verdict:** CONFIRMED (proof `test_p4`).
- **Where:** `manceps_core/repo/carriers.py:31` (`phone` is not a sensitive field), `:291-315` (`update_carrier`);
  `manceps_core/repo/consent.py:33-51` (the cache ignores `subject.phone`).
- **Scenario:** a dispatcher grants SMS consent for carrier X at `+12145550300`. Then the dispatcher sends
  `PATCH /v1/carriers/X {"phone": "(469) 555-0111"}`. The carrier document now holds `phone=+14695550111` with
  `consent.sms=true`. The plugin's consent check (`hermes-freight/carriers.py:188`, lookup by phone) will say the new
  number has consent. The ledger shows consent was only given for the old number.
- **Rule broken:** META rule 2. Consent belongs to a number and a channel, not to a document.
- **Minimal fix:** when `phone` changes in `update_carrier`, the same repo call must clear the consent cache. The
  simplest way is to append `revoked` ledger rows for every granted channel with method
  `"phone number changed"`, then rebuild the cache. Also make `cache_from_events` count only rows whose
  `subject.phone` equals the subject's current phone. Apply the same rule to drivers. Add a regression test.

### F2. Broker vetting checks a DOT the caller supplies, not the broker's MC

- **Severity:** high. **Verdict:** CONFIRMED (proof `test_p7`).
- **Where:** `manceps_api/routes/brokers.py:348`; `manceps_core/brokers/check.py:144-166` and `:188-213`;
  `manceps_core/brokers/reference.py:58-66`.
- **Scenario:** a broker with MC `999999` is checked with body `{"dot_number": "777"}`. DOT 777 is a legitimate
  broker. The DOT can also be stored earlier via `PATCH /v1/brokers/{mc}`.
  - The FMCSA lookup by DOT returns DOT 777's record, so operating status and authority both pass.
  - The bond query is `$or: [{mc_number: 999999}, {dot_number: 777}]`, so DOT 777's bond passes.
  - The verdict is `looks_ok` for MC 999999. Nothing checks that the FMCSA record's docket matches the MC.
- **Why it matters:** the classic double-brokering scam is exactly this: a fake MC presented with a real broker's DOT.
  The check should fail closed here, but it passes.
- **Minimal fix:** when both MC and DOT are known, run the docket lookup for the MC as well, and require the docket
  record's `dotNumber` to equal the DOT. If they disagree, mark `fmcsa_operating` and `broker_authority` as `fail`
  with the detail "MC and DOT belong to different entities". Match the bond on the resolved pair, not with `$or`.
  Add a regression test.

### F3. A failed lookup does not lower the verdict

- **Severity:** medium. **Verdict:** CONFIRMED (proof `test_p7`).
- **Where:** `manceps_core/brokers/check.py:284-298` (`verdict`).
- **Scenario:** RDAP is down and DNS fails, so `domain_age=unknown` and `email_dns=unknown`. The three critical
  checks pass, so the verdict is still `looks_ok`. An unparseable email gives `email_domain=unknown`, also
  `looks_ok`.
- **Rule broken:** section 6.6 says failures return `review` or `do_not_book` with `unknown` items, never a pass.
  META rule 4 says a failed lookup is `unknown`, never `pass`.
- **Minimal fix:** in `verdict`, return `review` when any check is `unknown`. Only allow `looks_ok` when every check
  that ran is `pass`.

### F4. A refresh that races `logout-all`, logout or reuse revocation survives it

- **Severity:** medium. **Verdict:** CONFIRMED (proof `test_p5`, which interleaves deterministically).
- **Where:** `manceps_api/auth/sessions.py:125-139` (`rotate`).
- **Scenario:**
  1. `rotate` reads the current row while it is not yet revoked.
  2. `logout-all` runs: it bumps the epoch and revokes every session.
  3. `rotate` inserts the successor, which is not revoked, and the claim succeeds because its filter is only
     `rotated_to: None`.
  4. `auth_refresh` reads the user after the epoch bump, so the new access token carries the new epoch.
  - The attacker keeps a live session plus a refresh token that rotates again.
  - A thief who refreshes in a tight loop can therefore beat the victim's `logout-all`. `revoke_family` on
    reuse detection has the same gap.
- **Minimal fix:** make the claim conditional: `{"_id": current_id, "rotated_to": None, "revoked_at": None}`. Keep
  inserting the successor before the claim. Then a revoke that lands before the claim makes the claim fail; on
  failure delete the successor and return 401. A revoke that lands after the claim also revokes the successor,
  which already exists. Add a regression test.

### F5. Infinity or NaN input writes the record, then fails the audit with a 500

- **Severity:** medium. **Verdict:** CONFIRMED (proofs `test_p2` and `test_p3`).
- **Where:**
  - `manceps_core/repo/store.py:156-164` and `:243-252`: the write happens first, the audit after.
  - `manceps_core/hashing.py:55` uses `allow_nan=False`.
  - `manceps_core/repo/carriers.py:96-117`: `_floor` and `_number` reject NaN but accept `inf`.
  - `manceps_core/repo/contacts.py:65-67` and `:86`: `abs(nan) > 90` is False, so NaN passes.
  - The pydantic `float` fields at `routes/carriers.py:75-76` and `routes/contacts.py:87-88` allow inf and NaN.
- **Scenario A (carrier):** the owner posts `{"rate_floor_per_mile": 1e999}`, which is valid JSON and parses to
  `inf`.
  - The carrier is stored with an infinite floor and **no audit row**, and the caller gets a 500.
  - After that, **every** `PATCH` of that carrier by anyone also writes and returns 500 with no audit row,
    because the stored `before` state has `inf` in it.
  - `GET` renders the floor as `null`, which hides the bad value.
- **Scenario B (facility):** a dispatcher posts `{"location": {"lat": NaN, "lng": 0}}`. The result is 500 and an
  unaudited row on mongomock. On a real MongoDB the 2dsphere index rejects the insert, which is still an unhandled
  500.
- **Rule broken:** "every write to firm data appends an audit record", plus "no 500 on bad input".
- **Minimal fix:**
  - Reject non-finite numbers in `_number` and `_coordinate` with `math.isfinite`.
  - Set `allow_inf_nan=False` on request models: a `ConfigDict` on `StrictModel` covers every route.
  - Defense in depth: compute the audit hashes before the write, so a hash failure aborts before anything is
    stored.

### F6. OTP verify reveals which phones have accounts, with no rate limit

- **Severity:** medium. **Verdict:** CONFIRMED (proof `test_p1`).
- **Where:** `manceps_api/routes/auth_otp.py:133-137`.
- **Scenario:** `POST /v1/auth/otp/verify {"phone": X, "code": "000000"}` with no signup fields.
  - An unknown phone gets 422 `signup_details_required`.
  - A registered phone gets 400 `invalid_code`.
  - The 422 is returned before `enforce(...)`, so unknown phones are never rate limited. 30 calls in a row all
    return 422.
  - The result: an unauthenticated, unthrottled oracle for which dispatchers use Manceps.
- **Minimal fix:**
  - Apply a per-IP limit and the per-phone check limit before the user lookup.
  - Check the code before deciding between sign-in and signup.
  - Return `signup_details_required` only after the code is approved. Twilio has already proven phone ownership at
    that point.

### F7. Removing or demoting the last owner is a check-then-act race

- **Severity:** medium. **Verdict:** CONFIRMED by line trace (proof `test_p6` replays the interleaving).
- **Where:** `manceps_api/routes/members.py:353-367` (`_keep_an_owner`), `:403-407`, `:429-432`.
- **Scenario:** firm A has two owners, O1 and O2. At the same time, O1 sends `DELETE /v1/members/O2` and O2 sends
  `DELETE /v1/members/O1`. Both see `count(owners) == 2`, both pass, and both delete. The firm now has zero owners,
  so nobody can manage members, change terms or read the audit log. The same race exists for two concurrent
  demotions.
- **Minimal fix:** make the change and the check atomic. One option is a per-firm counter of owners updated with a
  conditional `$inc` that has a `{owners: {$gt: 1}}` guard. Another is a transaction where the count is re-read
  after the write, and the write is rolled back (role restored or row re-inserted) when the count is 0.

### F8. Invitation email matching uses an email nobody verified

- **Severity:** medium. **Verdict:** CONFIRMED (proof `test_p8`).
- **Where:** `manceps_api/routes/me.py:153-161` (`PATCH /v1/me` sets any unclaimed email);
  `manceps_api/routes/members.py:276-287` (`_identity_matches`).
- **Scenario:** an owner invites `alice@corp.com` as a dispatcher. Mallory gets the token, for example from a
  forwarded email, a shared chat, a log, or a shoulder-surfed screen. Mallory signs up with her own phone, sets
  `email=alice@corp.com` on `/v1/me`, and accepts. The rule "the email must match" adds no protection.
  - The same unverified email also lets Mallory squat Alice's address. Alice can then never set it, because the
    unique index blocks her.
  - Magic-link mails for Mallory's account would go to Alice's inbox, a login-CSRF vector.
- **Minimal fix:** store `email_verified_at`, and set it only through a magic-link round trip to that address.
  Match invitations and allow magic-link sign-in only on a verified email. Until that exists, refuse email-only
  invitations, or require the phone to match.

### F9. Rate limits trust the attacker-controlled first `X-Forwarded-For` hop

- **Severity:** medium (only with `TRUST_PROXY=1`). **Verdict:** CONFIRMED (proof `test_p11`).
- **Where:** `manceps_api/requestinfo.py:22-24`.
- **Scenario:** standard proxies (nginx `$proxy_add_x_forwarded_for`, ALB, Fly, Render) **append** the real client
  IP. The code takes the **first** entry, which the client wrote. The proof sends 25 OTP sends from one real IP,
  each with a fake first hop. All 25 return 202, but the per-IP limit is 10 per hour.
  - Every per-IP limit can be bypassed this way: OTP send, magic-link start and verify, refresh, scoped exchange,
    and signup status.
  - This opens SMS-pumping toll fraud against Twilio across many phones.
- **Minimal fix:** take the right-most hop, or the hop at a configured `TRUSTED_PROXY_HOPS` index from the right. Or
  rely on uvicorn's `proxy_headers` with `forwarded_allow_ips` and use `request.client.host`.

### F10. No request body size limit

- **Severity:** medium. **Verdict:** CONFIRMED by line trace. There is no body-limit middleware in
  `manceps_api/app.py:83-97`, and grep finds no `content-length` or body-limit code.
- **Where:** app wiring; `manceps_api/idempotency.py:167` (`await request.body()`); FastAPI reads JSON bodies
  whole.
- **Scenario:** an unauthenticated `POST /v1/auth/otp/start` with a body of several hundred MB is buffered and
  parsed in memory before pydantic's per-field `max_length` runs. A few parallel requests can exhaust worker
  memory.
- **Rule broken:** META quality gate 6 ("input size limits").
- **Minimal fix:** add a pure-ASGI middleware that rejects a `Content-Length` over a configured limit (for example
  64 KiB for JSON routes) with 413, and counts streamed bytes for chunked bodies. Imports in WP1.4 get their own
  higher limit.

### F11. A dispatcher can grant consent directly, with no owner and no approval

- **Severity:** medium. **Verdict:** CONFIRMED behavior. Whether it is a defect depends on how the spec is read.
- **Where:** `manceps_api/routes/carrier_access.py:59-78` (`FirmDispatcher`).
- **Scenario:** a dispatcher sends `POST /v1/carriers/X/consent {"channel": "sms", "method": "x"}`. SMS consent is
  recorded right away.
  - META rule 3 says "changing a carrier's ... consent ...: always an approval request".
  - `SENSITIVE_CARRIER_FIELDS` includes `consent`, yet this route bypasses the approval rule that applies to
    `PATCH`.
- **Minimal fix:** for `action=granted`, require the owner, or return 409 `approval_required` with
  `approval_kind="carrier_terms_change"` for dispatchers, the same as in `check_terms`. Revokes can stay open to
  dispatchers, because revoking fails safe. If the spec intends dispatchers to grant, write that down explicitly in
  the threat model.

### F12. Concurrent consent writes can leave a stale cache

- **Severity:** medium. **Verdict:** PLAUSIBLE (a narrow race, traced but not reproduced).
- **Where:** `manceps_core/repo/consent.py:114-115` and `:68-82`.
- **Scenario:**
  1. Request A appends a `granted` row and reads a ledger that holds only that row.
  2. Request B appends a `revoked` row, reads both rows, and writes the cache `sms=false`.
  3. A writes its older cache last: `sms=true`.
  - The ledger says revoked, but the cache that the plugin reads says granted.
  - This fails open on TCPA, until `rebuild_cache` runs, and nothing schedules it.
- **Minimal fix:** write the cache with a compare-and-set on the newest ledger row. Filter on
  `{"$or": [{"consent.recorded_at": {"$lte": latest_at}}, {"consent": {"$exists": False}}]}`, or recompute in a loop
  until the ledger's newest `_id` is unchanged. Alternatively, have the plugin read the ledger.

### F13. Idempotency records are scoped to the firm, not the user

- **Severity:** low. **Verdict:** CONFIRMED (proof `test_p10`).
- **Where:** `manceps_api/idempotency.py:124`; `manceps_core/indexes.py:126`.
- **Scenario:** an owner and a dispatcher of the same firm send the same `Idempotency-Key` with the same body to
  `POST /v1/carriers`. The dispatcher gets the owner's stored response with `Idempotency-Replayed: true`.
  - The data never leaves the firm, and tokens are stripped before saving.
  - But one user can be served another user's response, and the dispatcher's request is silently dropped.
- **Minimal fix:** add `user_id` to the record and to the unique index: `(tenant_id, user_id, key, route)`.

### F14. Portal tokens ignore firm status, and carrier offboarding leaves links live

- **Severity:** low. **Verdict:** CONFIRMED by line trace.
- **Where:** `manceps_api/auth/principal.py:220-228`; `manceps_core/repo/carriers.py:332-352`.
- **Scenario:**
  - A suspended firm's portal links still exchange and authenticate. Firm routes return 403 `firm_suspended`.
  - Offboarding a carrier does not revoke its `scoped_links`. In this phase that only yields a 404 on
    `/v1/portal/me`. Phase 3 portal routes will inherit the gap.
- **Minimal fix:**
  - In `portal_principal` and `auth_scoped_exchange`, require the firm to be active.
  - In `delete_carrier`, revoke the carrier's live links through `PlatformRepo`.

### F15. `firm_activate` can make a new signup owner of an existing firm

- **Severity:** low. **Verdict:** PLAUSIBLE. It depends on a firm row existing that no signup reserved.
- **Where:** `manceps_worker/firm_activate.py:77-111`.
- **Scenario:** when `firms[_id=tenant_id]` already exists, the `$setOnInsert` upsert does nothing. The membership
  upsert still gives the signup's user an `owner` membership in that existing firm. The only guard against
  collisions is the provisioner's `signups.tenant_id` index plus a filesystem check (`taken`). Any firm row created
  another way, for example by an operator or a restore, can be taken over.
- **Minimal fix:** after the upsert, when `created` is False, require `firm["signup_id"] == signup["_id"]`.
  Otherwise raise `ValueError`, so the runner tags it and does not grant membership.

### F16. The broker `notes` array grows without bound

- **Severity:** low. **Verdict:** CONFIRMED by line trace.
- **Where:** `manceps_core/repo/brokers.py:162-163`.
- **Scenario:** `$push` with no `$slice`. Each 1000-character note adds about 1.1 KB, so roughly 14k notes reach the
  16 MB document limit. After that every write to the broker fails with a 500. Every list or get call also renders
  the whole array.
- **Minimal fix:** `$push: {notes: {$each: [note], $slice: -N}}` with a named cap, or move overflow notes into the
  `notes` collection.

## Areas checked and found sound

- **Tenant isolation by construction.**
  - `TenantDb.for_principal` is the only path to a firm database, and the tenant regex blocks underscore
    collisions.
  - Every firm-data route uses `firm_db(request, principal)`. Ids are parsed and looked up inside that database
    only.
  - The only raw `client[...]` or `platform_db[...]` uses are the reference database, users, firms and scoped-link
    lookups by an unguessable id.
  - `PlatformRepo` injects `tenant_id` into filters and inserts, rejects foreign `tenant_id` anywhere in the
    filter, and blocks tenant changes in updates.
  - Invitations, scoped links, memberships and idempotency all go through it.
  - Cross-firm ids in `carrier_id`, `contact_ids` and note `ref` are validated inside the caller's firm database.
- **JWT verification.**
  - The algorithm is pinned to EdDSA, and the `kid` must be in the keyring.
  - `aud`, `iss`, `exp` (against the app clock), `iat` and `sid` are required.
  - Claim types are checked, and an invalid `tid` cannot form a `Principal`.
  - Portal tokens are rejected on firm routes and firm tokens on the portal route, because each verifies its own
    audience.
  - Every request reads the session and user: revoked session, wrong user, inactive user and stale epoch all
    return 401. The firm role comes from the live membership, not the token.
- **Refresh rotation and reuse.**
  - The claim is conditional, and a reused token revokes its family.
  - Concurrent use of the same token revokes the winner's successor too, because the successor is inserted before
    the claim. (F4 is a separate race against revocation.)
- **Cookie.** `mc_refresh` is `HttpOnly; Secure; SameSite=Lax; Path=/v1/auth`. Native clients get the token in the
  body; browsers never do.
- **Switch-firm and refresh re-resolution.** Both use the live membership and firm status.
- **Session endpoints.** Lists and deletes are filtered by the caller's user id.
- **Magic links.**
  - 256-bit token, stored hashed, single use through a conditional `find_one_and_update`, 15-minute expiry.
  - `start` returns 202 in every case.
  - Returns 503 when the feature is disabled.
- **Scoped links.** 256-bit `mcl_` token stored hashed. The firm comes from the stored link. The exchange is rate
  limited.
- **Role checks.**
  - Viewer < dispatcher < owner is enforced on every data route I read.
  - Invitations, member changes, audit, firm patch and carrier delete require the owner.
  - No dispatcher-to-owner path was found.
  - Request models use `extra="forbid"`, so `role` and `tenant_id` cannot be smuggled in.
- **Sensitive carrier PATCH and create.**
  - Fee, floor, agreement and consent return 409 `approval_required` for dispatchers. A `null` removal of these
    fields is caught too.
  - `consent` is refused on `PATCH` even for owners.
  - A consent grant without `method` returns 422.
- **Phone tombstones.**
  - Carrier and driver soft delete writes a unique `deleted:<id>` tombstone and keeps the real number in
    `phone_deleted`.
  - Trucks unset the VIN.
  - Re-adding works, and the plugin's phone lookup cannot match a tombstone.
- **Search input.**
  - Every `$regex` goes through `re.escape` and is capped at 100 characters.
  - Query parameters are typed strings, and body fields are validated by pydantic and then by repo rules. No
    `$`-key or dict value reaches a filter.
  - Pagination limits are 1 to 200. Bad cursors return 400.
  - Bad ObjectIds return 404 (`parse_id`, `_object_id`, path patterns).
- **Error envelope.** All handlers render the envelope. 500s reveal nothing. Validation errors never echo input.
- **Secrets.**
  - Settings use `SecretStr`.
  - Log redaction covers token query parameters, bearer headers and sensitive keys, and uvicorn's access log is
    off.
  - Broker-check details exclude URLs and the FMCSA key.
  - `/v1/integrations` returns status only.
  - Idempotency replays strip invitation and link tokens.
  - `gen_keys.py` prints only to stdout.
- **Broker vetting otherwise fails closed.** A missing key, transport error, parse error or partial bond data gives
  `unknown`. No FMCSA record gives `fail`. Without `FMCSA_WEBKEY` the route returns 503. (F2 and F3 are the
  exceptions.)
- **Counters and events.** Counters use an atomic upsert-`$inc` with one retry on the first-insert race. Event `seq`
  comes from that counter and has a unique index.
- **Worker.** `firm_activate` is idempotent: upserts, the activation audit is written once, and `activated_at` is
  set last (apart from F15).
- **Settings.** Production fails closed without the core secrets, and refuses a wildcard CORS origin.

## Not verified

- I did not run anything against a real MongoDB. F12 and the real-database behavior of F5-B are reasoned from
  MongoDB semantics.
- I did not review WP1.4 or WP1.5 code (imports, loads, approvals, SSE). It does not exist in this tree yet.

## Fixes

Builder fix pass, 2026-10-25. Every finding was fixed. Each fix has a regression test that asserts the correct
behavior. The tests were red before the fix and are green after it. All 10 reviewer proofs in the scratchpad file
now fail, because the buggy behavior they assert is gone.

| Finding | Fix | Regression tests |
|---|---|---|
| F1 consent follows a phone change | `consent.phone_changes` drops the cache in the same write that changes the number. `consent.revoke_for_phone_change` appends one `revoked` ledger row with method `phone_changed` for each channel the old number held. The cache only counts rows whose `subject.phone` is the current number (`cache_for_phone`). Wired into `update_carrier` and the driver `update_record`. | `test_review_fixes_data.py::test_f1_carrier_phone_change_revokes_consent`, `::test_f1_driver_phone_change_revokes_consent`, `::test_f1_cache_ignores_grants_for_another_number` |
| F2 MC and DOT never cross-checked | `check._identity` resolves the MC docket record and requires its `dotNumber` to equal any supplied or stored DOT. A mismatch, or an MC with no record, adds a failing `mc_dot_match` check and fails `fmcsa_operating` and `broker_authority`, so the verdict is `do_not_book`. With an MC, the bond is matched on the MC and the docket's own DOT, never on an unverified DOT. A check with only a DOT gives `mc_dot_match=unknown`, so it is at most `review`. | `test_review_fixes_data.py::test_f2_mc_and_dot_of_different_entities_is_do_not_book`, `::test_f2_mc_without_docket_record_cannot_borrow_a_dot`, `::test_f2_dot_only_check_is_never_looks_ok`, `::test_f2_matching_mc_and_dot_still_look_ok`, `test_brokers.py::test_f2_route_refuses_a_stored_foreign_dot` |
| F3 unknown checks ignored | `verdict`: any `fail` gives `do_not_book`. `looks_ok` requires every check present to `pass`, and requires `fmcsa_operating`, `broker_authority`, `bond` and `mc_dot_match` to all be present. Anything else is `review`. | `test_review_fixes_data.py::test_f3_unknown_check_caps_verdict_at_review[ops@acme.com]`, `[not-an-email]` |
| F4 refresh racing logout-all | The rotate claim filters `{_id, rotated_to: None, revoked_at: None}`. A failed claim deletes the successor, revokes the family and returns 401. Each session stores the user's `epoch`, and refresh refuses (and revokes the family) when the user's `token_epoch` has moved on. | `test_review_fixes_auth.py::test_f4_refresh_racing_logout_all_fails[before_successor]`, `[after_successor]`, `::test_f4_refresh_requires_current_epoch` |
| F5 inf/NaN written without audit | `StrictModel` sets `allow_inf_nan=False`, so non-finite numbers in any request body are 422. `_number` (carriers) and `_coordinate` (facilities) require `math.isfinite`. `store.ensure_auditable` hashes the states before `insert`, `update`, `soft_delete`, `add_note` and `record_consent` write anything, so a write can never land without its audit row. | `test_review_fixes_data.py::test_f5_non_finite_numbers_are_422_and_write_nothing`, `::test_f5_repo_rejects_non_finite_values_before_writing` |
| F6 OTP verify reveals accounts | Order is: per-IP check limit (`CHECK_PER_IP=60`/h), then per-phone check limit, then the code, then the account lookup. A wrong code is the same 400 for every phone. Only after an approved code does an unknown phone get 422 `signup_details_required`, with a single-use, phone-bound, 10-minute `signup_ticket` (`mcs_…`, stored hashed in `platform.signup_tickets`, TTL index). The client finishes signup by sending `signup_ticket` + `firm_name` + `accept_terms` instead of a code. | `test_review_fixes_auth.py::test_f6_wrong_code_is_the_same_for_known_and_unknown_phones`, `::test_f6_unknown_phones_are_rate_limited`, `::test_f6_signup_ticket_finishes_signup_once`; updated `test_auth_otp.py::test_otp_new_user_without_signup_details_is_422` |
| F7 last-owner race | The route now writes first, then checks, then compensates. `remove_membership` marks the row `removing`, then counts active owners. If none are left it restores the row and returns 409, otherwise it deletes it. `change_membership_role` demotes first, counts, and restores `owner` if none are left. Of two concurrent changes, at most one can see another owner left. | `test_review_fixes_auth.py::test_f7_concurrent_owner_changes_keep_an_owner[remove]`, `[demote]` (deterministic interleaving); `test_realdb.py::test_last_owner_removal_is_atomic`, `::test_last_owner_demotion_is_atomic` (threads, real MongoDB, 12 rounds each) |
| F8 invitations matched an unverified email | `PATCH /v1/me` with a new email unsets `email_verified_at`, and `GET/PATCH /v1/me` expose `user.email_verified`. Magic links store the address they were sent to; using one sets `email_verified_at`, but only if the user still has that address. Invitation accept matches the phone, or the email only when verified. Otherwise it returns 403 `email_not_verified` or `invitation_mismatch`. | `test_review_fixes_auth.py::test_f8_invitation_needs_a_verified_email`, `test_auth_magic_link.py::test_f8_magic_link_marks_the_email_verified` |
| F9 leftmost X-Forwarded-For trusted | `client_ip(request, settings)` takes the entry `TRUSTED_PROXY_HOPS` (default 1, max 10) from the right. If the header is shorter than the proxy chain, it uses the peer address. | `test_review_fixes_auth.py::test_f9_client_ip_counts_trusted_hops_from_the_right`, `::test_f9_spoofed_first_hop_cannot_dodge_ip_limit` |
| F10 no body size limit | `BodyLimitMiddleware` (pure ASGI) applies to every route. The default is `MAX_BODY_BYTES` = 1 MiB. A declared Content-Length over the limit gets 413 before the body is read. A chunked body is counted as it streams and refused once it passes the limit. The 413 uses the error envelope (`payload_too_large`) and carries `X-Request-ID` (tested). The middleware sits inside CORS, so CORS headers apply too (by construction, not tested). The per-route hook `app.body_limit_rules` gives `POST /v1/imports` (WP1.4) `IMPORT_MAX_BYTES` plus 64 KiB of multipart framing. | `test_review_fixes_auth.py::test_f10_request_body_limit`, `::test_f10_per_route_override_hook` |
| F11 dispatcher grants consent directly | `POST /v1/carriers/{id}/consent` from a dispatcher returns 409 `approval_required` with `approval_kind=carrier_terms_change`, and no ledger row is written. The owner records the grant directly. `DELETE …/consent/{channel}` stays immediate for dispatchers and owners. | `test_review_fixes_data.py::test_f11_consent_grant_needs_owner_revoke_is_immediate`; `test_consent_links.py` updated to grant as owner |
| F12 stale consent cache | Ledger rows carry a gap-free per-subject `version`. A unique index on `(subject.type, subject.id, version)` serializes concurrent appends, and a loser retries with the next version. The cache is built from the gap-free prefix and written with a compare-and-set on `consent_version <= v` and the phone it was computed for. A writer with an older view can never overwrite a newer cache. `rebuild_cache` forces the write. | `test_review_fixes_data.py::test_f12_stale_cache_write_cannot_resurrect_revoked_consent` (deterministic); `test_realdb.py::test_consent_cache_matches_ledger_under_concurrent_writes` (8 threads × 16 writes, real MongoDB) |
| F13 idempotency per firm, not per user | Records carry `user_id`, and the unique index is `(tenant_id, user_id, key, route)`. Startup drops the retired `tenant_id_1_key_1_route_1` index. | `test_review_fixes_auth.py::test_f13_idempotency_is_scoped_to_the_user`, `test_indexes.py::test_retired_idempotency_index_is_dropped` |
| F14 portal ignores firm and carrier state | `scoped.portal_allowed` requires an active firm and a live carrier that is not offboarded. It is checked on exchange and on every portal request. Offboarding by PATCH `status=offboarded` or by DELETE revokes the carrier's links (`revoke_subject_links`, audited as `carrier.links_revoke`). | `test_review_fixes_data.py::test_f14_portal_rejects_suspended_firm`, `::test_f14_offboarded_carrier_loses_portal_access[patch]`, `[delete]`, `[direct]`; `test_portal.py::test_portal_is_tenant_isolated` now expects 401 `link_revoked` for a deleted carrier |
| F15 activation onto a foreign firm row | `_upsert_firm` raises `ValueError` when an existing firm row's `signup_id` differs, so no membership is granted. | `test_review_fixes_auth.py::test_f15_firm_activate_refuses_another_signups_firm` |
| F16 unbounded broker notes | `$push: {notes: {$each: [note], $slice: -MAX_NOTES_KEPT}}` with `MAX_NOTES_KEPT = 200`. The note shape `{at, text, session_id, by}` is unchanged. | `test_review_fixes_data.py::test_f16_broker_notes_keep_only_the_newest` |

Found by the new property tests (`tests/test_properties.py`, Hypothesis) and fixed in the same pass:

- `\D` and `\d` match Unicode digits. Because of that, `normalize_phone("000000000٠")` returned a non-ASCII "E.164" number, and MC and DOT numbers kept Arabic-Indic digits. Every digit pattern is now `[0-9]`: phones, `fields.digits`, `check.NON_DIGITS`, ZIP, the OTP code and the MC path. Tests: `test_phone_normalizer_never_crashes_and_only_returns_e164`, `test_phone_normalizer_refuses_non_ascii_digits`, `test_mc_validator_returns_ascii_digits_only`.
- `canonical_json({1: x})` and `canonical_json({"1": x})` produced the same hash. Non-string object keys are now refused. Test: `test_canonical_json_refuses_ambiguous_keys`.
