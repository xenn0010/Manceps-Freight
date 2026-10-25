import { agentOf } from "../agents";
import { showToast } from "../actions";
import { AGENT_COLUMNS, LETTERS, type Row } from "../data";
import { saveDriverCell } from "../live/fleet";
import { isEditableDriverColumn } from "../live/mappers";
import { activeSheet, cellView, justifyFor } from "../logic/sheetView";
import { getState, setState, useAppState } from "../store";
import { AgentAvatar, DemoTag, FONT } from "./ui";

export const GRID_LINE = "1px solid rgba(1,13,29,.08)";
const CELL_LINE = "1px solid rgba(1,13,29,.06)";

/** Header row with column letters and names; demo agent columns on the live drivers tab carry a Demo tag. */
export function GridHead({ gridCols }: { gridCols: string }): JSX.Element {
  const s = useAppState(), { cols, isLoads } = activeSheet(s), ci = cols.findIndex((c) => c[0] === s.cell.k);
  return (
    <>
      <div style={{ position: "sticky", top: 0, zIndex: 3, display: "grid", gridTemplateColumns: gridCols, background: "rgba(241,245,249,.92)", backdropFilter: "blur(8px)", WebkitBackdropFilter: "blur(8px)" }}>
        <span style={{ height: 26, borderRight: GRID_LINE, borderBottom: GRID_LINE }} />
        {cols.map((c, i) => (
          <span key={c[0]} style={{ height: 26, display: "grid", placeItems: "center", fontSize: 11, borderRight: GRID_LINE, borderBottom: GRID_LINE, background: i === ci ? "rgba(34,114,173,.14)" : "transparent", color: i === ci ? "#1B5E94" : "#8C9AAD" }}>{LETTERS[i]}</span>
        ))}
      </div>
      <div style={{ position: "sticky", top: 26, zIndex: 2, display: "grid", gridTemplateColumns: gridCols, background: "rgba(255,255,255,.9)" }}>
        <span style={{ height: 34, display: "grid", placeItems: "center", fontSize: 11, color: "#8C9AAD", borderRight: GRID_LINE, borderBottom: "1px solid rgba(1,13,29,.12)", background: "rgba(241,245,249,.92)" }}>1</span>
        {cols.map((c) => (
          <span key={c[0]} style={{ height: 34, display: "flex", alignItems: "center", gap: 6, padding: "0 10px", fontSize: 12, letterSpacing: ".015em", color: "#64748A", whiteSpace: "nowrap", borderRight: CELL_LINE, borderBottom: "1px solid rgba(1,13,29,.12)", justifyContent: justifyFor(c[3]) }}>{c[1]}{!isLoads && AGENT_COLUMNS.has(c[0]) && <DemoTag />}</span>
        ))}
      </div>
    </>
  );
}

function AgentCursor(): JSX.Element {
  const name = agentOf(useAppState().agent).name;
  return (
    <span style={{ position: "absolute", left: -2, top: -19, height: 17, display: "flex", alignItems: "center", gap: 4, padding: "0 6px 0 2px", borderRadius: "4px 4px 4px 0", background: "#2272AD", color: "#FFFFFF", fontSize: 10.5, whiteSpace: "nowrap", pointerEvents: "none" }}>
      <AgentAvatar size={13} />{name}
    </span>
  );
}

function toggleRow(ri: number): void {
  setState((x) => ({ rowsSel: x.rowsSel.includes(ri) ? x.rowsSel.filter((i) => i !== ri) : [...x.rowsSel, ri] }));
}

/**
 * Open the editor on a drivers sheet cell, or explain why it can't be edited.
 *
 * Args:
 *   r: Row index.
 *   k: Column key.
 */
