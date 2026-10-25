import { ROUTES } from "../data/seed";
import { BEN_ACK, BEN_TEXT, REAPPT_CONTACT, REAPPT_OBJECTIVE } from "../data/scripts";
import { hhmm, money, signedMoney, stamp } from "../lib/format";
import { offerEconomics, truckCpm } from "../lib/metrics";

// Phase 2 transitions: exception re-appointment, execution timeline, revised terms, terms guard, feedback.
const iso = () => new Date().toISOString();
export const TIMING2 = { counter: 2500, benText: 1800, benAck: 2800 };
const TONE_TEXT = {
  Friendly: BEN_TEXT,
  Concise: "L-201 Stockton now 15:30–16:30. Reply OK.",
  Formal: "Please note the L-201 Stockton appointment is rescheduled to 15:30–16:30 today. Kindly reply OK to confirm.",
};

export function log(d, key, entry) {
  if (d.data.activity.some((a) => a.key === key)) return false;
  d.data.seq += 1;
  d.data.activity.push({ id: `ACT-${d.data.seq}`, key, seq: d.data.seq, at: d.clockMin, createdAt: iso(), ...entry });
  return true;
}
export function notify(d, key, n) {
  if (d.data.notifications.some((x) => x.key === key)) return;
  d.data.seq += 1;
  d.data.notifications.push({ id: `N-${d.data.seq}`, key, at: d.clockMin, read: false, status: "open", createdAt: iso(), ...n });
}
export function resolveAttention(d, attId, status) {
  const a = d.data.attention[attId];
  if (a && a.status === "open") a.status = status;
  d.data.notifications.forEach((n) => {
    if (n.id === `N-${attId}`) {
      n.status = "resolved";
      n.read = true;
    }
  });
}
const pushMsg = (d, convId, id, from, text, extra = {}) => {
  const conv = d.data.conversations[convId];
  if (!conv || conv.messages.some((m) => m.id === id)) return;
  conv.messages.push({ id, from, at: d.clockMin, text, ...extra });
};

// ---- Truck 102 exception ----
export function startReappointment(d, now, events) {
  const id = "CALL-L201-REAPPT";
  if (d.data.calls[id] || d.data.attention["ATT-102"].status !== "open") return false;
  d.data.calls[id] = {
    id, kind: "reappointment", script: "reappt", tripId: "L-201", truckId: "T-102", contact: REAPPT_CONTACT, objective: REAPPT_OBJECTIVE,
    status: "in_progress", paused: false, lineIndex: 0, lastLineAt: now - 1100, startedAt: d.clockMin, outcome: null, source: "ai", createdAt: iso(),
  };
  d.data.trips["L-201"].reapptCallId = id;
  log(d, `reappt-start-${id}`, { source: "ai", text: "Calling Central Valley Brokers for a new L-201 appointment", link: { type: "call", id } });
  notify(d, `reappt-start-${id}`, { group: "updates", title: "Calling broker · Truck 102", body: "Requesting 15:30–16:30 in Stockton", link: { type: "call", id } });
  events.push({ kind: "info", title: "Calling broker for new appointment", body: "Central Valley Brokers (simulated)", link: { type: "call", id } });
  return true;
}

export function completeReappointment(d, c, now, events) {
  const t = d.data.trips["L-201"];
  if (t.revision) return;
  c.outcome = c.outcome || "New window 15:30–16:30 confirmed";
  t.revision = { window: "15:30–16:30", confirmedAt: d.clockMin, source: "Broker call · Central Valley Brokers", driverStatus: "none", driverStatusAt: now };
  t.delivery = { ...t.delivery, window: "Mon 15:30–16:30" };
  t.delayHistory.push({ at: d.clockMin, label: "Revised window confirmed", value: "Mon 15:30–16:30", source: "Broker call (simulated)" });
  const truck = d.data.trucks["T-102"];
  Object.assign(truck, { health: "working", pill: "Rescheduled", statusShort: "On track · rescheduled", status: "Loading in Fresno · rescheduled" });
  resolveAttention(d, "ATT-102", "resolved");
  delete d.data.aiTasks["TASK-L201"];
  log(d, "reappt-done", { source: "broker", text: "New window 15:30–16:30 confirmed for L-201 · alert resolved", link: { type: "truck", id: "T-102" } });
  notify(d, "reappt-done", { group: "updates", title: "Truck 102 rescheduled", body: "Stockton 15:30–16:30 confirmed", link: { type: "truck", id: "T-102" } });
  events.push({ kind: "success", title: "New window 15:30–16:30 confirmed", body: "L-201 on track · rescheduled", link: { type: "truck", id: "T-102" } });
}

