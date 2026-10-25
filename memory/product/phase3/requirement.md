# Phase 3 Requirements: Fleet setup, conversational intake, AI settings (phase-3)

**Goal:** Replace the Fleet placeholder with a polished setup workspace. The dispatcher can view and edit Carrier, Truck, Driver and Commitment records. A short guided intake (typed or simulated voice) extracts the details into a structured confirmation before saving. AI operating instructions are set in one place. Every edit flows through the shared store, so the dashboard map, schedule, metrics and panels reflect it.

Context: `../overview.md`. Builds on Phases 1–2 as delivered: the Moveon design, the shared store `freightos-demo`, `src/services/*` (engine.js, engine2.js, phase2Services.js), the AI instructions/rules list, and the demo script. Everything external is SIMULATED.

## Functional requirements

### Fleet workspace
- REQ-107 [always] The system shall show the Fleet page with tab pills "Carriers", "Trucks", "Drivers" and "Commitments", each with a count.
- REQ-108 [always] The system shall show seeded records: 1 carrier (Demo West Freight), 4 trucks (101–104, 53' dry van), 4 drivers (Ava Reed, Ben Ortiz, Chloe Chen, Daniel Brooks), and commitments L-101, L-103, L-201, L-301 (plus L-102 once booked).
- REQ-109 [event] When the dispatcher opens a record, the system shall show an editable detail drawer. (no failure mode)
- REQ-110 [always] The system shall show Carrier fields: name, contact name, phone, email, and operating preferences (home base, preferred lanes, max deadhead mi, min rate/mi, avoid regions).
- REQ-111 [always] The system shall show Truck fields: unit, carrier, equipment, current location, operational status, truck availability (from), and cost assumptions ($/mi, default $1.80).
- REQ-112 [always] The system shall show Driver fields: name, phone, assigned truck, driver availability (from), home location, and preferences, with a note that "Rest/hours info is scenario data, not a compliance assessment".
- REQ-113 [always] The system shall show Commitment fields: truck, origin, destination, pickup window, delivery window, status, rate, broker, and terms (commodity, weight, protected flag).
- REQ-114 [always] The system shall keep truck availability and driver availability as separate inputs.
- REQ-115 [event] When the dispatcher saves an edit, the system shall update the shared store and show a "Saved" toast. [unwanted partner REQ-116]
- REQ-116 [unwanted] If a required field is empty or a window ends before it starts, then the system shall show an inline error and disable Save.
- REQ-117 [event] When a truck's cost per mile is edited, the system shall recalculate the dashboard metrics from the new value (interpreted: the per-truck rate applies to that truck's segments).
- REQ-118 [event] When a commitment's windows are edited, the system shall reflect the change on the schedule and in the truck panel.
- REQ-119 [event] When the dispatcher adds a new record via "Add", the system shall open the guided intake for that record type. (no failure mode)

### Conversational intake
- REQ-120 [event] When the dispatcher types or dictates (simulated mic) a description, the system shall show extracted fields in a structured confirmation card with each field editable. [unwanted partner REQ-121]
- REQ-121 [unwanted] If required fields are missing from the description, then the system shall list them as "Needs info" and keep "Confirm & save" disabled until they are filled.
- REQ-122 [always] The system shall provide example prompts, e.g. "Add truck 105, 53' dry van, in Fresno, available Tue 06:00, driver Maria Lopez 555-0142".
- REQ-123 [event] When the dispatcher confirms, the system shall create linked records with stable IDs and show them on the dashboard map/strip/schedule.
- REQ-124 [unwanted] If the unit number already exists, then the system shall warn "Truck 105 already exists" and offer to edit instead of duplicating.
- REQ-125 [always] The system shall walk through a short guided stepper (Carrier → Truck → Driver → Commitment) with skip-able steps (interpreted).

### AI settings
- REQ-126 [always] The system shall show an "AI settings" panel (reachable from the header/command bar and Fleet) with: negotiation floor ($/mi), max counter steps, auto-contact brokers on/off, require approval before booking (locked on in demo), driver message tone, and active rules (from Phase 2).
- REQ-127 [event] When a setting changes, the system shall log an activity entry and apply it to the next simulated action (interpreted). (no failure mode)
- REQ-128 [event] When the dispatcher deletes or toggles a rule, the system shall update the AI instructions list. (no failure mode)

### Shell polish
- REQ-129 [always] The system shall keep the header count "N trucks" in sync with the truck records.
- REQ-130 [event] When Reset demo runs, the system shall restore all Fleet records, settings and rules to seed.

## Quality requirements
```
Q-16 Tag: Fleet.Sync
     Scale: dashboard surfaces not reflecting a Fleet edit (map, strip, schedule, header count, metrics)
     Meter: tester edits cost/mi and windows, adds truck 105
     Must: 0   Plan: 0
Q-17 Tag: Intake.Usability
     Scale: steps for a first-time user to add a truck+driver
     Meter: tester
     Must: ≤ 4 actions after typing   Plan: 2
Q-18 Tag: Data.Validation
     Scale: invalid records saved (empty required, window end < start, duplicate unit)
     Meter: tester
     Must: 0   Plan: 0
Q-19 Tag: Visual.Polish
     Scale: consistency with the Moveon reference (tab pills, light tables, drawers)
     Meter: human
     Must: consistent   Plan: stage-ready
```
