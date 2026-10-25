# Phase 1 Requirements: FreightOS dashboard + return-load flow (phase-1)

**Goal:** A dispatcher opens the dashboard, understands fleet finances, positions and AI work at a glance, asks FreightOS about Truck 101's return load, inspects the simulated broker call, approves, receives broker confirmation, sees the metrics change, and receives driver acknowledgment. All of it is deterministic and resettable.

Context, seed data and integration choices: see `../overview.md`. Everything external is MOCKED and demo-only.

## Functional requirements

### Shell & header
- REQ-1 [always] The system shall show a slim left navigation with "Dashboard" and "Fleet" destinations.
- REQ-2 [always] The system shall show "Demo West Freight", "4 trucks" and a short status summary in the header.
- REQ-3 [always] The system shall show the scenario clock "Mon 26 Oct 2026 · 10:00 PT" in the header.
- REQ-4 [always] The system shall show a small "Demo data" indicator in the header.
- REQ-5 [always] The system shall show a "Talk to FreightOS" microphone button in the header.
- REQ-6 [event] When the dispatcher clicks "Reset demo" and confirms, the system shall restore the initial scenario, clock, metrics and records. [unwanted partner REQ-7]
- REQ-7 [unwanted] If the dispatcher cancels the reset confirmation, then the system shall leave the current state unchanged.
- REQ-8 [event] When the dispatcher opens Fleet in this phase, the system shall show a read-only list of the 4 trucks with driver and status, plus a "Setup coming next" note (interpreted). (no failure mode)

### Business summary
- REQ-9 [always] The system shall show three cards: "Booked revenue", "After trip costs (est.)", "Empty driving".
- REQ-10 [always] The system shall derive every card value from the shared trip/segment ledger at $1.80/mi.
- REQ-11 [state] While the return load is not booked, the system shall show $3,700, $1,054 with "$2,646 direct costs · Before overhead", and 29.9% with "440 of 1,470 planned miles".
- REQ-12 [state] While the return load is booked, the system shall show $4,800, $2,100 with "$2,700 direct costs · Before overhead", and 4.7% with "70 of 1,500 planned miles".
- REQ-13 [event] When the dispatcher opens the "Current plan" info, the system shall explain that it covers active trips, confirmed trips picking up in the next 48 h, and required connecting repositioning, and that booked revenue is not cash collected. (no failure mode)
- REQ-14 [event] When the dispatcher clicks a metric card, the system shall open a breakdown panel listing the contributing trips/segments with revenue, miles, cost and the formula. (no failure mode)
- REQ-15 [state] While a proposal is awaiting confirmation, the system shall show a labelled "Preview" of post-booking values without changing the card values.

### Map
- REQ-16 [always] The system shall render a real clean basemap (MapLibre + free vector tiles) centred on California, keeping provider attribution visible.
- REQ-17 [always] The system shall keep the labels San Francisco, Oakland, Sacramento, Stockton, Fresno, San Jose and Los Angeles legible while suppressing unrelated POIs.
- REQ-18 [event] When the dashboard loads, the system shall fit all 4 trucks into view with padding. (no failure mode)
- REQ-19 [always] The system shall draw each truck as a small truck marker with heading and a short unit label ("101").
- REQ-20 [always] The system shall keep truck labels from overlapping each other.
- REQ-21 [event] When the dispatcher hovers a truck, the system shall show a tooltip with driver and one-line status. (no failure mode)
- REQ-22 [always] The system shall draw routes along plausible roads (pre-baked road geometry).
- REQ-23 [always] The system shall show a legend for confirmed work (solid), proposed work (dashed accent) and empty repositioning (dotted grey).
- REQ-24 [always] The system shall show current position with a different symbol from future pickup and delivery stops.
- REQ-25 [event] When the dispatcher selects a truck on the map, the system shall emphasize its route, subdue the other routes and open the truck detail panel. (no failure mode)
- REQ-26 [event] When the dispatcher deselects (close panel, Esc, or click empty map), the system shall return to the fleet overview with all routes at normal emphasis. (no failure mode)
- REQ-27 [always] The system shall show a Map / Schedule switch, with Schedule showing a "Coming in next phase" placeholder that keeps the selected truck (interpreted).