function tickBen(d, now, events) {
  const r = d.data.trips["L-201"].revision;
  if (!r) return;
  if (r.driverStatus === "none" && d.data.calling?.mode !== "live" && now - r.driverStatusAt >= TIMING2.benText) {
    r.driverStatus = "sent";
    r.driverStatusAt = now;
    pushMsg(d, "CONV-DRV-102", "MSG-BEN-REAPPT", "ai", TONE_TEXT[d.data.settings?.driverTone] || BEN_TEXT);
    log(d, "ben-text", { source: "ai", text: "Texted Ben Ortiz the new 15:30–16:30 window", link: { type: "thread", id: "CONV-DRV-102" } });
    events.push({ kind: "info", title: "Text sent to Ben Ortiz", body: "New Stockton window (simulated)", link: { type: "thread", id: "CONV-DRV-102" } });
  } else if (r.driverStatus === "sent" && now - r.driverStatusAt >= TIMING2.benAck) {
    r.driverStatus = "acknowledged";
    pushMsg(d, "CONV-DRV-102", "MSG-BEN-ACK", "driver", BEN_ACK);
    log(d, "ben-ack", { source: "driver", text: "Ben Ortiz acknowledged the new window", link: { type: "thread", id: "CONV-DRV-102" } });
    notify(d, "ben-ack", { group: "updates", title: "Ben Ortiz acknowledged", body: "Stockton 15:30–16:30", link: { type: "thread", id: "CONV-DRV-102" } });
  }
}

// ---- Revised terms ----
function tickCounter(d, now, events) {
  const p = d.data.proposals["P-1"];
  if (p.status !== "changes_requested" || !p.targetRate || p.counteredFor === p.version) return;
  if (now - p.statusChangedAt < TIMING2.counter) return;
  const settings = d.data.settings || {};
  if (p.version - 1 >= (settings.maxCounterSteps ?? 2)) {
    p.counteredFor = p.version;
    p.status = "proposal_ready";
    p.statusChangedAt = now;
    log(d, `counter-limit-${p.id}-v${p.version}`, { source: "ai", text: `No new counter: max counter steps (${settings.maxCounterSteps}) reached`, link: { type: "decision", id: p.id } });
    events.push({ kind: "info", title: "Counter limit reached", body: "Change it in AI settings", link: { type: "decision", id: p.id } });
    return;
  }
  const o = d.data.offers[p.offerId];
  const prev = o.rate;
  const counter = Math.round((prev + p.targetRate) / 2 / 50) * 50;
  const perMile = counter / (o.loadedMiles + o.emptyToPickup + o.emptyAfter);
  const floorNote = settings.negotiationFloor ? (perMile < settings.negotiationFloor ? ` · below your $${settings.negotiationFloor.toFixed(2)}/mi floor` : ` · $${perMile.toFixed(2)}/mi clears your $${settings.negotiationFloor.toFixed(2)}/mi floor`) : "";
  p.counteredFor = p.version;
  p.version += 1;
  p.versions.push({ version: p.version, rate: counter, prevRate: prev, target: p.targetRate, at: d.clockMin, source: "Broker counter (simulated)" });
  o.rate = counter;
  p.status = "proposal_ready";
  p.reviewRequired = true;
  p.statusChangedAt = now;
  p.history.push({ status: "proposal_ready", at: d.clockMin, version: p.version });
  const doc = d.data.documents[o.documentId];
  doc.fields[0] = { ...doc.fields[0], offer: `${money(counter)} all-in`, written: `${money(counter)} all-in` };
  const e = offerEconomics(o, d.data.segments[p.replacesSegmentId], truckCpm(d.data, o.truckId));
  const att = d.data.attention["ATT-101"];
  if (att.status === "open") att.summary = `v${p.version} · ${signedMoney(e.delta)} vs empty return · review required`;
  log(d, `counter-${p.id}-v${p.version}`, { source: "broker", text: `Broker countered ${money(counter)} (asked ${money(p.targetRate)}) · proposal v${p.version}${floorNote}`, link: { type: "decision", id: p.id } });
  notify(d, `counter-${p.id}-v${p.version}`, { group: "needs_you", title: `Review required · O-1 v${p.version}`, body: `Broker countered ${money(counter)}`, link: { type: "decision", id: p.id } });
  events.push({ kind: "info", title: `Broker countered ${money(counter)}`, body: `Proposal v${p.version} needs your review`, link: { type: "decision", id: p.id } });
}

