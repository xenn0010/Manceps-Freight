import { CALL_CONTACT, CALL_OBJECTIVE, DRIVER_ACK, DRIVER_INSTRUCTIONS, callScript } from "../data/scripts";
import { buildAnswer } from "./aiScripts";
import { tick2, completeReappointment, reviewTerms } from "./engine2";

// Pure, idempotent state transitions applied to an immer draft of the store.
export const TIMING = { termsToCall: 900, line: 1700, bookToInstructions: 1800, instructionsToAck: 2800, aiReply: 1100 };

const iso = () => new Date().toISOString();
const OPEN = ["proposal_ready", "changes_requested"];

export function log(d, key, entry) {
  if (d.data.activity.some((a) => a.key === key)) return false;
  d.data.seq += 1;
  d.data.activity.push({ id: `ACT-${d.data.seq}`, key, seq: d.data.seq, at: d.clockMin, createdAt: iso(), ...entry });
  return true;
}

function notify(d, key, n) {
  if (d.data.notifications.some((x) => x.key === key)) return;
  d.data.seq += 1;
  d.data.notifications.push({ id: `N-${d.data.seq}`, key, at: d.clockMin, read: false, status: "open", createdAt: iso(), ...n });
}

function setStatus(p, status, now, clock) {
  p.status = status;
  p.statusChangedAt = now;
  p.updatedAt = iso();
  p.history.push({ status, at: clock });
}

function resolveAttention(d, attId, status) {
  const a = d.data.attention[attId];
  if (a && a.status === "open") a.status = status;
  d.data.notifications.forEach((n) => {
    if (n.id === `N-${attId}`) {
      n.status = "resolved";
      n.read = true;
    }
  });
}

const canDecide = (p) => p && OPEN.includes(p.status) && p.handledBy === "ai";

export function approve(d, pid, now, events) {
  const p = d.data.proposals[pid];
  if (!canDecide(p) || p.termsFlag === "differ") return false;
  const approvalId = `APR-${pid}-v${p.version}`;
  if (p.approvals.some((a) => a.id === approvalId)) return false;
  d.clockMin += 1;
  p.reviewRequired = false;
  p.approvals.push({ id: approvalId, version: p.version, at: d.clockMin, by: "dispatcher", createdAt: iso() });
  setStatus(p, "terms_approved", now, d.clockMin);
  log(d, `approve-${approvalId}`, { source: "dispatcher", text: "You approved O-1 terms · $1,100 LA→Oakland", link: { type: "decision", id: pid } });
  events.push({ kind: "success", title: "Terms approved", body: "Requesting broker confirmation" });
  return true;
}

export function reject(d, pid, reason, now, events) {
  const p = d.data.proposals[pid];
  if (!canDecide(p) || !reason?.trim()) return false;
  d.clockMin += 1;
  p.rejectReason = reason.trim();
  setStatus(p, "rejected", now, d.clockMin);
  d.data.offers[p.offerId].status = "rejected";
  resolveAttention(d, "ATT-101", "dismissed");
  log(d, `reject-${pid}-v${p.version}`, { source: "dispatcher", text: `You rejected O-1 · “${p.rejectReason}”`, link: { type: "decision", id: pid } });
  events.push({ kind: "info", title: "Proposal rejected", body: "Truck 101 keeps the empty return" });
  return true;
}

export function requestChanges(d, pid, note, now, events, target) {
  const p = d.data.proposals[pid];
  if (!p || p.status !== "proposal_ready" || p.handledBy !== "ai" || !(note?.trim() || target)) return false;
  d.clockMin += 1;
  p.changeNote = note?.trim() || `Target ${target}`;
  p.targetRate = Number(target) || null;
  setStatus(p, "changes_requested", now, d.clockMin);
  log(d, `changes-${pid}-v${p.version}`, { source: "dispatcher", text: `Changes requested on O-1 v${p.version}${p.targetRate ? ` · target $${p.targetRate.toLocaleString("en-US")}` : ""} · “${p.changeNote}”`, link: { type: "decision", id: pid } });
  events.push({ kind: "info", title: "Changes requested", body: p.targetRate ? "Asking the broker for a better rate" : "Saved with the proposal" });
  return true;
}

export function reviewAndBook(d, now, events) {
  if (!reviewTerms(d, events)) return false;
  const p = d.data.proposals["P-1"];
  const c = p.callId && d.data.calls[p.callId];
  if (c && c.status === "completed" && p.status === "awaiting_broker") {
    c.outcome = "Confirmed in writing · reviewed";
    book(d, p, now, events);
  }
  return true;
}