### Truck detail panel
- REQ-28 [event] When a truck is selected, the system shall show unit, driver, equipment "53' dry van", current status, truck availability, driver availability, current trip and upcoming commitments. (no failure mode)
- REQ-29 [state] While Truck 101 is selected, the system shall mark L-103 as "Protected commitment".

### Attention strip & AI activity
- REQ-30 [always] The system shall show an attention strip with "Delivery at risk · Truck 102" (amber/red) and "Return load ready · Truck 101".
- REQ-31 [event] When the dispatcher clicks "Return load ready · Truck 101", the system shall select Truck 101 and open the return-load decision panel. (no failure mode)
- REQ-32 [event] When the dispatcher clicks "Delivery at risk · Truck 102", the system shall select Truck 102 and show the delay facts (release 12:30, ETA 15:30 vs window 14:00–15:00, "Revised appointment requested") (interpreted: resolution flow is phase 2). (no failure mode)
- REQ-33 [always] The system shall show a one-line AI activity summary such as "Finding loads for Truck 104 · Waiting on one broker".
- REQ-34 [event] When the dispatcher expands the AI activity summary, the system shall show a timestamped activity feed, newest first, with each entry linked to its record. (no failure mode)

### AI command bar & voice
- REQ-35 [always] The system shall show a persistent "Ask FreightOS…" input with a mic button in reserved space that never covers the map controls or actions.
- REQ-36 [always] The system shall show example chips "What needs me?", "Explain Truck 101's plan" and "Find a return load".
- REQ-37 [event] When the dispatcher submits a command, the system shall open a conversation panel with a scripted deterministic answer. [unwanted partner REQ-38]
- REQ-38 [unwanted] If the command matches no script, then the system shall reply with a helpful fallback listing the supported example commands.
- REQ-39 [event] When "What needs me?" is asked, the system shall list the 2 attention items, each as a clickable link to its decision.
- REQ-40 [event] When "Explain Truck 101's plan" or "Find a return load" is asked, the system shall summarize offer O-1 ($1,100, +$1,046 vs empty return, SF by Tue 18:00) with an "Open decision" link.
- REQ-41 [event] When the dispatcher clicks a mic (header or bar), the system shall show a listening waveform, then a transcribed preset command, then the scripted answer. [unwanted partner REQ-42]
- REQ-42 [unwanted] If the dispatcher clicks the mic again while listening, then the system shall cancel listening without sending a command.
- REQ-43 [always] The system shall link AI claims to their supporting conversation, call or document.

### Return-load decision
- REQ-44 [always] The system shall lead the decision panel with the proposed action, the business effect ("+$1,046 planned contribution vs empty return") and the schedule fit ("In SF Tue 18:00 · protects Wed 08:00 pickup").
- REQ-45 [event] When the dispatcher expands economics, the system shall show revenue $1,100, 430 mi (400 loaded, 12 + 18 empty), cost $774, contribution $326, versus empty return $0 / $720 / -$720.
- REQ-46 [always] The system shall state that +$1,046 is improved planned contribution, not extra revenue or realized savings.
- REQ-47 [event] When the dispatcher expands alternatives, the system shall show LA–Phoenix $1,600 as unsuitable because its Wednesday delivery conflicts with L-103. (no failure mode)
- REQ-48 [always] The system shall show load terms: Demo Pacific Broker, Tue PU 08:00–09:00 LA, DEL 16:00–17:00 Oakland, 53' dry van, packaged goods, 30,000 lb, with a "Written terms match offer" check linked to the rate confirmation document.
- REQ-49 [always] The system shall label the primary action "Approve and request confirmation".
- REQ-50 [event] When the dispatcher clicks "Approve and request confirmation", the system shall set the status to "Awaiting broker" and start a simulated broker call. [unwanted partner REQ-51]
- REQ-51 [unwanted] If the approve action fires more than once, then the system shall create only one approval, one call and one booking.
- REQ-52 [event] When the dispatcher clicks "Reject", the system shall require a reason before rejecting. [unwanted partner REQ-53]
- REQ-53 [unwanted] If the reason is empty, then the system shall keep the reject button disabled.
- REQ-54 [event] When the dispatcher clicks "Request changes", the system shall capture a note and set the status to "Changes requested" with an activity entry (interpreted: the negotiation round is phase 2). (no failure mode)
- REQ-55 [event] When the dispatcher clicks "Take over", the system shall pause AI on this task and show "You're handling this". (no failure mode)

