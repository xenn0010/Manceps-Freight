import { agentOf } from "../agents";
import { pick } from "../actions";
import { allNeeds, weekTotal } from "../demo";
import { needSummary } from "../logic/derive";
import { setState, useAppState, type View } from "../store";
import { DemoTag, FONT, GLASS, Icon } from "./ui";

const VIEWS: [View, string, string][] = [
  ["map", "Map", "M9 4L3 6v14l6-2 6 2 6-2V4l-6 2zM9 4v14M15 6v14"],
  ["sheet", "Sheet", "M4 4h16v16H4zM4 9h16M4 14h16M10 4v16"],
];

function Stat({ value, label }: { value: string; label: string }): JSX.Element {
  return (
    <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", padding: "0 20px", gap: 1 }}>
      <span style={{ fontSize: 18, letterSpacing: "-0.01em", fontVariantNumeric: "tabular-nums" }}>{value}</span>
      <span style={{ fontSize: 11, letterSpacing: ".015em", color: "#64748A" }}>{label}</span>
    </div>
  );
}

const Divider = (): JSX.Element => <span style={{ width: 1, margin: "10px 0", background: "rgba(1,13,29,.08)" }} />;

function ViewSwitch(): JSX.Element {
  const s = useAppState();
  const go = (k: View): void => {
    if (k === "sheet" && s.sel) pick(null);
    setState({ view: k, me: false, chat: false, permOpen: false });
  };
  return (
    <div style={{ pointerEvents: "auto", display: "flex", gap: 2, padding: 4, borderRadius: 10, ...GLASS }}>
      {VIEWS.map(([k, label, icon]) => {
        const on = s.view === k;
        return (
          <button key={k} type="button" onClick={() => go(k)} style={{ height: 32, display: "flex", alignItems: "center", gap: 6, padding: "0 12px", border: 0, borderRadius: 7, cursor: "pointer", font: `13px ${FONT}`, background: on ? "#010D1D" : "transparent", color: on ? "#FFFFFF" : "#3D4A5C", boxShadow: on ? "0 4px 10px -4px rgba(1,13,29,.5)" : "none", transition: "background .2s" }}>
            <Icon d={icon} size={15} join />{label}
          </button>
        );
      })}
    </div>
  );
}

/** Top bar: logo, map/sheet switch, live truck count, demo weekly stats and decisions, and the account button. */
export function Header(): JSX.Element {
  const s = useAppState();
  const need = needSummary(allNeeds(s, agentOf(s.agent).name).length);
  const n = s.trucks.length;
  const toggleMe = (): void => {
    if (!s.me && s.sel) pick(null);
    setState({ me: !s.me });
  };
  return (
    <header style={{ position: "absolute", left: 20, right: 20, top: 16, display: "flex", alignItems: "center", gap: 16, pointerEvents: "none" }}>
      <img src="/assets/manceps-logo-cut.png" alt="Manceps" style={{ height: 40, width: "auto", display: "block", pointerEvents: "auto" }} />
      <ViewSwitch />
      <div style={{ flex: 1, display: "flex", justifyContent: "center" }}>
        <div style={{ pointerEvents: "auto", display: "flex", alignItems: "stretch", height: 48, borderRadius: 12, ...GLASS }}>
          <Stat value={String(n)} label={n === 1 ? "truck in your fleet" : "trucks in your fleet"} />
          <Divider />
          <Stat value={weekTotal(s.booked).total} label="booked this week" />
          <Divider />
          <button type="button" className="hv-need" onClick={() => setState({ later: [] })} style={{ display: "flex", alignItems: "center", gap: 10, padding: "0 18px 0 16px", border: 0, background: "transparent", cursor: "pointer", fontFamily: FONT, color: "#010D1D", borderRadius: "0 8px 8px 0" }}>
            <span style={{ width: 24, height: 24, borderRadius: "50%", display: "grid", placeItems: "center", fontSize: 12, color: "#FFFFFF", background: need.dot }}>{need.mark}</span>
            <span style={{ fontSize: 14, whiteSpace: "nowrap" }}>{need.text}</span>
          </button>
          <span style={{ display: "flex", alignItems: "center", paddingRight: 12 }}><DemoTag /></span>
        </div>
      </div>
      <button type="button" onClick={toggleMe} aria-label="Account" style={{ pointerEvents: "auto", width: 40, height: 40, border: 0, borderRadius: "50%", cursor: "pointer", background: "#010D1D", color: "#F1F5F9", display: "grid", placeItems: "center", font: `13px ${FONT}`, boxShadow: s.me ? "0 0 0 3px #FFFFFF,0 0 0 5px #2272AD" : "0 0 0 0 transparent", transition: "box-shadow .2s" }}>{s.profile?.initials ?? ""}</button>
    </header>
  );
}
