# Requirements: FreightOS

## Core Value
An AI dispatcher, supervised by a human, that fills a small fleet's empty windows with profitable, schedule-safe loads. The dispatcher sees in one glance (1) how the fleet is doing financially, (2) where the trucks are and what they are doing, (3) what the AI is handling and what needs them, and can approve, change or take over from the dashboard.

## Personas & Roles
- **Dispatcher** (the only app user): small trucking company owner or independent dispatcher. Sets instructions, reviews decisions, corrects facts, intervenes.
- **Brokers / Drivers**: never log in. They appear only as simulated call and text counterparties.
- No auth. Single-user demo.

## Features
| id | feature | persona | phase |
|---|---|---|---|
| F-1 | App shell: slim nav (Dashboard, Fleet), header with "Demo West Freight", "4 trucks", status summary, notifications, scenario clock, "Demo data" badge, "Talk to FreightOS" mic, demo reset | Dispatcher | 1 |
| F-2 | Business summary: 3 cards (Booked revenue, After trip costs (est.), Empty driving), "Current plan" scope explainer, click a card to see its calculation and contributing trips, all derived from shared ledger | Dispatcher | 1 |
| F-3 | Map canvas: real clean basemap (MapLibre, free tiles, attribution) centred on California, key city labels, 4 truck markers with heading + unit labels, hover/selection status, no label collisions, road-following routes, legend (confirmed / proposed / empty repositioning), current position vs future stops, fit-to-fleet | Dispatcher | 1 |
| F-4 | Truck detail panel: select a truck to see its focused plan, deselect to return to fleet overview, with other routes subdued | Dispatcher | 1 |
| F-5 | Attention strip ("Delivery at risk · Truck 102", "Return load ready · Truck 101"), each opening its decision | Dispatcher | 1 |
| F-6 | AI activity summary line, expandable into an activity feed | Dispatcher | 1 |
| F-7 | AI command bar "Ask FreightOS…" with mic, example chips, scripted deterministic answers in a conversation panel; simulated voice (waveform, preset command) | Dispatcher | 1 |
| F-8 | Return-load decision panel: recommendation first, then economics, evidence, alternatives (LA–Phoenix $1,600 conflict); approve / request changes / reject with reason / take over | Dispatcher | 1 |
| F-9 | Simulated broker call panel: contact, objective, status, transcript, extracted facts, outcome, pause/takeover; written-terms comparison | Dispatcher | 1 |
| F-10 | Booking state machine through driver acknowledgment: proposal ready → terms approved → awaiting broker → booked → driver instructions sent → driver acknowledged; metrics update only after broker confirmation; preview before | Dispatcher | 1 |
| F-11 | Notifications: info vs decision-required, each opens its context | Dispatcher | 1 |
| F-12 | Schedule view (Map/Schedule switch, shared selection), one row per truck, time scale, day boundaries, now marker, quiet rest, tentative proposed blocks, conflicts, inspect commitments beyond horizon | Dispatcher | 2 |
| F-13 | Delivery exception flow for Truck 102: broker re-appointment call, confirm 15:30–16:30, resolve alert, keep delay history | Dispatcher | 2 |
| F-14 | Execution updates: picked up → in transit → delivered → document received, with scenario time advance; driver call/text panels | Dispatcher | 2 |
| F-15 | Revised terms: a negotiated rate change creates a new proposal version needing re-review and recalculation | Dispatcher | 2 |
| F-16 | Feedback model: correction of fact vs choice for this decision vs standing rule (scoped driver/truck/carrier) with review before applying | Dispatcher | 2 |
| F-17 | Fleet page: editable Carrier, Truck, Driver, Commitment records; separate truck vs driver availability; cost assumptions | Dispatcher | 3 |
| F-18 | Conversational intake: type a description, see a structured confirmation of extracted fields (scripted), then save | Dispatcher | 3 |
| F-19 | AI settings / operating instructions panel (negotiation limits, preferences) | Dispatcher | 3 |

## Phases
- **Phase 1 (MVP: stage demo core)**: dashboard with full 4-truck scenario, map, metrics, attention strip, AI/voice controls, and the return-load flow from review to driver acknowledgment. F-1 to F-11. [requirement](phase1/requirement.md) · [journeys](phase1/journeys.md)
- **Phase 2: schedule & exceptions**: Schedule view, Truck 102 exception resolution, execution updates, revised terms, feedback/rules. F-12 to F-16.
- **Phase 3: fleet setup**: Fleet page records, conversational intake, AI settings. F-17 to F-19.

