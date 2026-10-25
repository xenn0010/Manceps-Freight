import Vapi from "@vapi-ai/web";
import { useStore } from "../store/useStore";
import { openLink } from "../lib/links";
import { openAttention } from "../lib/selectors";
import { planLedger, summarize } from "../lib/metrics";
import { hhmm, money } from "../lib/format";
import { contactsService } from "./contactsService";
import { liveCallService } from "./liveCallService";

// Dispatcher voice via Vapi Web. Answers only from the state snapshot; navigation runs through client-side tools.
const KEY = process.env.REACT_APP_VAPI_PUBLIC_KEY;
const S = () => useStore.getState();
let vapi = null;
let unsub = null;
let snapTimer = 0;
let lastSnap = "";
let failCb = null;

export function stateSnapshot(data, clockMin) {
  const m = summarize(planLedger(data), data.carrier.costPerMile);
  const trucks = Object.values(data.trucks).map((t) => `- Truck ${t.unit} (${data.drivers[t.driverId]?.name}): ${t.statusShort || t.status}; at ${t.location}; truck available ${t.truckAvailableAt}; driver available ${data.drivers[t.driverId]?.availableAt}`);
  const att = openAttention(data).map((a) => `- ${a.title} · Truck ${data.trucks[a.truckId]?.unit}: ${a.summary || ""}`);
  const props = Object.values(data.proposals).map((p) => `- Proposal ${p.id} (offer ${p.offerId}, Truck ${data.trucks[p.truckId]?.unit}): status ${p.status}, rate ${money(data.offers[p.offerId].rate)}, version ${p.version}`);
  const calls = Object.values(data.liveCalls).slice(-3).map((c) => `- Call ${c.id} with ${c.contact.name}: ${c.status}${c.outcome ? `, ${c.outcome}` : ""}`);
  return [
    `Time: Mon ${hhmm(clockMin)} PT. Carrier: ${data.carrier.name}. Calling mode: ${data.calling.mode}.`,
    "Trucks:", ...trucks,
    "Needs attention:", ...(att.length ? att : ["- nothing open"]),
    "Proposals:", ...props,
    `Metrics: booked revenue ${money(m.revenue)}, after trip costs ${money(m.afterCosts)}, empty driving ${(m.emptyPct * 100 || 0).toFixed(1)}%.`,
    ...(calls.length ? ["Recent calls:", ...calls] : []),
  ].join("\n");
}

const PROMPT = `You are FreightOS, the voice of an AI dispatch assistant, talking with the human dispatcher of Demo West Freight.
Answer ONLY from the STATE below and later "STATE UPDATE" messages. If something isn't in the state, say you don't have it. Never invent loads, rates or times.
Keep replies to one or two short spoken sentences. You explain and navigate; you do not book loads or make dispatch decisions.
Use tools to drive the screen whenever the dispatcher asks to see something: select_truck, open_decision, open_call, show_view, open_metric, open_activity, clear_selection.
When asked to phone a driver or broker, call request_call. The dispatcher must confirm on screen, so say "I've put the call up for you to confirm" and never claim you dialed.
If the dispatcher says stop, goodbye or that's all, say goodbye briefly and end the call.`;

const fn = (name, description, properties = {}, required = []) => ({ type: "function", async: true, function: { name, description, parameters: { type: "object", properties, required } } });
const TOOLS = [
  fn("select_truck", "Select a truck on the map and open its panel", { unit: { type: "string", description: "Truck unit number, e.g. 102" } }, ["unit"]),
  fn("open_decision", "Open the load decision/proposal for a truck", { truck: { type: "string", description: "Truck unit, e.g. 101" } }, ["truck"]),
  fn("open_call", "Open a phone call panel", { id: { type: "string", description: "Call id, or empty for the latest call" } }),
  fn("show_view", "Switch the main view", { view: { type: "string", enum: ["map", "schedule", "fleet"] } }, ["view"]),
  fn("open_metric", "Open a metric breakdown", { name: { type: "string", enum: ["revenue", "costs", "empty"] } }, ["name"]),
  fn("open_activity", "Open the AI activity feed"),
  fn("clear_selection", "Clear the selected truck and close panels"),
  fn("request_call", "Ask the dispatcher to confirm a phone call to a driver or broker", { contact: { type: "string", description: "Name, company or truck" }, purpose: { type: "string" } }, ["contact", "purpose"]),
];

const truckId = (u) => `T-${String(u || "").replace(/\D/g, "")}`;
function taskFor(c, purpose, data) {
  const p = data.proposals["P-1"];
  if (c.id === "D-102" && data.trips["L-201"].revision) return ["driver_window", { type: "trip", id: "L-201" }];
  if (c.id === "D-101" && p?.status === "booked") return ["driver_instructions", { type: "proposal", id: "P-1", version: p.version }];
  if (c.id === "BRK-CENTRAL") return ["broker_reappointment", { type: "trip", id: "L-201" }];
  if (c.id === "BRK-PACIFIC" && p?.status === "terms_approved") return ["broker_confirmation", { type: "proposal", id: "P-1", version: p.version }];
  return ["manual", null, purpose];
}

