import { toast } from "sonner";
import { useStore } from "../store/useStore";
import { run } from "./runtime";
import * as e4 from "./engine4";
import { contactsService } from "./contactsService";
import { callScripts } from "./callScripts";
import { openLink } from "../lib/links";

const API = `${process.env.REACT_APP_BACKEND_URL}/api/voice`;
const S = () => useStore.getState();
const timers = {};
const inflight = new Set();
const STATUS = { queued: "dialing", ringing: "ringing", "in-progress": "in_progress", forwarding: "in_progress", ended: "ended" };
const FAILED = /busy|did-not-answer|no-answer|failed|error|invalid|rejected|voicemail|unreachable|not-found/i;
const ACTIVE = ["dialing", "ringing", "in_progress"];
const human = (r) => ({ "customer-busy": "Line busy", "customer-did-not-answer": "No answer", "customer-ended-call-before-answer": "Declined" })[r] || (r || "Unknown error").replace(/[-.]/g, " ");

const patch = (id, p) => run((d) => e4.patchLiveCall(d, id, p));
const finish = (id, result) => {
  clearTimeout(timers[id]);
  run((d, now, ev) => e4.finishLiveCall(d, id, result, now, ev));
};

async function api(path, body) {
  const r = await fetch(`${API}${path}`, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : undefined);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.detail || `HTTP ${r.status}`);
  return j;
}

async function poll(id, endedPolls = 0) {
  const c = S().data.liveCalls[id];
  if (!c || c.applied) return;
  try {
    const v = await api(`/calls/${c.vapiId}`);
    const status = STATUS[v.status] || c.status;
    patch(id, { status, transcript: v.transcript, summary: v.summary, listenUrl: v.listenUrl });
    if (status === "ended") {
      const userSpoke = v.transcript.some((l) => l.role === "contact");
      if (FAILED.test(v.endedReason || "") || (!userSpoke && endedPolls === 0 && !v.structuredData && /customer|twilio|vonage/.test(v.endedReason || "")))
        return finish(id, { status: "failed", error: human(v.endedReason) });
      if (v.structuredData || endedPolls >= 10) return finish(id, { status: "ended", summary: v.summary, structuredData: v.structuredData || {}, endedReason: v.endedReason });
      timers[id] = setTimeout(() => poll(id, endedPolls + 1), 1500);
      return;
    }
  } catch (e) {
    if (endedPolls > 6) return finish(id, { status: "failed", error: e.message });
    endedPolls += 1;
  }
  timers[id] = setTimeout(() => poll(id, endedPolls), 1500);
}

async function dial(id) {
  const c = S().data.liveCalls[id];
  try {
    const r = await api("/calls", { contact: c.contact, task: c.task, linked: c.linked, idempotencyKey: `${id}-${c.attempt}` });
    patch(id, { vapiId: r.id, to: r.to, status: "dialing" });
    timers[id] = setTimeout(() => poll(id), 1200);
  } catch (e) {
    finish(id, { status: "failed", error: e.message });
  }
}

function simulate(id) {
  const c = S().data.liveCalls[id];
  const lines = callScripts.simulatedLines(c.task);
  const steps = [() => patch(id, { status: "ringing" }), () => patch(id, { status: "in_progress" })];
  lines.forEach((_, i) => steps.push(() => patch(id, { transcript: lines.slice(0, i + 1) })));
  steps.push(() => finish(id, { status: "ended", ...callScripts.simulatedResult(c.task) }));
  const next = (i) => {
    if (i >= steps.length || S().data.liveCalls[id]?.applied) return;
    steps[i]();
    timers[id] = setTimeout(() => next(i + 1), i < 2 ? 800 : 1100);
  };
  timers[id] = setTimeout(() => next(0), 600);
}

function reopen(id, mode) {
  clearTimeout(timers[id]);
  const c = S().data.liveCalls[id];
  run((d) => e4.patchLiveCall(d, id, { status: "dialing", mode, transcript: [], error: null, applied: false, structuredData: null, summary: null, outcome: null, vapiId: null, attempt: (c.attempt || 1) + 1 }));
  mode === "live" ? dial(id) : simulate(id);
}

export const liveCallService = {
  request: (contactId, taskType = "manual", linked = null, purpose = "") => S().setTransient({ callConfirm: { contactId, taskType, linked, purpose } }),
  cancelRequest: () => S().setTransient({ callConfirm: null }),
  setMode: (mode) => S().mutate((s) => void (s.data.calling.mode = mode)),
  setNumber: (id, number) => S().mutate((s) => void (s.data.calling.numbers[id] = number)),
  start({ contactId, taskType = "manual", linked = null, purpose = "" }) {
    const data = S().data;
    const key = `${taskType}:${contactId}:${linked?.id || "-"}:${linked?.version || 0}`;
    const existing = Object.values(data.liveCalls).find((c) => c.key === key && c.status !== "failed");
    if (existing || inflight.has(key)) {
      if (existing) openLink({ type: "livecall", id: existing.id });
      return existing?.id || null;
    }
    inflight.add(key);
    setTimeout(() => inflight.delete(key), 2000);
    const contact = contactsService.get(data, contactId);
    const task = callScripts.build(taskType, data, contact, purpose);
    const mode = data.calling.mode;
    const id = `LC-${data.seq + 1}-${Date.now().toString(36)}`;
    run((d) => e4.startLiveCall(d, { id, key, attempt: 1, contact, task, linked, mode, status: "dialing", transcript: [], startedAt: d.clockMin }));
    openLink({ type: "livecall", id });
    mode === "live" ? dial(id) : simulate(id);
    return id;
  },
  async end(id, takeOver = false) {
    const c = S().data.liveCalls[id];
    if (!c || c.applied) return;
    clearTimeout(timers[id]);
    if (c.mode === "live" && c.vapiId) await api(`/calls/${c.vapiId}/end`, {}).catch((e) => toast.error("Couldn't end the call", { description: e.message }));
    finish(id, { status: "ended", takenOver: takeOver, summary: takeOver ? "Dispatcher took over the call" : "Ended by dispatcher" });
  },
  retry: (id) => reopen(id, S().data.calling.mode),
  runSimulated: (id) => reopen(id, "simulated"),
  resume() {
    Object.values(S().data.liveCalls).forEach((c) => {
      if (!ACTIVE.includes(c.status) || c.applied) return;
      if (c.mode === "live" && c.vapiId) poll(c.id);
      else finish(c.id, { status: "ended", ...callScripts.simulatedResult(c.task) });
    });
  },
  config: () => api("/config").catch(() => ({ configured: false, demoDriverPhone: "" })),
};
