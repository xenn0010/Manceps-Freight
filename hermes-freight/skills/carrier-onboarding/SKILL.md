---
name: carrier-onboarding
description: "Add an owner-operator carrier to the firm's roster with terms and consent."
version: 0.1.0
author: hermes-freight
license: MIT
metadata:
  hermes:
    tags: [Freight, Dispatch, Carriers]
---

# Carrier onboarding

Use when the dispatcher says something like "add Carlos 214-555-0199 dry van 8%".

## Steps

1. **Collect the basics** from the dispatcher's message. Ask only for what is missing:
   - phone, name, company, MC and DOT numbers
   - equipment (dry_van, reefer, flatbed, step_deck, power_only, box_truck, hotshot)
   - dispatch fee percent, rate floor per loaded mile
   - home base, preferred lanes, regions or freight to avoid
2. **Check for an existing record** with `carrier_get` by phone. Update rather than duplicate.
3. **Save the profile** with `carrier_upsert`. Fee and rate floor need the dispatcher's
   approval; expect the approval prompt.
4. **Consent.** Do not record consent from the dispatcher's word alone. Record it only once
   the carrier has agreed, for example in the signed dispatch agreement or by replying YES
   to an opt-in message, and put that in `consent.method` with the date.
5. **Agreement.** Set `agreement_signed: true` only after the signed agreement is on file.
   The agreement template must come from the firm's transportation lawyer.
6. **Confirm back** to the dispatcher in one short message: name, equipment, fee, floor,
   lanes, and what is still missing (agreement, consent, W-9, COI, authority letter).

## Never

- Message the carrier before consent is on file. The policy hook blocks it anyway.
- Guess a rate floor. Ask.
