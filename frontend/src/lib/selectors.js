export const openAttention = (data) =>
  Object.values(data.attention)
    .filter((a) => a.status === "open")
    .sort((a, b) => a.priority - b.priority);

export function headerSummary(data) {
  const t = Object.values(data.trucks);
  const transit = t.filter((x) => x.health === "on_track").length;
  const dock = t.filter((x) => ["working", "risk"].includes(x.health)).length;
  const off = t.filter((x) => x.health === "idle").length;
  return `${transit} in transit · ${dock} at docks · ${off} off duty`;
}

export function aiSummary(data) {
  const parts = [];
  if (Object.values(data.calls).some((c) => c.status === "in_progress")) parts.push("Calling Demo Pacific Broker");
  Object.values(data.proposals).forEach((p) => {
    if (p.driverStatus === "instructions_sent") parts.push("Waiting on Ava Reed");
  });
  const auto = data.settings?.autoContactBrokers !== false;
  Object.values(data.aiTasks).forEach((t) => parts.push(!auto && t.id === "TASK-104" ? "Truck 104 search paused · auto-contact off" : t.text));
  return parts.join(" · ");
}

export const STEPS = ["Proposal ready", "Terms approved", "Awaiting broker", "Booked", "Driver instructions sent", "Driver acknowledged"];

export function stepReached(p) {
  const base = { proposal_ready: 1, changes_requested: 1, rejected: 1, terms_approved: 2, awaiting_broker: 3, booked: 4 }[p.status] || 1;
  if (p.status !== "booked") return base;
  return base + (p.driverStatus === "instructions_sent" ? 1 : p.driverStatus === "acknowledged" ? 2 : 0);
}

export const STATUS_LABEL = {
  proposal_ready: "Proposal ready", changes_requested: "Changes requested", rejected: "Rejected",
  terms_approved: "Terms approved", awaiting_broker: "Awaiting broker", booked: "Booked",
};

export const isAwaitingConfirmation = (p) => ["terms_approved", "awaiting_broker"].includes(p.status);

export function truckCommitments(data, truckId) {
  const items = [];
  Object.values(data.trips)
    .filter((t) => t.truckId === truckId && t.id !== data.trucks[truckId].currentTripId && ["active", "confirmed"].includes(t.status))
    .forEach((t) => items.push({ kind: "trip", sortKey: t.sortKey, trip: t }));
  Object.values(data.offers)
    .filter((o) => o.truckId === truckId && ["proposed", "awaiting_broker"].includes(o.status))
    .forEach((o) => items.push({ kind: "offer", sortKey: o.sortKey, offer: o }));
  Object.values(data.segments)
    .filter((s) => s.truckId === truckId && s.status === "planned")
    .forEach((s) => items.push({ kind: "segment", sortKey: s.sortKey, segment: s }));
  return items.sort((a, b) => a.sortKey - b.sortKey);
}