## UI/UX Rules
- SOLE visual reference (user decision, overrides LoopAI and the brief's colour words): Ronas IT "Moveon" Fleet Dispatch dashboard, https://dribbble.com/shots/27367688-Fleet-Dispatch-Tablet-Dashboard. Local copies are in /app/memory/product/design_ref/ref1.png, ref2.png and ref4.png (ref3 is a thank-you slide, ignore it).
  - Font SF UI Display (CSS stack: "SF Pro Display", -apple-system, then Inter as the web fallback). Palette: #181A1A ink, #AF6EFF purple (primary accent/actions/progress), #FFC46D amber, #A1E688 green.
  - Cool light-grey canvas (~#E6E7EA → #F1F2F4 soft gradient), frosted translucent white cards (~20px radius, subtle border, very soft shadow), lots of air.
  - Top bar: logo left, centred pill nav (active item is a white pill with icon + label, others are icon-only squares), bell + avatar/name on the right.
  - Status pills: green tint "In transit", purple tint "Picked up"/proposed, amber tint for warnings.
  - Purple progress bar with a ▶ marker for trip progress, and origin→destination with dot/line stops.
  - Muted grey bar sparklines with one highlighted bar, purple area-line charts with dashed markers, gradient tinted KPI cards (green/amber washes).
  - Horizontal selectable vehicle strip: cards with unit id, cargo/weight and a white truck image, with the selected one raised white with a purple cargo accent.
  - Clean, light, rounded tables with tab-pill filters and counts.
  - Large white 53' dry-van imagery as hero when a truck is focused (optional).
- Purple is the single action colour. Amber is the caution colour. Red only for hard exceptions (missed window).
- The map gets the most space. Secondary info goes in contextual side panels and drawers. Never show the full schedule, chat, feed and decision form at once.
- The command bar has reserved space and never covers the map controls or actions.
- Subtle motion on state changes, route selection and AI task progress.
- Figures are tabular and easy to scan. Desktop/laptop only, 1280–1920px.
- Every primary control produces a meaningful result. Visible keyboard focus.
- Copy is short and concrete: "Checking availability", "Broker offered $1,100", "Waiting for your approval".

## Integrations
| need | choice |
|---|---|
| Map | MapLibre GL + free clean vector basemap (CARTO Positron / OpenFreeMap), attribution kept. Swappable to Google Maps later behind a map adapter |
| Route geometry | Pre-baked road-following polylines (static GeoJSON in the app). No live routing API needed |
| AI chat | Scripted deterministic answers (MOCKED). Behind a service interface |
| Voice | Simulated mic: waveform + preset transcribed command (MOCKED) |
| Broker/driver calls & texts | Simulated, deterministic, demo-only (MOCKED). No real external messages |
| State | Browser-only: a frontend mock service layer (single store, localStorage persistence, reset). Clean `services/` interface for the teammate's future backend |

## Edge Cases
- Repeated clicks or events must not duplicate bookings, messages or activity entries (idempotent transitions).
- Metrics change only after broker confirmation. Before that, a labelled "Preview" shows the effect.
- A rate change makes a new proposal version, invalidates the earlier approval, and recalculates.
- Rejecting requires a reason. Take over pauses AI on that task.
- Booking status and driver acknowledgment are shown separately.
- Demo reset restores the exact initial scenario and clock.
- Commitments that extend past the visible horizon can still be inspected.

## Seed Data
Company: Demo West Freight. Clock: Mon 26 Oct 2026 10:00 Pacific. All trucks are 53' dry vans. Cost: $1.80/mi, all-in, no extra fuel or wages.
- **Truck 101 / Ava Reed**: unloading in LA, trip L-101 SF→LA. Truck release Mon 12:00, driver available Tue 07:00. Protected L-103: pickup SF Wed 08:00–09:00, deliver LA Wed 16:00–18:00.
- **Truck 102 / Ben Ortiz**: L-201 Fresno→Stockton. Loading delayed, release Mon 12:30, ETA 15:30 misses the 14:00–15:00 window. Re-appointment requested via broker (sim confirm 15:30–16:30).
- **Truck 103 / Chloe Chen**: L-301 Sacramento→Oakland, near Davis, ETA 11:30, window 11:00–13:00, on track.
- **Truck 104 / Daniel Brooks**: off duty San Jose until Tue 07:00. AI searching for next work.
- **Offer O-1**: Demo Pacific Broker, Tue LA→Oakland, $1,100, PU 08:00–09:00, DEL 16:00–17:00, packaged goods 30,000 lb, written terms match. 400 loaded + 12 empty to PU + 18 empty to SF = 430 mi, cost $774, contribution $326. Truck in SF Tue 18:00, 10 h rest + 4 h buffer before Wed PU. The alternative empty return is 400 mi, $0 revenue, $720 cost, -$720. Improvement is +$1,046 planned contribution (not extra revenue or savings).
- **Offer O-2**: second broker, LA→Phoenix $1,600. Wednesday delivery conflicts with L-103, so it is unsuitable.
- Ledger: L-101 $1,200 / 400 loaded / 15 empty; L-103 $1,300 / 400 / 10; L-201 $650 / 140 / 10; L-301 $550 / 90 / 5; plus 400 mi mandatory empty return (Truck 101) until booked.
- Initial cards: $3,700 · $1,054 ($2,646 direct costs · Before overhead) · 29.9% (440 of 1,470 planned miles).
- After confirmation: $4,800 · $2,100 (direct $2,700) · 4.7% (70 of 1,500 planned miles).
