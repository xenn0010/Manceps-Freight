import type { FormEvent } from "react";
import { agentOf } from "../agents";
import { showToast } from "../actions";
import type { SheetTab } from "../data";
import { classifyCommand, sheetOp } from "../demo";
import { toCsv } from "../logic/sheet";
import { activeSheet, formulaBar, sheetChips, sheetHeading, sheetStatus } from "../logic/sheetView";
import { getState, setState, useAppState } from "../store";
import { FleetActions } from "./FleetBoard";
import { GRID_LINE, GridHead, GridRow } from "./SheetGrid";
import { AgentAvatar, DemoTag, ENTER, FONT, GLASS, ICON_SEND, Icon, segStyle } from "./ui";

const URL_REVOKE_MS = 2000;

function download(): void {
  const s = getState(), { cols, rows } = activeSheet(s);
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([toCsv(cols, rows)], { type: "text/csv" }));
  a.download = "manceps-" + s.sheetTab + ".csv";
  a.click();
  window.setTimeout(() => URL.revokeObjectURL(a.href), URL_REVOKE_MS);
}

function submitCmd(e: FormEvent): void {
  e.preventDefault();
  const q = getState().cmd;
  setState({ cmd: "" });
  const k = classifyCommand(q);
  if (k) sheetOp(k);
  else showToast("Try: find backhauls, negotiate, flag low rates, book, send rate cons", true);
}

/** The agent command bar and quick chips; they run the scripted demo operations. */
function AgentBar(): JSX.Element {
  const s = useAppState(), name = agentOf(s.agent).name;
  return (
    <form onSubmit={submitCmd} style={{ display: "flex", alignItems: "center", gap: 8, height: 40, padding: "0 4px 0 6px", borderRadius: 20, flex: 1.4, minWidth: 320, background: "rgba(255,255,255,.85)", border: "1.5px solid rgba(34,114,173,.55)", boxShadow: "0 0 0 4px rgba(34,114,173,.1),0 10px 24px -14px rgba(27,94,148,.6)" }}>
        <AgentAvatar size={30} style={{ boxShadow: "0 0 0 2px rgba(255,255,255,.7)" }}>
          {s.busy && <span style={{ position: "absolute", inset: -4, borderRadius: "50%", border: "2px solid #2272AD", opacity: 0.7, animation: "ping 1.4s cubic-bezier(0,0,.2,1) infinite" }} />}
        </AgentAvatar>
        <input value={s.cmd} onChange={(e) => setState({ cmd: e.target.value })} placeholder={s.busy ? name + " is working…" : "Tell " + name + " what to do with this sheet"} style={{ flex: 1, minWidth: 0, height: "100%", border: 0, background: "transparent", outline: "none", color: "#010D1D", font: `14px ${FONT}` }} />
        <DemoTag />
        <button type="submit" aria-label="Run" style={{ width: 32, height: 32, flexShrink: 0, border: 0, borderRadius: "50%", background: "linear-gradient(180deg,#3A86C2,#1B5E94)", color: "#FFFFFF", cursor: "pointer", display: "grid", placeItems: "center" }}><Icon d={ICON_SEND} join /></button>
    </form>
  );
}

