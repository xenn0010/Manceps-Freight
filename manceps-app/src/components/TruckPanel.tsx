import { agentOf } from "../agents";
import { agentName, driverFirst, openChat, pick, showToast } from "../actions";
import { endCall, scriptFor, startCall } from "../demo";
import type { TruckView } from "../live/mappers";
import { fmtClock, nameParts } from "../logic/derive";
import { getState, setState, useAppState, type CallState, type TruckTab } from "../store";
import { DriverTab, EquipTab, LoadTab, RouteTab } from "./truckTabs";
import { AgentAvatar, DemoTag, ENTER, FONT, GLASS, ICON_CLOSE, Icon, Segmented } from "./ui";

const TABS: [TruckTab, string][] = [["load", "Load"], ["driver", "Driver"], ["route", "Route"], ["truck", "Truck"]];
/** Seconds of ringing before the driver picks up. */
export const RING_S = 3;
/** Transcript lines shown while the agent is on a call. */
const TRANSCRIPT_LINES = 3;
const PHONE = "M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2";
const HANG_UP = "M3 14c5-5 13-5 18 0l-2.5 2.5-3-1.5v-3a12 12 0 0 0-7 0v3l-3 1.5z";

function callAgent(id: string): void {
  if (getState().perm.drivers === "off") {
    showToast(agentName() + " can't call drivers · change it in Permissions", true);
    setState({ chat: true, permOpen: true });
  } else startCall(id, "agent");
}

function joinCall(): void {
  const c = getState().call;
  if (!c) return;
  endCall();
  startCall(c.id, "you");
}

