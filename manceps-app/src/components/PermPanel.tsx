import { agentOf } from "../agents";
import { LOCKED_PERMS, PERMS, PRESETS, presetMatches, setPerm, type FreePermKey, type PermKey, type PermLevel, type PresetKey } from "../demo";
import { setState, useAppState } from "../store";
import { AgentAvatar, BLUE_SHELL, DemoTag, FONT, ICON_CLOSE, Icon, Switch } from "./ui";

const LEVELS: [PermLevel, string][] = [["auto", "Auto"], ["ask", "Ask"], ["off", "Off"]];
const ROW_LINE = "1px solid rgba(1,13,29,.07)";
const LEVEL_BG: Record<PermLevel, string> = { off: "#3D4A5C", auto: "#2272AD", ask: "#010D1D" };
const LOCK = ["M7 11V8a5 5 0 0 1 10 0v3", "M5 11h14v10H5z"];

function isLocked(k: PermKey): k is (typeof LOCKED_PERMS)[number] {
  return (LOCKED_PERMS as readonly string[]).includes(k);
}

function Presets(): JSX.Element {
  const s = useAppState();
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(3,minmax(0,1fr))", gap: 8 }}>
      {(Object.keys(PRESETS) as PresetKey[]).map((k) => {
        const [name, desc, val] = PRESETS[k], on = presetMatches(k, s.perm);
        return (
          <button key={k} type="button" onClick={() => setPerm({ ...val })} style={{ textAlign: "left", padding: 12, borderRadius: 8, cursor: "pointer", fontFamily: FONT, color: "#010D1D", display: "flex", flexDirection: "column", gap: 3, background: on ? "#EEF5FB" : "#FFFFFF", border: on ? "1.5px solid #2272AD" : "1px solid rgba(1,13,29,.1)", transition: "border-color .2s,background .2s" }}>
            <span style={{ fontSize: 14 }}>{name}</span>
            <span className="pretty" style={{ fontSize: 12, lineHeight: 1.4, color: "#64748A" }}>{desc}</span>
          </button>
        );
      })}
    </div>
  );
}

function LevelPicker({ k }: { k: FreePermKey }): JSX.Element {
  const s = useAppState();
  return (
    <div style={{ flexShrink: 0, display: "flex", gap: 2, padding: 3, borderRadius: 7, background: "rgba(1,13,29,.05)" }}>
      {LEVELS.map(([v, l]) => {
        const on = s.perm[k] === v;
        return <button key={v} type="button" onClick={() => setPerm({ [k]: v })} style={{ height: 30, minWidth: 52, padding: "0 10px", border: 0, borderRadius: 5, cursor: "pointer", font: `12.5px ${FONT}`, background: on ? LEVEL_BG[v] : "transparent", color: on ? "#FFFFFF" : "#3D4A5C", boxShadow: on ? "0 1px 2px rgba(1,13,29,.2)" : "none", transition: "background .15s" }}>{l}</button>;
      })}
    </div>
  );
}

/** Booking loads and signing rate cons always wait for the owner's one-tap approval. */
function LockedLevel(): JSX.Element {
  return (
    <span title="Always needs your one-tap approval" style={{ flexShrink: 0, height: 36, display: "flex", alignItems: "center", gap: 6, padding: "0 12px", borderRadius: 7, background: "rgba(1,13,29,.05)", color: "#3D4A5C", fontSize: 12.5 }}>
      <Icon d={LOCK} size={14} join />Always asks you
    </span>
  );
}

function PermRow({ k, label, desc }: { k: PermKey; label: string; desc: string }): JSX.Element {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "11px 0", borderTop: ROW_LINE }}>
      <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 1 }}>
        <span style={{ fontSize: 14 }}>{label}</span>
        <span className="pretty" style={{ fontSize: 12, color: "#64748A" }}>{desc}</span>
      </div>
      {isLocked(k) ? <LockedLevel /> : <LevelPicker k={k} />}
    </div>
  );
}

/** What the agent may do without asking: presets, per-action levels and quiet hours. Demo until agent settings exist. */
export function PermPanel(): JSX.Element {
  const s = useAppState(), name = agentOf(s.agent).name;
  return (
    <div style={{ ...BLUE_SHELL, maxHeight: "calc(100vh - 110px)", display: "flex", flexDirection: "column" }}>
      <div style={{ height: 60, flexShrink: 0, display: "flex", alignItems: "center", gap: 12, padding: "0 8px 0 10px" }}>
        <AgentAvatar size={40} style={{ boxShadow: "0 0 0 2px rgba(255,255,255,.7)" }} />
        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 1, lineHeight: 1.2 }}>
          <span style={{ fontSize: 15, color: "#FFFFFF", display: "flex", alignItems: "center", gap: 8 }}>What {name} can do on its own<DemoTag dark /></span>
          <span style={{ fontSize: 12, color: "#E2E8F0" }}>Anything set to Ask comes to you first</span>
        </div>
        <button type="button" className="hv-ghost" onClick={() => setState({ permOpen: false, chat: true })} aria-label="Back to chat" style={{ width: 40, height: 40, border: 0, borderRadius: 6, background: "transparent", color: "#FFFFFF", cursor: "pointer", display: "grid", placeItems: "center" }}><Icon d={ICON_CLOSE} size={20} /></button>
      </div>
      <div style={{ flex: 1, minHeight: 0, overflow: "auto", borderRadius: 10, background: "rgba(255,255,255,.84)", padding: "16px 18px 14px", display: "flex", flexDirection: "column", gap: 14 }}>
        <Presets />
        <div style={{ display: "flex", flexDirection: "column" }}>
          {PERMS.map(([k, label, desc]) => <PermRow key={k} k={k} label={label} desc={desc} />)}
          <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "11px 0 2px", borderTop: ROW_LINE }}>
            <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 1 }}>
              <span style={{ fontSize: 14 }}>Quiet hours for drivers</span>
              <span style={{ fontSize: 12, color: "#64748A" }}>No calls 22:00–06:00. Texts only, unless it's urgent.</span>
            </div>
            <Switch on={s.quiet} label="Quiet hours" onClick={() => setState((x) => ({ quiet: !x.quiet }))} />
          </div>
        </div>
        <span style={{ fontSize: 12, color: "#8C9AAD" }}>{name} logs everything it does. Booking a load and signing a rate con always wait for your one-tap yes.</span>
      </div>
    </div>
  );
}