function Toolbar(): JSX.Element {
  const s = useAppState(), fb = formulaBar(s), { isLoads, rows } = activeSheet(s), head = sheetHeading(isLoads, rows);
  return (
    <>
      <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 14px 10px 18px", flexWrap: "wrap" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 1, flex: 1, minWidth: 180 }}>
          <span style={{ fontSize: 17, letterSpacing: "-0.01em", display: "flex", alignItems: "center", gap: 8 }}>{head.title}{isLoads && <DemoTag />}</span>
          <span style={{ fontSize: 12, color: "#64748A" }}>{head.sub}</span>
        </div>
        {!isLoads && <button type="button" className="hv-white" onClick={() => setState({ panel: "import" })} style={{ height: 36, display: "flex", alignItems: "center", gap: 8, padding: "0 14px", border: "1px solid rgba(1,13,29,.12)", borderRadius: 8, background: "rgba(255,255,255,.7)", color: "#010D1D", font: `13px ${FONT}`, cursor: "pointer" }}><Icon d="M12 20V9M7 14l5-5 5 5M5 4h14" size={15} join />Import</button>}
        <button type="button" className="hv-white" onClick={download} style={{ height: 36, display: "flex", alignItems: "center", gap: 8, padding: "0 14px", border: "1px solid rgba(1,13,29,.12)", borderRadius: 8, background: "rgba(255,255,255,.7)", color: "#010D1D", font: `13px ${FONT}`, cursor: "pointer" }}><Icon d="M12 4v11M7 10l5 5 5-5M5 20h14" size={15} join />Download for Excel</button>
      </div>
      <div style={{ display: "flex", alignItems: "stretch", gap: 8, padding: "0 14px 10px", flexWrap: "wrap" }}>
        <div style={{ display: "flex", alignItems: "center", height: 40, borderRadius: 8, background: "rgba(255,255,255,.7)", border: GRID_LINE, minWidth: 260, flex: 1, overflow: "hidden" }}>
          <span style={{ width: 56, height: "100%", display: "grid", placeItems: "center", fontSize: 12.5, fontVariantNumeric: "tabular-nums", borderRight: GRID_LINE, color: "#3D4A5C" }}>{fb.ref}</span>
          <span style={{ padding: "0 10px", fontSize: 13, fontStyle: "italic", color: "#8C9AAD" }}>fx</span>
          <span style={{ flex: 1, minWidth: 0, fontSize: 13.5, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", paddingRight: 10 }}>{fb.val}</span>
        </div>
        <AgentBar />
      </div>
      <div className="no-scrollbar" style={{ display: "flex", gap: 6, padding: "0 14px 12px", overflowX: "auto" }}>
        {sheetChips(s).map((c) => (
          <button key={c.k} type="button" className="hv-blue-border" onClick={() => sheetOp(c.k)} style={{ flexShrink: 0, height: 32, display: "flex", alignItems: "center", gap: 6, padding: "0 12px", borderRadius: 16, cursor: "pointer", font: `12.5px ${FONT}`, whiteSpace: "nowrap", background: c.done ? "rgba(31,154,90,.1)" : "rgba(255,255,255,.75)", color: c.done ? "#17673E" : "#010D1D", border: "1px solid rgba(1,13,29,.1)", opacity: s.busy ? 0.5 : 1 }}>
            <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#2272AD" }} />{c.label}
          </button>
        ))}
      </div>
    </>
  );
}

function Footer(): JSX.Element {
  const s = useAppState(), st = sheetStatus(s.busy, s.rowsSel.length, agentOf(s.agent).name, s.sheetTab === "loads");
  const tabs: [SheetTab, string][] = [["loads", "Loads"], ["drivers", "Drivers"]];
  return (
    <div style={{ height: 42, flexShrink: 0, display: "flex", alignItems: "center", gap: 4, padding: "0 10px", borderTop: GRID_LINE, background: "rgba(255,255,255,.5)" }}>
      {tabs.map(([k, label]) => (
        <button key={k} type="button" onClick={() => setState({ sheetTab: k, rowsSel: [], editor: null, cell: { r: 0, k: k === "loads" ? "rate" : "duty" } })} style={{ height: 30, padding: "0 14px", border: 0, borderRadius: 6, cursor: "pointer", font: `12.5px ${FONT}`, ...segStyle(s.sheetTab === k) }}>{label}</button>
      ))}
      <span style={{ flex: 1 }} />
      <span style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: st.ink, whiteSpace: "nowrap" }}>
        <span style={{ width: 7, height: 7, borderRadius: "50%", background: st.dot }} />{st.text}
      </span>
    </div>
  );
}

/** Empty drivers tab: a brand-new firm has no drivers yet. */
function NoDrivers(): JSX.Element {
  const s = useAppState();
  const text = s.fleetStatus === "error" ? s.fleetError ?? "Couldn't load your drivers." : s.fleetStatus === "ready" ? "No drivers yet. Add a truck with its driver, or import your drivers from a spreadsheet." : "Loading your drivers…";
  return (
    <div style={{ padding: "48px 24px", display: "flex", flexDirection: "column", alignItems: "center", gap: 14 }}>
      <span className="pretty" style={{ fontSize: 14, color: "#3D4A5C", textAlign: "center", maxWidth: 380 }}>{text}</span>
      {s.fleetStatus === "ready" && <div style={{ width: 300 }}><FleetActions /></div>}
    </div>
  );
}

/** Spreadsheet of loads (demo) and drivers (live, editable) that the agent can edit too. */
export function SheetView(): JSX.Element {
  const s = useAppState(), { cols, rows, isLoads } = activeSheet(s), now = Date.now();
  const gridCols = "44px " + cols.map((c) => c[2] + "px").join(" ");
  return (
    <div style={{ position: "absolute", left: 20, right: 20, top: 84, bottom: 20, display: "flex", flexDirection: "column", borderRadius: 16, overflow: "hidden", ...GLASS, animation: ENTER }}>
      <Toolbar />
      <div style={{ flex: 1, minHeight: 0, overflow: "auto", borderTop: GRID_LINE, background: "rgba(255,255,255,.55)" }}>
        <div style={{ width: "max-content", minWidth: "100%" }}>
          <GridHead gridCols={gridCols} />
          {rows.map((r, ri) => <GridRow key={typeof r.id === "string" && !isLoads ? r.id : ri} r={r} ri={ri} gridCols={gridCols} now={now} />)}
        </div>
        {!isLoads && !rows.length && <NoDrivers />}
      </div>
      <Footer />
    </div>
  );
}
