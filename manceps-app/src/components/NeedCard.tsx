import { agentOf } from "../agents";
import { ackLate102, allNeeds, book, type Need } from "../demo";
import { setState, useAppState } from "../store";
import { DemoTag, ENTER, FONT, GLASS } from "./ui";

/** The decision the card's main button performs; booking only ever happens from this owner tap. */
function runYes(n: Need): void {
  if (n.id === "b101") book();
  else ackLate102();
}

/** Card for the first open decision ("Needs your yes" / "Heads up"). Demo data until /v1/approvals lands. */
export function NeedCard(): JSX.Element | null {
  const s = useAppState();
  const list = allNeeds(s, agentOf(s.agent).name).filter((n) => !s.later.includes(n.id));
  const n = list[0];
  if (!n || s.sel || s.view === "sheet") return null;
  return (
    <div style={{ width: 340, borderRadius: 12, ...GLASS, overflow: "hidden", animation: ENTER, pointerEvents: "auto" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "14px 16px 0" }}>
        <span style={{ width: 8, height: 8, borderRadius: "50%", background: n.c }} />
        <span style={{ fontSize: 12, letterSpacing: ".015em", color: "#64748A", flex: 1 }}>{n.tag}</span>
        <span style={{ fontSize: 12, color: "#8C9AAD" }}>{list.length > 1 ? "1 of " + list.length : ""}</span>
        <DemoTag />
      </div>
      <div style={{ padding: "8px 16px 16px", display: "flex", flexDirection: "column", gap: 12 }}>
        <span className="pretty" style={{ fontSize: 18, lineHeight: 1.25, letterSpacing: "-0.01em" }}>{n.title}</span>
        <span className="pretty" style={{ fontSize: 13.5, lineHeight: 1.5, color: "#3D4A5C" }}>{n.body}</span>
        <div style={{ display: "flex", gap: 8 }}>
          <button type="button" className="hv-primary" onClick={() => runYes(n)} style={{ flex: 1, height: 40, border: 0, borderRadius: 6, background: "#010D1D", color: "#FFFFFF", font: `14px ${FONT}`, cursor: "pointer", transition: "background .2s cubic-bezier(.4,0,.2,1)" }}>{n.yesLabel}</button>
          <button type="button" className="hv-ink-border" onClick={() => setState((x) => ({ later: [...x.later, n.id] }))} style={{ height: 40, padding: "0 14px", border: "1px solid rgba(1,13,29,.14)", borderRadius: 6, background: "#FFFFFF", color: "#010D1D", font: `14px ${FONT}`, cursor: "pointer" }}>Later</button>
        </div>
      </div>
    </div>
  );
}