export function takeOverProposal(d, pid, events) {
  const p = d.data.proposals[pid];
  if (!p || p.handledBy === "dispatcher" || ["booked", "rejected"].includes(p.status)) return false;
  p.handledBy = "dispatcher";
  d.data.seq += 1;
  log(d, `takeover-${pid}-${d.data.seq}`, { source: "dispatcher", text: "You took over the Truck 101 return load · AI paused", link: { type: "decision", id: pid } });
  events.push({ kind: "info", title: "You're handling this", body: "AI paused on this task" });
  return true;
}

export function handBack(d, pid, events) {
  const p = d.data.proposals[pid];
  const call = p?.callId && d.data.calls[p.callId];
  if (!p || p.handledBy !== "dispatcher" || call?.status === "taken_over") return false;
  p.handledBy = "ai";
  d.data.seq += 1;
  log(d, `handback-${pid}-${d.data.seq}`, { source: "dispatcher", text: "Handed the Truck 101 return load back to AI", link: { type: "decision", id: pid } });
  events.push({ kind: "info", title: "AI resumed", body: "FreightOS is handling this again" });
  return true;
}

function startCall(d, p, now, events) {
  const callId = `CALL-${p.id}-v${p.version}`;
  if (d.data.calls[callId]) return;
  d.data.calls[callId] = {
    id: callId, proposalId: p.id, offerId: p.offerId, contact: CALL_CONTACT, objective: CALL_OBJECTIVE, script: "o1", rate: d.data.offers[p.offerId].rate,
    status: "in_progress", paused: false, lineIndex: 0, lastLineAt: now - TIMING.line + 600,
    startedAt: d.clockMin, outcome: null, source: "ai", createdAt: iso(),
  };
  p.callId = callId;
  setStatus(p, "awaiting_broker", now, d.clockMin);
  d.data.offers[p.offerId].status = "awaiting_broker";
  log(d, `call-start-${callId}`, { source: "ai", text: "Calling Demo Pacific Broker to confirm O-1", link: { type: "call", id: callId } });
  notify(d, `call-start-${callId}`, { group: "updates", title: "Calling Demo Pacific Broker", body: "Confirming O-1 at $1,100", link: { type: "call", id: callId } });
  events.push({ kind: "info", title: "Awaiting broker", body: "FreightOS is calling Demo Pacific Broker", link: { type: "call", id: callId } });
}

export function book(d, p, now, events) {
  if (p.status !== "awaiting_broker" || p.termsFlag === "differ") return;
  const o = d.data.offers[p.offerId];
  d.clockMin += 2;
  setStatus(p, "booked", now, d.clockMin);
  o.status = "booked";
  if (!d.data.trips[o.tripId]) {
    d.data.trips[o.tripId] = {
      id: o.tripId, truckId: o.truckId, origin: o.origin, destination: o.destination, status: "confirmed", phase: "Booked",
      revenue: o.rate, loadedMiles: o.loadedMiles, emptyMiles: o.emptyToPickup + o.emptyAfter, sortKey: o.sortKey,
      broker: o.broker, pickup: o.pickup, delivery: o.delivery, routes: o.routes, stops: o.stops, offerId: o.id,
      source: "ai", createdAt: iso(), updatedAt: iso(),
    };
  }
  const seg = d.data.segments[p.replacesSegmentId];
  if (seg) seg.status = "replaced";
  d.data.documents[o.documentId].status = "signed";
  resolveAttention(d, "ATT-101", "resolved");
  log(d, `booked-${p.id}-v${p.version}`, { source: "broker", text: "Booked O-1 as L-102 · LA→Oakland $1,100 · Truck 101", link: { type: "decision", id: p.id } });
  notify(d, `booked-${p.id}-v${p.version}`, { group: "updates", title: "Booked · Truck 101 LA→Oakland", body: "Broker confirmed in writing · $1,100", link: { type: "decision", id: p.id } });
  events.push({ kind: "success", title: "Booked · L-102", body: "Broker confirmed in writing. Metrics updated.", link: { type: "decision", id: p.id } });
}

function pushDriverMessage(d, id, from, text) {
  const conv = d.data.conversations["CONV-DRV-101"];
  if (conv.messages.some((m) => m.id === id)) return;
  conv.messages.push({ id, from, at: d.clockMin, text });
}

