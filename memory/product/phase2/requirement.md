# Phase 2 Requirements: Schedule, exceptions, execution & feedback (phase-2)

**Goal:** Complete the operational loop on the dashboard. The Schedule view mirrors the map. The Truck 102 delivery exception is resolved through a simulated broker re-appointment. Booked loads progress through pickup to document received as scenario time advances. Rate changes create re-reviewable proposal versions. Dispatcher feedback is classified as a fact correction, a one-off choice or a standing rule.

Context: `../overview.md`. Builds on Phase 1 as delivered: the Moveon design, the shared zustand store persisted in localStorage `freightos-demo`, `src/services/*`, side panels one at a time, booked load L-102 (O-1, pickup Carson), broker contact Maya Lin, and the demo-script helper. Everything external remains SIMULATED.

## Functional requirements

### Schedule view
- REQ-71 [event] When the dispatcher switches to Schedule, the system shall show one row per truck (101–104) in place of the map, keeping the selected truck highlighted. (no failure mode)
- REQ-72 [always] The system shall show a time scale from Mon 26 Oct 06:00 to at least Thu 29 Oct 00:00 PT, with labelled day boundaries.
- REQ-73 [always] The system shall show a "Now" marker at the current scenario clock time.
- REQ-74 [always] The system shall render rest/off-duty periods as quiet hatched or low-contrast blocks.
- REQ-75 [always] The system shall render jobs as solid blocks, proposed work as dashed purple "Proposed" blocks, empty repositioning as dotted grey blocks, and open gaps as labelled "Available" space.
- REQ-76 [always] The system shall render conflicts and at-risk windows in amber/red (e.g. the L-201 ETA 15:30 vs the 14:00–15:00 window).
- REQ-77 [state] While O-1 is not broker-confirmed, the system shall show it as tentative "Proposed".
- REQ-78 [event] When O-1 is booked, the system shall turn its block solid and remove the 400-mi empty-return block.
- REQ-79 [event] When the dispatcher clicks a schedule block, the system shall open the same truck/load panel the map opens. (no failure mode)
- REQ-80 [event] When a block extends past the visible horizon, the system shall show a "continues →" cue that opens the full commitment details. (no failure mode)
- REQ-81 [state] While the LA–Phoenix alternative is inspected, the system shall show its overlap with L-103 on Truck 101's row as a conflict preview (interpreted).

### Truck 102 delivery exception
- REQ-82 [event] When the dispatcher opens "Delivery at risk · Truck 102", the system shall show an exception panel with delay facts, the impact, and the primary action "Call broker for new appointment" (the AI request already logged).
- REQ-83 [event] When the simulated broker re-appointment call runs, the system shall show a call panel with transcript, extracted facts and the outcome "New window 15:30–16:30 confirmed".
- REQ-84 [event] When the new appointment is confirmed, the system shall resolve the alert, set L-201 to "On track · rescheduled", and update the map, schedule, attention strip and notifications.
- REQ-85 [always] The system shall preserve the delay history (original window, delay reason, release time, revised window, source) on L-201.
- REQ-86 [event] When the appointment is updated, the system shall send a simulated text to Ben Ortiz with the new window and track his acknowledgment separately.
- REQ-87 [unwanted] If the dispatcher triggers the re-appointment twice, then the system shall keep one call and one revision.

### Execution updates
- REQ-88 [event] When the dispatcher clicks "Advance time" (or a demo-script step), the system shall move the scenario clock to the next scheduled event and apply it. [unwanted partner REQ-89]
- REQ-89 [unwanted] If no further events exist, then the system shall show "No more scheduled events" and leave the clock unchanged.
- REQ-90 [always] The system shall progress trips through Picked up → In transit → Delivered → Document received, with each step logged with a time and source (driver call/text).
- REQ-91 [event] When a truck's position changes due to an event, the system shall move its marker along its route with animation.
- REQ-92 [event] When a delivery is completed, the system shall request the POD from the driver and show "Document received" with a viewable simulated POD document.
- REQ-93 [event] When Truck 103 delivers L-301, the system shall show a "Truck 103 available · finding next work" activity item (interpreted).
- REQ-94 [always] The system shall show driver call/text panels with the message thread, objective and outcome.
- REQ-95 [always] The system shall show Truck 104's AI search progress (e.g. "Checking 3 boards · Waiting on one broker") and surface a candidate offer for Tue 07:00+ as an info item (interpreted, no booking required).

### Revised terms
- REQ-96 [event] When the dispatcher uses "Request changes" with a target rate (e.g. $1,200), the system shall simulate a broker counter (e.g. $1,150) and create proposal version v2.
- REQ-97 [event] When a new version exists, the system shall invalidate the earlier approval and require review, with a v1→v2 diff.
- REQ-98 [event] When the rate changes, the system shall recalculate contribution, improvement and Preview metrics from the new rate.
- REQ-99 [unwanted] If written terms differ from the agreed version, then the system shall flag "Written terms differ" and block booking until the dispatcher reviews them.

### Feedback & rules
- REQ-100 [event] When the dispatcher gives feedback (from a decision, call or chat), the system shall ask them to classify it as "Correct a fact", "Just this decision" or "Make it a rule". (no failure mode)
- REQ-101 [event] When "Correct a fact" is chosen, the system shall update the record and log the correction with its old and new values.
- REQ-102 [event] When "Make it a rule" is chosen, the system shall show a rule preview with scope (Driver / Truck / Carrier) and the plain-language rule before "Apply rule".
- REQ-103 [unwanted] If the dispatcher cancels the rule preview, then the system shall save no rule.
- REQ-104 [always] The system shall list active rules in an "AI instructions" panel with scope, source and created time.

### Notifications & reset
- REQ-105 [always] The system shall emit info vs decision notifications for every Phase 2 transition, each opening its context.
- REQ-106 [event] When Reset demo runs, the system shall restore every Phase 2 record to the seed state.

## Quality requirements
```
Q-10 Tag: Schedule.Sync
     Scale: mismatches between schedule blocks, map and panel for the same truck/trip
     Meter: tester before/after booking and after re-appointment
     Must: 0   Plan: 0
Q-11 Tag: Time.Consistency
     Scale: events shown with times inconsistent with the scenario clock (future events marked done, etc.)
     Meter: tester across 5 Advance-time steps
     Must: 0   Plan: 0
Q-12 Tag: Idempotency.Exception
     Scale: duplicate calls/revisions/texts after repeat clicks or reload
     Meter: tester
     Must: 0   Plan: 0
Q-13 Tag: Metrics.Revision
     Scale: card/preview values matching rate-derived math after a v2 rate
     Meter: tester at $1,150
     Must: exact   Plan: exact
Q-14 Tag: Schedule.Legibility
     Scale: overlapping/unreadable block labels at 1280 width
     Meter: screenshot
     Must: 0   Plan: 0
Q-15 Tag: Visual.Polish
     Scale: consistency with the Moveon reference
     Meter: human
     Must: consistent   Plan: stage-ready
```
