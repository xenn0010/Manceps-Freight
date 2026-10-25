# FreightOS · PRD

## Original problem statement
Build Phase 1 of FreightOS, a premium AI-dispatcher operations web app for a hackathon stage demo. Spec: /app/memory/product/overview.md, phase1/requirement.md (REQ-1..70), phase1/journeys.md (JRN-1..25, acceptance criteria). Frontend-only state (zustand + localStorage + Reset demo), all mock actions via src/services/, metrics derived from the ledger at $1.80/mi, idempotent transitions, everything external simulated, MapLibre + CARTO Positron behind a map adapter, pre-baked road GeoJSON, desktop 1280–1920. Design (user override): Ronas IT "Moveon" fleet dashboard (refs in /app/memory/product/design_ref).

## Architecture
- Frontend: React (CRA/craco), zustand + immer + persist (`freightos-demo`), framer-motion, maplibre-gl, shadcn popover/alert-dialog, sonner.
- `src/data/` seed (stable IDs, source, timestamps, status, proposal version), route geometry (baked from OSRM via scripts/bake_routes.py), call/AI scripts.
- `src/services/` engine.js (pure idempotent transitions + resumable tick), runtime.js (apply + 250 ms sim loop), dispatchService, callService, aiService (+aiScripts), voiceService, demoScript, notify, index.js.
- `src/map/` mapAdapter.js (provider interface) → maplibreAdapter.js; features.js builds routes/stops/trucks; collision-aware label placement for trucks and cities.
- Backend: default FastAPI kept; `/api/openapi.json` and `/api/docs` exposed. No backend features.

## Implemented (Oct 2026, Phase 1)
- Top bar (logo, company, 4 trucks, status summary, clock, Demo data, Talk to FreightOS mic, notifications, demo script, reset, user chip) plus pill nav (Dashboard/Fleet).
- KPI cards derived from the ledger, with Preview while awaiting broker, breakdown panels and the Current plan popover; attention strip; truck strip selector with generated dry-van images.
- Map: muted basemap, 7 key city labels, SVG truck markers with heading, legend, stop symbols, selection emphasis/dimming, fit fleet / selected truck, zoom controls, Map/Schedule switch (placeholder).
- Contextual right panel (one at a time with a back stack): truck, decision, call, chat, metric, activity, document, thread.
- Booking chain (Proposal ready → … → Driver acknowledged) with simulated broker call (pause/resume/take over), driver texts, reject/request changes/take over/hand back.
- Command bar with chips, scripted answers and fallback; simulated voice; demo script (N/→ next, Shift+R reset, D toggle); toasts; shimmer.
- Testing agent iteration_1: all 25 journeys pass.

## Backlog
- P0 Phase 2: Schedule view (F-12), Truck 102 exception resolution (F-13), execution updates (F-14), revised terms/proposal versions (F-15), feedback/rules (F-16).
- P1 Phase 3: Fleet setup records (F-17), conversational intake (F-18), AI settings (F-19).
- P2: real backend behind services/, Google Maps adapter, live telephony.


## Phase 2 — implemented (Oct 2026)
- Map: basemap labels hidden; 7 custom city labels (data-testid city-label-*) placed around truck icons (76px selected box), each other, then truck pills. BB-verified 0 overlaps at 1280/1440/1920 for fleet + each truck selected.
- Schedule view (ScheduleView.jsx + lib/schedule.js): per-truck rows, job/proposed/empty/rest/available/conflict/window blocks, Mon–Wed + 24h ranges with edge "continues" cues, Now marker, LA→Phoenix conflict preview.
- Truck 102 exception: simulated broker re-appointment call → 15:30–16:30, alert resolved, Ben Ortiz text + ack, delay history.
- Execution timeline via Advance time (map + schedule): deliveries, POD documents, releases, L-102 events after booking; "No more scheduled events".
- Revised terms: Request changes w/ target rate → broker counter $1,150 → proposal v2, review required, v1→v2 diff (contribution $376, +$1,096; booked cards $4,850/$2,150/4.7%).
- Written-terms-differ guard (demo scenario) blocks approve/booking until Reviewed.
- Feedback classifier (fact / this decision / rule with preview), correction log, AI instructions panel (rules).
- Truck 104 search progress + candidate info notification. Demo script extended to Truck 102 resolution + scenarios.
- Services: src/services/engine2.js, phase2Services.js (exceptionService, executionService, termsService, feedbackService). Seed: data/seed2.js.

## Backlog
- P1: Phase 3 per product docs; Fleet page depth; Google Maps adapter swap.
- P2: rule enforcement in AI candidate ranking; schedule drag-to-reschedule.


## Phase 3 — implemented (Oct 2026)
- Map follow-up: displaced city labels get a leader line to their dot; candidates avoid rendered route layers (queryRenderedFeatures), truck icons and other city labels.
- Fleet page (pages/Fleet.jsx): Carriers / Trucks / Drivers / Commitments tab pills with counts, light tables, row -> editable Sheet drawer (components/fleet/RecordDrawer.jsx) with validation (required, positive numbers, unique unit, window end > start).
- Truck availability and driver availability are separate fields; per-truck costPerMile feeds planLedger/summarize (lib/metrics.js truckCpm).
- Commitment window edits sync trip sortKey + stop labels; schedule derives L-103 and new-truck rows from parsed windows (lib/windows.js, lib/schedule.js).
- Guided intake (components/fleet/IntakeDialog.jsx): Carrier → Truck → Driver → Commitment steps, typed or simulated mic, deterministic parser (lib/intakeParser.js), confirmation card, Needs info gating, duplicate-unit warning with Edit-instead; creates linked records placed at city coordinates (lib/cities.js).
- AI settings sheet (components/shell/AiSettingsSheet.jsx): negotiation floor, max counter steps, auto-contact, approval locked on, driver tone, rules toggle/delete; applied in engine2 (counter limit/floor note, Ben text tone) and AI summary.
- Services: services/engine3.js + fleetService.js (fleetService, intakeService, settingsService). Seed: data/seed3.js; SCHEMA_VERSION 3.
- Testing: iteration_3 — 12/12 Phase-3 journeys pass; testing agent pruned stale map markers after Reset.