export function beginEdit(r: number, k: string): void {
  const s = getState();
  if (s.sheetTab !== "drivers" || s.busy) return;
  const row = s.drivers[r];
  if (!row) return;
  if (!isEditableDriverColumn(k)) {
    const col = activeSheet(s).cols.find((c) => c[0] === k)?.[1] ?? "This column";
    showToast(col + " can't be edited here" + (k === "truck" || k === "carrier" ? " · it comes from the carrier's record" : ""));
    return;
  }
  setState({ editor: { r, k, v: String(row[k] ?? ""), saving: false } });
}

async function commitEdit(): Promise<void> {
  const ed = getState().editor;
  if (!ed || ed.saving) return;
  const row = getState().drivers[ed.r];
  if (row && String(row[ed.k] ?? "") === ed.v.trim()) { setState({ editor: null }); return; }
  setState({ editor: { ...ed, saving: true } });
  const ok = await saveDriverCell(ed.r, ed.k, ed.v);
  setState({ editor: ok ? null : { ...ed, saving: false } });
}

function CellEditor(): JSX.Element | null {
  const ed = useAppState().editor;
  if (!ed) return null;
  return (
    <input autoFocus value={ed.v} disabled={ed.saving} aria-label="Edit cell"
      onChange={(e) => setState({ editor: { ...ed, v: e.target.value } })}
      onKeyDown={(e) => { if (e.key === "Enter") void commitEdit(); if (e.key === "Escape") { e.stopPropagation(); setState({ editor: null }); } }}
      onBlur={() => void commitEdit()}
      style={{ position: "absolute", inset: 0, width: "100%", boxSizing: "border-box", padding: "0 10px", border: 0, outline: "2px solid #2272AD", background: "#FFFFFF", font: `13px ${FONT}`, color: "#010D1D", opacity: ed.saving ? 0.6 : 1 }} />
  );
}

/** One sheet row: row number toggle plus one cell button (or the editor) per column. */
export function GridRow({ r, ri, gridCols, now }: { r: Row; ri: number; gridCols: string; now: number }): JSX.Element {
  const s = useAppState(), { cols } = activeSheet(s), sel = s.rowsSel.includes(ri);
  return (
    <div style={{ display: "grid", gridTemplateColumns: gridCols, background: sel ? "rgba(34,114,173,.08)" : "transparent", transition: "background .2s" }}>
      <button type="button" onClick={() => toggleRow(ri)} aria-label="Select row" style={{ height: 38, border: 0, borderRight: GRID_LINE, borderBottom: CELL_LINE, cursor: "pointer", font: `11px ${FONT}`, fontVariantNumeric: "tabular-nums", background: sel ? "#2272AD" : s.cell.r === ri ? "rgba(34,114,173,.14)" : "rgba(241,245,249,.8)", color: sel ? "#FFFFFF" : "#8C9AAD" }}>{ri + 2}</button>
      {cols.map((col) => {
        const c = cellView(s, r, ri, col, now);
        const editing = s.sheetTab === "drivers" && s.editor?.r === ri && s.editor.k === col[0];
        return (
          <div key={col[0]} style={{ position: "relative", minWidth: 0 }}>
            <button type="button" onClick={() => setState({ cell: { r: ri, k: col[0] } })} onDoubleClick={() => beginEdit(ri, col[0])} onKeyDown={(e) => { if (e.key === "Enter") beginEdit(ri, col[0]); }} style={{ position: "relative", width: "100%", height: 38, minWidth: 0, display: "flex", alignItems: "center", padding: "0 10px", border: 0, borderRight: CELL_LINE, borderBottom: CELL_LINE, cursor: "cell", font: `13px ${FONT}`, fontVariantNumeric: "tabular-nums", textAlign: "left", whiteSpace: "nowrap", overflow: "visible", justifyContent: c.justify, background: c.bg, color: c.ink, boxShadow: c.ring, zIndex: c.z, transition: "background .4s" }}>
              <span style={{ overflow: "hidden", textOverflow: "ellipsis", padding: c.pp, borderRadius: 5, background: c.pbg }}>{c.v}</span>
              {c.agent && <AgentCursor />}
            </button>
            {editing && <CellEditor />}
          </div>
        );
      })}
    </div>
  );
}
