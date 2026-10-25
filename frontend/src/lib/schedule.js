import { parsePoint, parseWindow } from "./windows";

const b = (id, truckId, start, end, kind, label, link, lane) => ({ id, truckId, start, end, kind, label, link, lane });
const SEEDED = ["T-101", "T-102", "T-103", "T-104"];

// Trucks added in Fleet: their commitments from parsed windows, plus availability.
function genericRow(data, t) {
  const truck = { type: "truck", id: t.id };
  const from = parsePoint(t.truckAvailableAt) ?? 360;
  const blocks = from > 360 ? [b(`REST-${t.id}`, t.id, 360, from, "rest", `Unavailable until ${t.truckAvailableAt}`, truck)] : [];
  Object.values(data.trips)
    .filter((x) => x.truckId === t.id && ["active", "confirmed"].includes(x.status))
    .forEach((x) => {
      const pw = parseWindow(x.pickup.window);
      const dw = parseWindow(x.delivery.window);
      if (pw && dw) blocks.push(b(x.id, t.id, pw.startMin, dw.endMin, "job", `${x.id} · ${x.origin} → ${x.destination} · PU ${pw.start}–${pw.end}`, truck));
    });
  blocks.push(b(`AV-${t.id}`, t.id, Math.max(from, ...blocks.filter((x) => x.kind === "job").map((x) => x.end)), 4320, "available", "Available", truck));
  return { truckId: t.id, blocks };
}

// Derives schedule blocks per truck from the same store records the map uses.
export function scheduleRows(data, ui) {
  const t101 = "T-101";
  const seg = data.segments["SEG-101-RET"];
  const o1 = data.offers["O-1"];
  const p = data.proposals["P-1"];
  const booked = !!data.trips["L-102"];
  const live = ["proposed", "awaiting_broker"].includes(o1.status);
  const truck = (id) => ({ type: "truck", id });
  const r101 = [
    b("L-101", t101, 360, 720, "job", "L-101 · Unloading in Vernon", truck(t101)),
    b("REST-101-A", t101, 720, 1860, "rest", "Driver rest · Ava available Tue 07:00", truck(t101)),
  ];
  if (seg.status === "planned") r101.push(b("SEG-101-RET", t101, 1860, 2280, "empty", "Empty return LA → SF · 400 mi", truck(t101), live ? 1 : undefined));
  if (live) r101.push(b("O-1", t101, 1890, 2520, "proposed", `Proposed · O-1 LA → Oakland ${"$" + o1.rate.toLocaleString("en-US")}`, { type: "decision", id: p.id }, seg.status === "planned" ? 0 : undefined));
  if (booked) r101.push(b("L-102", t101, 1890, 2520, "job", `L-102 Booked · LA → Oakland $${o1.rate.toLocaleString("en-US")}`, truck(t101)));
  const l103 = data.trips["L-103"];
  const pw103 = parseWindow(l103.pickup.window);
  const dw103 = parseWindow(l103.delivery.window);
  const s103 = pw103 ? pw103.startMin : 3360;
  const e103 = dw103 ? dw103.endMin : 3960;
  r101.push(
    b("REST-101-B", t101, 2520, 3120, "rest", "10 h rest", truck(t101)),
    b("BUF-101", t101, 3120, Math.max(3120, s103), "rest", "4 h buffer", truck(t101)),
    b("L-103", t101, s103, e103, "job", `L-103 · SF → LA · PU ${pw103 ? `${pw103.start}–${pw103.end}` : l103.pickup.window} · Protected`, truck(t101)),
    b("AV-101", t101, e103, 4560, "available", "Available", truck(t101))
  );
  if (ui.inspectAlt && live) r101.push(b("O-2", t101, 2040, 3420, "conflict", "LA → Phoenix $1,600 · conflicts with L-103", { type: "decision", id: p.id }, 1));

  const l201 = data.trips["L-201"];
  const fixed = !!l201.revision;
  const r102 = [
    b("L-201-LOAD", "T-102", 360, 750, fixed ? "job" : "risk", "L-201 · Loading (release 12:30)", truck("T-102"), 0),
    b("L-201", "T-102", 750, 930, fixed ? "job" : "risk", "L-201 → Stockton · ETA 15:30", truck("T-102"), 0),
    fixed
      ? b("WIN-201", "T-102", 930, 990, "window", "Window 15:30–16:30", truck("T-102"), 1)
      : b("WIN-201", "T-102", 840, 900, "conflict", "Window 14:00–15:00 · missed", truck("T-102"), 1),
    b("AV-102", "T-102", 990, 4320, "available", "Available", truck("T-102")),
  ];
  const r103 = [
    b("L-301", "T-103", 540, 690, "job", "L-301 → Oakland · ETA 11:30", truck("T-103")),
    b("AV-103", "T-103", 690, 4320, "available", "Available · finding next work", truck("T-103")),
  ];
  const r104 = [
    b("REST-104", "T-104", 360, 1860, "rest", "Off duty · until Tue 07:00", truck("T-104")),
    b("AV-104", "T-104", 1860, 4320, "available", "Available · AI searching", truck("T-104")),
  ];
  return [
    { truckId: t101, blocks: r101 },
    { truckId: "T-102", blocks: r102 },
    { truckId: "T-103", blocks: r103 },
    { truckId: "T-104", blocks: r104 },
    ...Object.values(data.trucks).filter((t) => !SEEDED.includes(t.id)).map((t) => genericRow(data, t)),
  ];
}