### Broker call & booking chain
- REQ-56 [always] The system shall show a call panel with contact, objective, live status, transcript lines appearing progressively, extracted facts and outcome.
- REQ-57 [event] When the dispatcher clicks "Pause" in the call panel, the system shall stop transcript progress until "Resume" is clicked. (no failure mode)
- REQ-58 [event] When the dispatcher clicks "Take over" in the call panel, the system shall end the AI's role in the call and mark it "Dispatcher took over". (no failure mode)
- REQ-59 [event] When the simulated broker confirms in writing, the system shall mark O-1 "Booked", add the trip to the plan and update the three metrics to the REQ-12 values.
- REQ-60 [event] When the load is booked, the system shall automatically send simulated driver instructions to Ava Reed and show "Driver instructions sent".
- REQ-61 [event] When the simulated driver replies, the system shall show "Driver acknowledged" separately from booking status.
- REQ-62 [always] The system shall show the status stepper: Proposal ready → Terms approved → Awaiting broker → Booked → Driver instructions sent → Driver acknowledged.
- REQ-63 [event] When the load is booked, the system shall replace Truck 101's empty-return route with the proposed-then-confirmed LA→Oakland→SF route on the map.
- REQ-64 [event] When the load is booked, the system shall remove "Return load ready · Truck 101" from the attention strip.

### Notifications
- REQ-65 [always] The system shall show a notifications bell with an unread count.
- REQ-66 [always] The system shall separate "Needs you" notifications from "Updates".
- REQ-67 [event] When the dispatcher clicks a notification, the system shall open its related truck, decision or call. (no failure mode)

### Architecture
- REQ-68 [always] The system shall keep all records (carriers, trucks, drivers, trips, offers, proposals, conversations, calls, documents, attention items, activity, notifications) in one shared store with stable IDs, timestamps, source and status.
- REQ-69 [always] The system shall route every mock action through a `services/` interface that can later be swapped for backend calls.
- REQ-70 [always] The system shall persist demo state in localStorage so a page reload keeps progress until reset.

## Quality requirements
```
Q-1  Tag: Metrics.Correctness
     Scale: card values matching the overview ledger figures exactly
     Meter: tester reads cards before and after booking, 2 runs
     Must: 6/6 values exact   Plan: 6/6 + breakdown sums match
Q-2  Tag: State.Sync
     Scale: surfaces (cards, map, attention strip, notifications, panel, feed) reflecting a booking
     Meter: tester after booking
     Must: 6/6   Plan: 6/6 within 500 ms
Q-3  Tag: Idempotency.Booking
     Scale: duplicate bookings/messages after rapid repeat clicks or reload mid-flow
     Meter: tester triple-clicks approve, reloads mid-call
     Must: 0   Plan: 0
Q-4  Tag: Map.Legibility
     Scale: overlapping truck labels or hidden city labels at 1280, 1440, 1920 widths
     Meter: screenshots at 3 widths
     Must: 0   Plan: 0
Q-5  Tag: Layout.Obstruction
     Scale: map controls/actions covered by the command bar or panels
     Meter: screenshots, panel open and closed
     Must: 0   Plan: 0
Q-6  Tag: Visual.Polish
     Scale: dispatcher judgement vs Dribbble references (typography, spacing, cards)
     Meter: human
     Must: "looks premium"   Plan: stage-demo ready
Q-7  Tag: Perf.Load
     Scale: ms from navigation to map + cards rendered
     Meter: browser timing, 3 loads
     Must: < 3000   Plan: < 1500 (estimate)
Q-8  Tag: Demo.Repeatability
     Scale: full stage flow runs identically after reset
     Meter: tester runs flow, resets, reruns
     Must: 2/2 identical   Plan: 3/3
Q-9  Tag: A11y.Focus
     Scale: primary controls reachable with Tab and a visible focus ring
     Meter: tester keyboard pass
     Must: 100% of primary actions   Plan: 100%
```
