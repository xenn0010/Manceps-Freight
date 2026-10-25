import { log, notify, completeReappointment } from "./engine2";
import { book, sendInstructions, acknowledge } from "./engine";

// Phase 4: live/simulated phone calls and their outcomes. Every apply is idempotent.
const iso = () => new Date().toISOString();

export function startLiveCall(d, rec) {
  if (d.data.liveCalls[rec.id]) return false;
  d.data.liveCalls[rec.id] = { ...rec, createdAt: iso(), applied: false };
  log(d, `lc-start-${rec.id}`, { source: "ai", text: `${rec.mode === "live" ? "Live" : "Simulated"} call to ${rec.contact.name}: ${rec.task.objective}`, link: { type: "livecall", id: rec.id } });
  notify(d, `lc-start-${rec.id}`, { group: "updates", title: `Calling ${rec.contact.name}`, body: rec.task.objective, say: `I'm calling ${rec.contact.name}${rec.contact.company && rec.contact.role === "broker" ? ` at ${rec.contact.company}` : ""}: ${rec.task.objective.charAt(0).toLowerCase()}${rec.task.objective.slice(1)}.`, link: { type: "livecall", id: rec.id } });
  return true;
}

export function patchLiveCall(d, id, patch) {
  const c = d.data.liveCalls[id];
  if (!c) return false;
  Object.assign(c, patch);
  return true;
}

const APPLY = {
  driver_instructions(d, c, sd, now, events) {
    const p = d.data.proposals[c.linked?.id];
    if (!p || p.status !== "booked" || !sd.acknowledged) return null;
    if (p.driverStatus === "none") sendInstructions(d, p, now, events);
    acknowledge(d, p, events);
    return "Driver acknowledged";
  },
  driver_window(d, c, sd, now) {
    const r = d.data.trips["L-201"].revision;
    if (!r || !sd.acknowledged) return null;
    r.driverStatus = "acknowledged";
    r.driverStatusAt = now;
    notify(d, "ben-ack", { group: "updates", title: "Ben Ortiz acknowledged", body: "Stockton 15:30–16:30", link: { type: "truck", id: "T-102" } });
    return "Ben Ortiz acknowledged";
  },
  broker_reappointment(d, c, sd, now, events) {
    if (!sd.confirmed && !sd.new_window) return null;
    completeReappointment(d, { outcome: "" }, now, events);
    return `New window ${sd.new_window || "15:30–16:30"} confirmed`;
  },
  broker_confirmation(d, c, sd, now, events) {
    const p = d.data.proposals[c.linked?.id];
    if (!p || !sd.confirmed) return null;
    if (p.status === "terms_approved") p.status = "awaiting_broker";
    book(d, p, now, events);
    return p.status === "booked" ? "Broker confirmed · booked" : "Confirmed · booking blocked for review";
  },
  manual: () => "Call completed",
};

export function finishLiveCall(d, id, result, now, events) {
  const c = d.data.liveCalls[id];
  if (!c || c.applied) return false;
  Object.assign(c, result, { applied: true, endedAt: d.clockMin });
  if (c.status === "failed") {
    log(d, `lc-fail-${id}-${c.attempt || 1}`, { source: "system", text: `Call to ${c.contact.name} failed: ${c.error}`, link: { type: "livecall", id } });
    notify(d, `lc-fail-${id}-${c.attempt || 1}`, { group: "needs_you", title: `Call failed · ${c.contact.name}`, body: c.error, say: `My call to ${c.contact.name} didn't go through (${c.error}). Nothing changed.`, link: { type: "livecall", id } });
    return true;
  }
  if (c.takenOver) {
    c.outcome = "Dispatcher took over";
    return true;
  }
  const out = (APPLY[c.task.type] || APPLY.manual)(d, c, c.structuredData || {}, now, events);
  c.outcome = out || "No outcome recorded · record unchanged";
  log(d, `lc-done-${id}`, { source: "ai", text: `Call with ${c.contact.name} ended: ${c.outcome}`, link: { type: "livecall", id } });
  notify(d, `lc-done-${id}`, { group: "updates", title: `Call ended · ${c.contact.name}`, body: c.outcome, say: `${c.contact.name}: ${c.outcome.charAt(0).toLowerCase()}${c.outcome.slice(1)}.`, link: { type: "livecall", id } });
  return true;
}