export function simulateTermsDiffer(d, events) {
  const p = d.data.proposals["P-1"];
  if (p.termsFlag === "differ" || ["booked", "rejected"].includes(p.status)) return false;
  const doc = d.data.documents["DOC-RC-1"];
  const rate = d.data.offers["O-1"].rate;
  doc.fields[0] = { ...doc.fields[0], written: `${money(rate - 50)} all-in` };
  doc.matches = false;
  p.termsFlag = "differ";
  log(d, `terms-differ-${p.version}`, { source: "ai", text: `Written terms differ: rate con says ${money(rate - 50)}`, link: { type: "document", id: doc.id } });
  notify(d, `terms-differ-${p.version}`, { group: "needs_you", title: "Written terms differ · O-1", body: "Booking blocked until you review", link: { type: "decision", id: p.id } });
  events.push({ kind: "info", title: "Written terms differ", body: "Booking blocked until reviewed", link: { type: "decision", id: p.id } });
  return true;
}

export function reviewTerms(d, events) {
  const p = d.data.proposals["P-1"];
  if (p.termsFlag !== "differ") return false;
  p.termsFlag = "reviewed";
  log(d, `terms-reviewed-${p.version}`, { source: "dispatcher", text: "You reviewed the differing written terms", link: { type: "document", id: "DOC-RC-1" } });
  events.push({ kind: "info", title: "Terms reviewed", body: "Booking unblocked" });
  return true;
}

// ---- Execution timeline ----
const EXEC_LABEL = { picked_up: "Picked up", in_transit: "In transit", delivered: "Delivered", pod: "Document received", released: "Released", on_duty: "On duty" };
const routeOf = (t) => (t.routes || []).find((r) => r.kind === "loaded");
const posOn = (t, f) => {
  const c = ROUTES[routeOf(t).id].coordinates;
  return c[Math.min(c.length - 1, Math.round((c.length - 1) * f))];
};

function closeLateAlert(d, t, events) {
  const a = d.data.attention["ATT-102"];
  if (!a || a.status !== "open") return;
  const text = `Delivered late · ${hhmm(d.clockMin)} (window 14:00–15:00)`;
  t.delayHistory.push({ at: d.clockMin, label: "Delivered late", value: `${hhmm(d.clockMin)} vs 14:00–15:00`, source: "Driver call (simulated)" });
  resolveAttention(d, "ATT-102", "delivered_late");
  a.resolution = text;
  delete d.data.aiTasks["TASK-L201"];
  log(d, "late-L-201", { source: "system", text: `Truck 102 alert closed: ${text}`, link: { type: "truck", id: "T-102" } });
  notify(d, "late-L-201", { group: "updates", title: "Truck 102 alert closed", body: text, link: { type: "truck", id: "T-102" } });
  events.push({ kind: "info", title: "Truck 102 alert closed", body: text, link: { type: "truck", id: "T-102" } });
}

