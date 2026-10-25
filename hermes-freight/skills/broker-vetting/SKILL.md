---
name: broker-vetting
description: "Vet a freight broker before quoting or booking, and record what was learned."
version: 0.1.0
author: hermes-freight
license: MIT
metadata:
  hermes:
    tags: [Freight, Dispatch, Brokers, Fraud]
---

# Broker vetting

Use before quoting, negotiating, or booking any load from a broker.

## Steps

1. **Recall first.** Call `broker_recall` with the MC number. Read the tags and notes.
2. **Check if needed.** If there is no check in the last 30 days, call `broker_check` with
   the MC (or DOT) and the contact's email address.
3. **Read the verdict:**
   - `do_not_book`: stop. Tell the dispatcher which check failed.
   - `review`: tell the dispatcher what is unknown or warned, and why it matters.
   - `looks_ok`: FMCSA operating status and broker authority are active and nothing warned.
     The bond is still unverified; say so.
4. **Fraud signals to call out** even when the verdict is `looks_ok`:
   - free email provider (gmail.com, yahoo.com) instead of a company domain
   - domain registered recently, or not matching the company name on FMCSA
   - phone or email on the Rate Con differs from the FMCSA contact
   - pressure to move fast, unusual payment terms, request to change payee details
5. **Remember.** After any call or load, save facts with `broker_remember`: payment speed,
   detention and lumper handling, rate behavior, problems. Include the date and source.

## Never

- Say a broker is verified when a check is `unknown`.
- Share a carrier's rate floor or fee with the broker.