function sendInstructions(d, p, now, events) {
  if (p.driverStatus !== "none") return;
  d.clockMin += 1;
  p.driverStatus = "instructions_sent";
  p.driverStatusAt = now;
  p.history.push({ status: "driver_instructions_sent", at: d.clockMin });
  pushDriverMessage(d, `MSG-INSTR-${p.id}-v${p.version}`, "ai", DRIVER_INSTRUCTIONS);
  log(d, `instr-${p.id}-v${p.version}`, { source: "ai", text: "Driver instructions sent to Ava Reed", link: { type: "thread", id: "CONV-DRV-101" } });
  events.push({ kind: "info", title: "Driver instructions sent", body: "Texted Ava Reed (simulated)", link: { type: "thread", id: "CONV-DRV-101" } });
}

function acknowledge(d, p, events) {
  if (p.driverStatus !== "instructions_sent") return;
  d.clockMin += 2;
  p.driverStatus = "acknowledged";
  p.history.push({ status: "driver_acknowledged", at: d.clockMin });
  pushDriverMessage(d, `MSG-ACK-${p.id}-v${p.version}`, "driver", DRIVER_ACK);
  log(d, `ack-${p.id}-v${p.version}`, { source: "driver", text: "Ava Reed acknowledged L-102", link: { type: "thread", id: "CONV-DRV-101" } });
  notify(d, `ack-${p.id}-v${p.version}`, { group: "updates", title: "Driver acknowledged · Ava Reed", body: "L-102 Tue LA→Oakland", link: { type: "thread", id: "CONV-DRV-101" } });
  events.push({ kind: "success", title: "Driver acknowledged", body: "Ava Reed confirmed L-102", link: { type: "thread", id: "CONV-DRV-101" } });
}

export function pauseCall(d, id, paused, now) {
  const c = d.data.calls[id];
  if (!c || c.status !== "in_progress" || c.paused === paused) return false;
  c.paused = paused;
  if (!paused) c.lastLineAt = now;
  return true;
}

export function takeOverCall(d, id, events) {
  const c = d.data.calls[id];
  if (!c || c.status !== "in_progress") return false;
  c.status = "taken_over";
  c.paused = false;
  c.outcome = "Dispatcher took over";
  if (c.proposalId) d.data.proposals[c.proposalId].handledBy = "dispatcher";
  log(d, `call-takeover-${id}`, { source: "dispatcher", text: "You took over the broker call · AI left the call", link: { type: "call", id } });
  events.push({ kind: "info", title: "Dispatcher took over", body: "AI left the call" });
  return true;
}

export function logBrokerConfirmation(d, id, now, events) {
  const c = d.data.calls[id];
  if (!c || c.status !== "taken_over" || c.manualConfirmed) return false;
  c.manualConfirmed = true;
  if (c.kind === "reappointment") {
    c.outcome = "Dispatcher took over · New window 15:30–16:30 confirmed";
    completeReappointment(d, c, now, events);
    return true;
  }
  c.outcome = "Dispatcher took over · confirmed in writing";
  book(d, d.data.proposals[c.proposalId], now, events);
  return true;
}

// Advances every simulated timer that is due. Safe to call repeatedly and after reloads.
export function tick(d, now, events) {
  Object.values(d.data.proposals).forEach((p) => {
    if (p.status === "terms_approved" && p.handledBy === "ai" && now - p.statusChangedAt >= TIMING.termsToCall) startCall(d, p, now, events);
    if (p.status === "booked" && p.driverStatus === "none" && now - p.statusChangedAt >= TIMING.bookToInstructions) sendInstructions(d, p, now, events);
    if (p.driverStatus === "instructions_sent" && now - p.driverStatusAt >= TIMING.instructionsToAck) acknowledge(d, p, events);
  });
  Object.values(d.data.calls).forEach((c) => {
    if (c.status !== "in_progress" || c.paused || now - c.lastLineAt < TIMING.line) return;
    const total = callScript(c).lines.length;
    c.lineIndex = Math.min(c.lineIndex + 1, total);
    c.lastLineAt = now;
    if (c.lineIndex >= total) {
      c.status = "completed";
      c.endedAt = d.clockMin;
      if (c.kind === "reappointment") return completeReappointment(d, c, now, events);
      const p = d.data.proposals[c.proposalId];
      c.outcome = p.termsFlag === "differ" ? "Written terms differ · review required" : "Confirmed in writing";
      book(d, p, now, events);
    }
  });
  tick2(d, now, events);
  const msgs = d.chat.messages;
  const lastMsg = msgs[msgs.length - 1];
  if (lastMsg && lastMsg.role === "user" && now - lastMsg.ts >= TIMING.aiReply) {
    msgs.push({ id: `${lastMsg.id}-reply`, role: "ai", ts: now, at: d.clockMin, ...buildAnswer(d.data, lastMsg.text) });
  }
}
