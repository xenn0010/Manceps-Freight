import { useStore } from "../store/useStore";
import { openLink } from "../lib/links";
import { aiService } from "./aiService";
import { dispatchService } from "./dispatchService";
import { executionService, exceptionService, termsService } from "./phase2Services";

const S = () => useStore.getState();

export const DEMO_STEPS = [
  { id: "glance", label: "Fleet overview", hint: "Cards, map, attention", run: () => { S().closePanel(); S().setMapMode("map"); S().requestFit(); } },
  { id: "truck103", label: "Inspect Truck 103", hint: "On track · ETA 11:30", run: () => openLink({ type: "truck", id: "T-103" }) },
  { id: "ask", label: "Ask “What needs me?”", hint: "Scripted AI answer", run: () => aiService.ask("What needs me?") },
  { id: "decision", label: "Open return-load decision", hint: "+$1,046 vs empty return", run: () => openLink({ type: "decision", id: "P-1" }) },
  { id: "approve", label: "Approve and request confirmation", hint: "Starts broker call", run: () => { openLink({ type: "decision", id: "P-1" }); dispatchService.approve("P-1"); } },
  { id: "call", label: "Watch the broker call", hint: "Live transcript", run: () => { const id = S().data.proposals["P-1"].callId; if (id) openLink({ type: "call", id }); } },
  { id: "effect", label: "Booking effect on Empty driving", hint: "29.9% → 4.7%", run: () => S().openPanel("metric", "empty") },
  { id: "ack", label: "Driver acknowledgment", hint: "Stepper complete", run: () => openLink({ type: "decision", id: "P-1" }) },
  { id: "schedule", label: "Schedule view", hint: "L-102 booked, empty return gone", run: () => { openLink({ type: "truck", id: "T-101" }); S().setMapMode("schedule"); } },
  { id: "advance", label: "Advance time · Truck 103 delivers", hint: "11:30 delivery, then POD", run: () => { S().setMapMode("map"); executionService.advanceTime(); executionService.advanceTime(); openLink({ type: "truck", id: "T-103" }); } },
  { id: "exception", label: "Open Truck 102 exception", hint: "ETA 15:30 vs 14:00–15:00", run: () => openLink({ type: "truck", id: "T-102" }) },
  { id: "resolve", label: "Call broker · resolve exception", hint: "New window 15:30–16:30", run: () => { exceptionService.callBrokerForAppointment(); const id = S().data.trips["L-201"].reapptCallId; if (id) openLink({ type: "call", id }); } },
];

export const DEMO_SCENARIOS = [
  { id: "revise", label: "Revised terms · ask $1,200", run: () => { openLink({ type: "decision", id: "P-1" }); dispatchService.requestChanges("P-1", "Ask for $1,200", 1200); } },
  { id: "terms-differ", label: "Written terms differ", run: () => { openLink({ type: "decision", id: "P-1" }); termsService.simulateTermsDiffer(); } },
];

export const demoScript = {
  runStep(i) {
    const step = DEMO_STEPS[i];
    if (!step) return;
    step.run();
    S().mutate((s) => void (s.ui.demoStep = Math.min(i + 1, DEMO_STEPS.length)));
  },
  next() {
    const i = S().ui.demoStep;
    if (i >= DEMO_STEPS.length) return;
    this.runStep(i);
  },
};