function applyEvent(d, ev, events) {
  ev.status = "done";
  ev.appliedAt = d.clockMin;
  const t = ev.tripId && d.data.trips[ev.tripId];
  const truck = d.data.trucks[ev.truckId];
  const set = (o) => Object.assign(truck, o);
  if (t) {
    t.exec = ev.kind === "pod" ? "document_received" : ev.kind;
    t.execLog = [...(t.execLog || []), { label: EXEC_LABEL[ev.kind], at: d.clockMin, source: ev.source }];
  }
  if (ev.kind === "picked_up" && t) set({ position: posOn(t, 0.04), pill: "In transit", health: "on_track", statusShort: `${t.id} picked up`, status: `Picked up ${t.id}` });
  if (ev.kind === "in_transit" && t) set({ position: posOn(t, 0.5), pill: "In transit", health: "on_track", statusShort: `${t.id} in transit`, status: `In transit · ${t.id}` });
  if (ev.kind === "delivered" && t) {
    const late = t.id === "L-201" && !t.revision;
    set({ position: posOn(t, 1), pill: late ? "Late" : "Delivered", health: late ? "risk" : "working", statusShort: late ? "Delivered late · missed window" : `${t.id} delivered`, status: `Delivered ${t.id}` });
    if (late) closeLateAlert(d, t, events);
  }
  if (ev.kind === "pod" && t) {
    const docId = `POD-${t.id}`;
    d.data.documents[docId] = {
      id: docId, kind: "pod", title: `Proof of delivery · ${t.id}`, from: d.data.drivers[truck.driverId].name, fileName: `POD_${t.id}.jpg`,
      receivedAt: d.clockMin, status: "received", matches: true, source: "driver", createdAt: iso(),
      fields: [
        { label: "Trip", written: `${t.id} · ${t.origin} → ${t.destination}` },
        { label: "Delivered", written: stamp(d.clockMin - 15) },
        { label: "Consignee signature", written: "Signed · no exceptions" },
        { label: "Pieces", written: "As tendered" },
      ],
    };
    t.podId = docId;
    if (t.id === "L-301") {
      set({ health: "idle", pill: "Available", statusShort: "Available · finding next work", status: "Available in Oakland · finding next work" });
      log(d, "t103-available", { source: "ai", text: "Truck 103 available · finding next work", link: { type: "truck", id: "T-103" } });
    }
    if (t.id === "L-102") set({ position: ROUTES["R-O1-EMPTY-SF"].coordinates.slice(-1)[0], pill: "In SF yard", statusShort: "In SF · rest before L-103", status: "In SF yard · rest before L-103" });
    if (t.id === "L-201") set({ health: "idle", pill: "Available", statusShort: "Available in Stockton", status: "Available in Stockton" });
  }
  if (ev.kind === "released") set({ pill: "Released", statusShort: "Released · driver rest to Tue 07:00", status: "Released in Vernon · driver resting" });
  if (ev.kind === "on_duty") set({ health: "idle", pill: "On duty", statusShort: "On duty · AI searching", status: "On duty in San Jose" });
  const convId = `CONV-DRV-${truck.unit}`;
  pushMsg(d, convId, `MSG-${ev.id}`, "driver", ev.text, { channel: ev.source });
  log(d, `ev-${ev.id}`, { source: "driver", text: `${ev.text} (${ev.source.toLowerCase()})`, link: t?.podId && ev.kind === "pod" ? { type: "document", id: t.podId } : { type: "truck", id: truck.id } });
  notify(d, `ev-${ev.id}`, { group: "updates", title: `${EXEC_LABEL[ev.kind]} · Truck ${truck.unit}`, body: ev.text, link: ev.kind === "pod" ? { type: "document", id: t.podId } : { type: "truck", id: truck.id } });
  events.push({ kind: "info", title: `${stamp(d.clockMin)} · ${EXEC_LABEL[ev.kind]}`, body: ev.text, link: { type: "truck", id: truck.id } });
}

const eligible = (d, ev) => ev.status === "pending" && (!ev.tripId || !!d.data.trips[ev.tripId]);

export function advanceTime(d, events) {
  const next = d.data.events.filter((e) => eligible(d, e)).sort((a, b) => a.at - b.at)[0];
  if (!next) {
    events.push({ kind: "info", title: "No more scheduled events", body: "The clock stays where it is" });
    return false;
  }
  d.clockMin = Math.max(d.clockMin, next.at);
  applyEvent(d, next, events);
  return true;
}

// ---- Feedback ----
export function correctFact(d, fact) {
  const rec = d.data[fact.entity][fact.id];
  const old = rec[fact.field];
  if (old === fact.value) return false;
  rec[fact.field] = fact.value;
  d.data.seq += 1;
  d.data.corrections.push({ id: `COR-${d.data.seq}`, ...fact, old, at: d.clockMin, source: "dispatcher" });
  log(d, `cor-${d.data.seq}`, { source: "dispatcher", text: `Corrected ${fact.label}: ${old} → ${fact.value}`, link: { type: "truck", id: fact.truckId } });
  return true;
}

export function addRule(d, rule, events) {
  d.data.seq += 1;
  const id = `RULE-${d.data.seq}`;
  d.data.rules[id] = { id, ...rule, at: d.clockMin, status: "active", createdAt: iso() };
  log(d, `rule-${id}`, { source: "dispatcher", text: `New AI rule (${rule.scopeLabel}): ${rule.text}`, link: { type: "rules", id: null } });
  notify(d, `rule-${id}`, { group: "updates", title: "AI instruction added", body: rule.text, link: { type: "rules", id: null } });
  events.push({ kind: "success", title: "Rule applied", body: rule.text, link: { type: "rules", id: null } });
}

export function oneOff(d, ctx, text) {
  const p = ctx.proposalId && d.data.proposals[ctx.proposalId];
  if (p) p.oneOffNotes = [...(p.oneOffNotes || []), { text, at: d.clockMin }];
  d.data.seq += 1;
  log(d, `oneoff-${d.data.seq}`, { source: "dispatcher", text: `Noted for this decision only: “${text}”`, link: p ? { type: "decision", id: p.id } : { type: "activity", id: null } });
}

export function tick2(d, now, events) {
  tickBen(d, now, events);
  tickCounter(d, now, events);
}
