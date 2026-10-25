# Phase 4 Journeys

Earlier journeys stay valid except those superseded below. Live-call journeys are human-verified (a real phone is needed). The tester uses Simulated mode for automated runs.

- **JRN-56** Google map. Steps: open the dashboard. Expected: a Google basemap with the light restrained style and Google attribution, the 7 city labels readable, 4 trucks with labels and no overlaps, routes, legend, and selection dimming working.
- **JRN-57** Map fallback. Steps: run with an invalid Google key (dev check). Expected: the MapLibre map renders and the app keeps working.
- **JRN-58** Voice session (human). Steps: click "Talk to FreightOS", allow the mic, and say "What needs me today?". Expected: the state goes Connecting → Listening, and FreightOS answers aloud about the Truck 102 delay and the Truck 101 return load, with live captions shown.
- **JRN-59** Voice navigation (human). Steps: say "Show me Truck 102", then "Open the return load for 101", then "Switch to schedule", then "Show empty driving". Expected: each UI action happens (truck selected, decision opened, schedule view, metric breakdown).
- **JRN-60** Voice fallback. Steps: deny mic permission and click the mic. Expected: "Voice unavailable, using demo voice" appears and the simulated voice path runs.
- **JRN-61** Real driver call (human). Steps: set Calling to Live, book O-1, and click "Call Ava" (or confirm the card). Expected:
  - The phone +16093021443 rings, and the panel shows "Live call", Dialing → In progress, and a live transcript.
  - When the callee says they confirm, the call ends with an outcome and Ava's status becomes "Driver acknowledged".
- **JRN-62** Voice-requested call (human). Steps: say "Call Ben about the new window". Expected: the confirm card "Call Ben Ortiz now?" appears. Confirming dials; cancelling places no call.
- **JRN-63** Real broker call (human). Steps: set the broker phone, open the Truck 102 exception, and click "Call broker". Expected: a live call asks for a new appointment. An outcome of 15:30–16:30 resolves the alert and keeps the delay history.
- **JRN-64** Call failure. Steps: call an invalid or unanswered number. Expected: the reason is shown, the record is unchanged, and Retry and "Run simulated call" are offered.
- **JRN-65** No double dial. Steps: triple-click Call. Expected: one call is placed.
- **JRN-66** Secrets. Steps: inspect the frontend bundle and network. Expected: the Vapi private key is never present; only the public key appears client-side.
- **JRN-67** Simulated mode. Steps: set Calling to Simulated and run the full stage demo. Expected: the full stage demo works as in Phases 1–3 with "Simulated" badges.
- **JRN-68** Briefing replaces Needs you. Steps: open the dashboard and run the demo. Expected:
  - No "Needs you" / "Updates" tab exists.
  - A briefing stream shows first-person updates as events occur, each clicking through to its context.
  - The decision item shows one inline action ("Review load"). superseded: [JRN-20]
- **JRN-69** Speak updates. Steps: turn "Speak updates" on and trigger a booking. Expected: the new briefing item is spoken aloud.
- **JRN-70** Calling settings. Steps: edit Ava's demo number and reload. Expected: the number persists, and Reset restores the defaults.