const HANDLERS = {
  select_truck: ({ unit }) => openLink({ type: "truck", id: truckId(unit) }),
  open_decision: ({ truck }) => {
    const p = Object.values(S().data.proposals).find((x) => x.truckId === truckId(truck));
    p ? openLink({ type: "decision", id: p.id }) : openLink({ type: "truck", id: truckId(truck) });
  },
  open_call: ({ id }) => {
    const d = S().data;
    if (d.liveCalls[id]) return openLink({ type: "livecall", id });
    if (d.calls[id]) return openLink({ type: "call", id });
    const last = Object.values(d.liveCalls).pop() || Object.values(d.calls).pop();
    last && openLink({ type: last.task ? "livecall" : "call", id: last.id });
  },
  show_view: ({ view }) => {
    if (view === "fleet") return S().setView("fleet");
    S().setView("dashboard");
    S().setMapMode(view === "schedule" ? "schedule" : "map");
  },
  open_metric: ({ name }) => openLink({ type: "metric", id: ["revenue", "costs", "empty"].includes(name) ? name : "empty" }),
  open_activity: () => openLink({ type: "activity" }),
  clear_selection: () => S().closePanel(),
  request_call: ({ contact, purpose }) => {
    const data = S().data;
    const c = contactsService.find(data, `${contact} ${purpose || ""}`);
    if (!c) return;
    const [taskType, linked] = taskFor(c, purpose, data);
    liveCallService.request(c.id, taskType, linked, purpose);
  },
};

const setVoice = (patch) => S().setVoice({ ...S().transient.voice, ...patch });

function onMessage(m) {
  if (m.type === "transcript") {
    const v = S().transient.voice;
    const line = { role: m.role === "user" ? "you" : "ai", text: m.transcript };
    const finals = (v.captions || []).filter((c) => c.final);
    setVoice({ transcript: m.transcript, captions: [...finals, { ...line, final: m.transcriptType === "final" }].slice(-3) });
  }
  if (m.type === "tool-calls")
    (m.toolCallList || []).forEach((t) => {
      let args = t.function?.arguments || {};
      try {
        if (typeof args === "string") args = JSON.parse(args || "{}");
      } catch {
        args = {};
      }
      HANDLERS[t.function?.name]?.(args);
    });
}

function bind() {
  vapi.on("call-start", () => {
    setVoice({ status: "listening" });
    unsub = useStore.subscribe((s) => s.data, () => {
      clearTimeout(snapTimer);
      snapTimer = setTimeout(() => {
        const snap = stateSnapshot(S().data, S().clockMin);
        if (snap === lastSnap) return;
        lastSnap = snap;
        vapi.send({ type: "add-message", message: { role: "system", content: `STATE UPDATE\n${snap}` }, triggerResponseEnabled: false });
      }, 1500);
    });
  });
  vapi.on("speech-start", () => setVoice({ status: "speaking" }));
  vapi.on("speech-end", () => S().transient.voice.status === "speaking" && setVoice({ status: "listening" }));
  vapi.on("message", onMessage);
  vapi.on("call-end", () => {
    unsub?.();
    clearTimeout(snapTimer);
    S().setVoice({ status: "idle", transcript: "", captions: [], mode: "live" });
  });
  vapi.on("error", (e) => {
    const st = S().transient.voice.status;
    if (st === "connecting") failCb?.(e?.error?.message || e?.message || "Vapi error");
  });
}

export const vapiVoice = {
  available: () => !!KEY,
  async start(onFail) {
    failCb = onFail;
    S().setVoice({ status: "connecting", transcript: "", captions: [], mode: "live" });
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach((t) => t.stop());
      if (!vapi) {
        vapi = new Vapi(KEY);
        bind();
      }
      lastSnap = stateSnapshot(S().data, S().clockMin);
      await vapi.start({
        name: "FreightOS Dispatcher",
        firstMessage: "FreightOS here. What do you need?",
        model: { provider: "openai", model: "gpt-4.1-mini", temperature: 0.3, messages: [{ role: "system", content: `${PROMPT}\n\nSTATE\n${lastSnap}` }], tools: TOOLS },
        voice: { provider: "vapi", voiceId: "Elliot" },
        transcriber: { provider: "deepgram", model: "nova-3", language: "en" },
        clientMessages: ["tool-calls", "transcript", "status-update", "speech-update"],
        endCallFunctionEnabled: true,
        maxDurationSeconds: 600,
        silenceTimeoutSeconds: 45,
      });
    } catch (e) {
      onFail(e?.message || "Microphone or Vapi unavailable");
    }
  },
  stop() {
    vapi?.stop();
    unsub?.();
    S().setVoice({ status: "idle", transcript: "", captions: [], mode: "live" });
  },
};
