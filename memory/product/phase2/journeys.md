# Phase 2 Journeys

Start each one after Reset demo. 1440×900 unless noted. Phase 1 journeys JRN-1..JRN-23 and JRN-25 remain valid.

- **JRN-26** Schedule overview (supersedes JRN-24). Steps: select Truck 101, then switch to Schedule. Expected:
  - 4 rows, Truck 101 highlighted, day labels Mon/Tue/Wed and a "Now" marker at 10:00.
  - L-101 shows as solid, the 400-mi empty return as dotted grey, O-1 as dashed purple "Proposed", and L-103 on Wed as solid.
  - Truck 104 shows off duty (quiet) until Tue 07:00.
  - Switching back to Map keeps Truck 101 selected. superseded: [JRN-24]
- **JRN-27** Schedule conflict. Steps: in Schedule, look at Truck 102. Expected: the L-201 ETA 15:30 shows past the 14:00–15:00 window in amber/red.
- **JRN-28** Block click. Steps: click the L-103 block. Expected: the same truck/load panel as the map opens, with full pickup and delivery windows.
- **JRN-29** Beyond horizon. Steps: scroll or zoom so a block is cut at the edge. Expected: a "continues →" cue appears and opens the full commitment.
- **JRN-30** Booking reflected in schedule. Steps: run the Phase 1 booking, then open Schedule. Expected: O-1 (L-102) is solid "Booked" and the empty-return block is gone.
- **JRN-31** Exception resolution. Steps: click "Delivery at risk · Truck 102", then "Call broker for new appointment", and let it finish. Expected:
  - The call panel transcript ends with "New window 15:30–16:30 confirmed".
  - The alert leaves the attention strip, and L-201 reads "On track · rescheduled".
  - The delay history shows the original 14:00–15:00, release 12:30 and revised 15:30–16:30.
  - A text to Ben Ortiz is sent, then acknowledged.
  - The schedule block is no longer red.
- **JRN-32** Exception idempotency. Steps: click the re-appointment action 3 times and reload mid-call. Expected: one call, one revision, one driver text.
- **JRN-33** Advance time. Steps: click "Advance time" repeatedly. Expected:
  - The clock moves to each next event in order (e.g. 11:30 Truck 103 delivered, 12:00 Truck 101 released, 12:30 Truck 102 loaded…).
  - The markers animate, and the activity feed and notifications log each event with its time.
  - Truck 103 goes Delivered → Document received with a viewable POD, then shows "available · finding next work".
- **JRN-34** End of events. Steps: advance past the last event. Expected: "No more scheduled events" appears and the clock stays the same.
- **JRN-35** Execution of the booked load. Steps: book O-1, then advance to Tue. Expected: L-102 shows Picked up → In transit → Delivered → Document received, each logged with a time and source (driver text/call).
- **JRN-36** Revised terms. Steps: on O-1, Request changes with a target of $1,200. Expected:
  - The broker counters $1,150 and proposal v2 appears with a v1→v2 diff.
  - The approval is reset to "Review required".
  - Contribution becomes $376, improvement +$1,096, and the Preview revenue $4,850 / after costs $2,150.
- **JRN-37** Revised booking metrics. Steps: approve v2 and let it confirm. Expected: cards show $4,850 / $2,150 / 4.7%.
- **JRN-38** Written terms mismatch. Steps: trigger the demo scenario "Written terms differ" (a demo-script option). Expected: the warning shows, and booking is blocked until "Reviewed" is clicked.
- **JRN-39** Feedback: fact. Steps: from Truck 101's panel, give the feedback "Driver available Tue 06:00" and choose "Correct a fact". Expected: the field updates and a correction log shows old → new.
- **JRN-40** Feedback: rule. Steps: in chat type "Never book Ava on loads over 450 miles" and choose "Make it a rule". Expected: a preview shows scope Driver: Ava Reed and the rule text. Apply adds it to AI instructions. Cancel adds nothing.
- **JRN-41** Feedback: one-off. Steps: reject O-1 with the reason "Prefer Oakland later pickup", classified as "Just this decision". Expected: no rule is created and the reason is logged on the proposal.
- **JRN-42** Truck 104 search. Steps: expand the AI activity. Expected: Truck 104's search progress shows, and a candidate offer appears as an info notification.
- **JRN-43** Reset. Steps: after JRN-31 + JRN-36 + JRN-40, Reset demo. Expected: the alert is back, the rules list is empty, v1 only, and the clock is 10:00.