function CallActions({ id }: { id: string }): JSX.Element {
  const name = agentOf(useAppState().agent).name;
  return (
    <div style={{ display: "flex", gap: 8, marginTop: 2 }}>
      <button type="button" className="hv-primary" onClick={() => startCall(id, "you")} style={{ flex: 1, height: 40, border: 0, borderRadius: 6, background: "#010D1D", color: "#FFFFFF", font: `14px ${FONT}`, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", gap: 8, transition: "background .2s cubic-bezier(.4,0,.2,1)" }}><Icon d={PHONE} join />Call {driverFirst(id)}</button>
      <button type="button" className="hv-blue-border" onClick={() => callAgent(id)} style={{ flex: 1, height: 40, border: "1px solid rgba(1,13,29,.14)", borderRadius: 6, background: "#FFFFFF", color: "#010D1D", font: `14px ${FONT}`, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}><AgentAvatar size={20} />{name} calls<DemoTag /></button>
    </div>
  );
}

function callText(c: CallState, first: string, mute: boolean): { title: string; sub: string } {
  const el = Math.floor((Date.now() - c.t0) / 1000);
  if (c.mode === "agent") return { title: agentName() + " is talking to " + first, sub: "Live · " + fmtClock(el) };
  const live = el >= RING_S;
  return { title: (live ? "On call with " : "Calling ") + first, sub: live ? fmtClock(el - RING_S) + (mute ? " · muted" : "") : "Ringing…" };
}

function CallCard({ id, c }: { id: string; c: CallState }): JSX.Element {
  const s = useAppState(), you = c.mode === "you", first = driverFirst(id), initials = nameParts(first).initials;
  const txt = callText(c, first, s.mute);
  const lines = you ? [] : scriptFor(id).slice(Math.max(0, c.step - (TRANSCRIPT_LINES - 1)), c.step + 1);
  return (
    <div style={{ borderRadius: 8, background: you ? "#010D1D" : "#EEF4FA", color: you ? "#F1F5F9" : "#010D1D", padding: 12, display: "flex", flexDirection: "column", gap: 10, animation: "up .2s cubic-bezier(0,0,.2,1)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <span style={{ position: "relative", width: 32, height: 32, flexShrink: 0, borderRadius: "50%", display: "grid", placeItems: "center", fontSize: 12, background: you ? "#2272AD" : "#010D1D", color: "#FFFFFF" }}>
          <span style={{ position: "absolute", inset: 0, borderRadius: "50%", background: "#2272AD", opacity: 0.5, animation: "ping 1.6s cubic-bezier(0,0,.2,1) infinite" }} />
          <span style={{ position: "relative" }}>{initials}</span>
        </span>
        <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", lineHeight: 1.25 }}>
          <span style={{ fontSize: 14, display: "flex", alignItems: "center", gap: 8 }}>{txt.title}<DemoTag dark={you} /></span>
          <span style={{ fontSize: 12, opacity: 0.75, fontVariantNumeric: "tabular-nums" }}>{txt.sub}</span>
        </div>
        {you && <button type="button" onClick={() => setState((x) => ({ mute: !x.mute }))} aria-label="Mute" aria-pressed={s.mute} style={{ width: 36, height: 36, border: 0, borderRadius: "50%", cursor: "pointer", display: "grid", placeItems: "center", background: s.mute ? "#D9443A" : "rgba(255,255,255,.14)", color: "#FFFFFF" }}><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" /></svg></button>}
        <button type="button" onClick={endCall} aria-label="End call" style={{ width: 36, height: 36, border: 0, borderRadius: "50%", cursor: "pointer", display: "grid", placeItems: "center", background: "#D9443A", color: "#FFFFFF" }}><Icon d={HANG_UP} join /></button>
      </div>
      {!you && (
        <>
          <div style={{ display: "flex", flexDirection: "column", gap: 6, fontSize: 13, lineHeight: 1.45 }}>
            {lines.map(([who, text]) => (
              <div key={who + text} style={{ display: "flex", gap: 8, animation: "up .2s cubic-bezier(0,0,.2,1)" }}>
                <span style={{ flexShrink: 0, width: 58, color: "#64748A", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{who}</span>
                <span className="pretty">{text}</span>
              </div>
            ))}
          </div>
          <button type="button" className="hv-faint" onClick={joinCall} style={{ height: 34, border: 0, borderRadius: 6, background: "#FFFFFF", color: "#010D1D", font: `13px ${FONT}`, cursor: "pointer" }}>Join the call</button>
        </>
      )}
    </div>
  );
}

function askAbout(unit: string): void {
  openChat();
  setState({ text: "How's " + unit + " doing?" });
}

/** Right-hand panel for the selected truck: live load, driver, route and equipment tabs, plus demo calls. */
export function TruckPanel({ id }: { id: string }): JSX.Element | null {
  const s = useAppState(), t: TruckView | undefined = s.trucks.find((x) => x.id === id), c = s.call && s.call.id === id ? s.call : null;
  if (!t) return null;
  return (
    <div style={{ position: "absolute", right: 20, top: 88, width: 360, maxHeight: "calc(100vh - 112px)", display: "flex", flexDirection: "column", borderRadius: 12, ...GLASS, overflow: "hidden", animation: ENTER }}>
      <div style={{ height: 92, flexShrink: 0, background: "linear-gradient(180deg,rgba(255,255,255,.35),rgba(214,228,240,.45))", display: "flex", alignItems: "flex-end", justifyContent: "center", position: "relative" }}>
        <div style={{ width: "88%", height: 62, marginBottom: 8, background: "url(/assets/truck-blue.png) center bottom / contain no-repeat" }} />
        <button type="button" className="hv-white" onClick={() => pick(null)} aria-label="Close" style={{ position: "absolute", right: 8, top: 8, width: 32, height: 32, border: 0, borderRadius: 6, background: "rgba(255,255,255,.85)", cursor: "pointer", display: "grid", placeItems: "center", color: "#3D4A5C" }}><Icon d={ICON_CLOSE} /></button>
      </div>
      <div style={{ padding: "14px 16px 16px", display: "flex", flexDirection: "column", gap: 10, overflow: "auto", minHeight: 0 }}>
        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8 }}>
          <span style={{ fontSize: 20, letterSpacing: "-0.01em" }}>Truck {t.unit}</span>
          {t.equipment && <span style={{ fontSize: 12, padding: "3px 8px", borderRadius: 5, background: "#F1F5F9", color: "#3D4A5C" }}>{t.equipment}</span>}
        </div>
        <span style={{ fontSize: 14, color: "#3D4A5C" }}>{t.carrier}</span>
        <Segmented items={TABS} value={s.tab} onChange={(k) => setState({ tab: k })} style={{ marginTop: 2 }} />
        {s.tab === "load" && <LoadTab />}
        {s.tab === "driver" && <DriverTab t={t} />}
        {s.tab === "truck" && <EquipTab t={t} />}
        {s.tab === "route" && <RouteTab />}
        {c ? <CallCard id={id} c={c} /> : <CallActions id={id} />}
        <button type="button" className="hv-soft" onClick={() => askAbout(t.unit)} style={{ height: 36, marginTop: 2, border: 0, borderRadius: 6, background: "rgba(1,13,29,.05)", color: "#010D1D", font: `13.5px ${FONT}`, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}><AgentAvatar size={20} />Ask {agentOf(s.agent).name} about {t.unit}</button>
      </div>
    </div>
  );
}
