# Phase 4 Requirements: Real voice (Vapi), Google Maps, proactive AI UX (phase-4)

**Goal:** Make the demo really talk.
1. The dispatcher speaks to FreightOS in the browser (Vapi Web SDK, voice only), and FreightOS answers and navigates the UI.
2. FreightOS places REAL outbound phone calls to drivers and brokers through Vapi. Live status and transcript appear in the call panel, and the outcome updates the app state.
3. The map moves to Google Maps with a clean code-defined style.
4. The "Needs you" notification tab is replaced by a proactive AI briefing stream.

Out of scope (owned by the user's teammate in a separate worktree):
- the core AI dispatch engine/logic
- the broker and shipper database
- the load search
- the main backend/data model
- the metrics card redesign (the user will do it)

Keep integration points clean and swappable.

Context: `../overview.md`. Builds on Phases 1–3 as delivered (Moveon design, the zustand store `freightos-demo`, `src/services/*`, the map adapter, the simulated call engine).

## Functional requirements

### Google Maps
- REQ-131 [always] The system shall render the dashboard map with Google Maps JS API through the existing map adapter, using `REACT_APP_GOOGLE_MAPS_API_KEY`.
- REQ-132 [always] The system shall apply a restrained code-defined style (light grey, POIs/transit hidden, key CA city labels legible), since no Map ID exists.
- REQ-133 [always] The system shall keep truck markers, heading, collision-free labels, routes, legend, stops, selection dimming and fit-to-fleet working as before.
- REQ-134 [unwanted] If the Google key fails to load or is rejected, then the system shall fall back to the MapLibre adapter automatically and log the reason.

### Dispatcher voice (Vapi Web)
- REQ-135 [event] When the dispatcher clicks "Talk to FreightOS" or the command bar mic, the system shall start a Vapi web voice session and show a live state (Connecting / Listening / FreightOS speaking) with a waveform. [unwanted partner REQ-136]
- REQ-136 [unwanted] If mic permission is denied or Vapi fails, then the system shall show "Voice unavailable, using demo voice" and run the existing simulated voice path.
- REQ-137 [always] The system shall give the voice assistant a live snapshot of the current app state (trucks, trips, offers, alerts, metrics) in its context at session start and on change (via add-message).
- REQ-138 [event] When the assistant invokes a client-side navigation tool, the system shall perform the UI action: select_truck(unit), open_decision(truck), open_call(id), show_view(map|schedule|fleet), open_metric(name), open_activity(), clear_selection().
- REQ-139 [event] When the dispatcher asks FreightOS to call a driver or broker by voice, the system shall show a confirm card "Call Ava Reed now?" before placing the real call.
- REQ-140 [always] The system shall show the live voice transcript in a compact caption area that does not cover the map controls.
- REQ-141 [event] When the dispatcher clicks the mic again or says "stop", the system shall end the voice session. (no failure mode)

### Real outbound calls (Vapi phone)
- REQ-142 [always] The system shall place outbound calls only through a thin backend proxy (`/api/voice/*`) that holds the Vapi private key (interpreted: minimal backend, the only backend work in this thread).
- REQ-143 [event] When a real call is started (driver instructions after booking, Truck 102 new-window text/call, a broker re-appointment or confirmation call, or a manual "Call" button), the system shall create a Vapi call with a task-specific transient assistant (objective, facts, allowed outcomes) to the configured number.
- REQ-144 [state] While a real call is active, the system shall show in the call panel: who is being called, the objective, status (Dialing / Ringing / In progress / Ended), a live transcript, and a "Live call" badge (not "Simulated").
- REQ-145 [event] When the dispatcher clicks "End call" or "Take over", the system shall end the Vapi call through the proxy (take over = end AI leg, mark "Dispatcher took over").
- REQ-146 [event] When a call ends, the system shall show the summary, extracted facts and outcome from Vapi analysis (structured data), and apply the outcome to the linked record (e.g. driver acknowledged, broker confirmed 15:30–16:30).
- REQ-147 [unwanted] If the call fails, is busy or isn't answered, then the system shall show the reason, leave the record unchanged, and offer "Retry" and "Run simulated call".
- REQ-148 [unwanted] If the same call action fires twice, then the system shall place only one call.
- REQ-149 [always] The system shall gate every real call behind an explicit user click or the confirm card. Nothing auto-dials without confirmation (interpreted from overview: real calls need a user-triggered or explicitly authorized action).
- REQ-150 [always] The system shall provide a "Calling" settings section with a Live / Simulated mode toggle and editable demo phone numbers per contact: drivers (default all → +16093021443) and brokers (Demo Pacific Broker, Desert Line Logistics, the Truck 102 broker; the user fills in the second phone).
- REQ-151 [always] The system shall keep contact lookup behind `contactsService` and the call-script/assistant builder behind `callScripts`, so the teammate's broker/shipper database and AI engine can replace them.

### Proactive AI briefing (replaces "Needs you")
- REQ-152 [always] The system shall remove the "Needs you" / "Updates" notification tab UI.
- REQ-153 [always] The system shall show a proactive AI briefing stream: short, timestamped, first-person updates ("I'm calling Ava with tomorrow's pickup", "Broker confirmed 15:30–16:30") that appear as events happen, each clickable to open its context.
- REQ-154 [always] The system shall visually set decision-required updates apart with a single inline action button (e.g. "Review load") instead of a separate tab (interpreted).
- REQ-155 [optional] Where "Speak updates" is on, the system shall speak new briefing items aloud (browser speech or Vapi say) (interpreted).
- REQ-156 [always] The system shall keep the attention strip and activity feed consistent with the briefing stream from the same store.

## Quality requirements
```
Q-20 Tag: Voice.Latency
     Scale: s from end of dispatcher speech to FreightOS audio reply
     Meter: human, 5 tries
     Must: < 3   Plan: < 1.5
Q-21 Tag: Voice.Navigation
     Scale: share of spoken navigation requests that perform the right UI action
     Meter: human, 10 commands
     Must: 8/10   Plan: 10/10
Q-22 Tag: Call.Safety
     Scale: real calls placed without an explicit click/confirm, or duplicated
     Meter: tester (with Simulated mode) + code review of call triggers
     Must: 0   Plan: 0
Q-23 Tag: Secrets.Exposure
     Scale: Vapi private key present in frontend bundle/network responses
     Meter: tester greps the built JS and network
     Must: 0   Plan: 0
Q-24 Tag: Call.Outcome
     Scale: real calls whose outcome correctly updates the linked record
     Meter: human, 3 calls
     Must: 2/3   Plan: 3/3
Q-25 Tag: Demo.Resilience
     Scale: stage demo completes when network/Vapi fails (falls back to simulated)
     Meter: tester in Simulated mode
     Must: yes   Plan: yes
```
