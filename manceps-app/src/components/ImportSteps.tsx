import { useRef } from "react";
import { showToast } from "../actions";
import { imports } from "../api";
import { friendlyMessage } from "../api/errors";
import type { DuplicateStrategy } from "../api/types";
import { IMPORT_ENTITIES, IMPORT_FIELDS, mappingProblems } from "../live/imports";
import { setState } from "../store";
import type { ImportCtl } from "./ImportPanel";
import { BTN_OUTLINE, BTN_PRIMARY, FIELD, FONT, segStyle } from "./ui";

const MUTED = { fontSize: 13, color: "#64748A", lineHeight: 1.5 } as const;
const URL_REVOKE_MS = 2000;
const PREVIEW_ROWS = 8;
const STRATEGIES: [DuplicateStrategy, string][] = [["update", "Update matches"], ["merge", "Fill empty fields"], ["skip", "Skip matches"]];
const ROW_LINE = "1px solid rgba(1,13,29,.06)";

async function downloadTemplate(entity: string): Promise<void> {
  try {
    const res = await imports.template(entity === "drivers" ? "drivers" : "carriers");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(await res.blob());
    a.download = "manceps-" + entity + "-template.csv";
    a.click();
    window.setTimeout(() => URL.revokeObjectURL(a.href), URL_REVOKE_MS);
  } catch (e) {
    showToast(friendlyMessage(e));
  }
}

/** Step 1: what to import and the file. */
export function ChooseStep({ c }: { c: ImportCtl }): JSX.Element {
  const file = useRef<HTMLInputElement>(null);
  return (
    <>
      <div style={{ display: "flex", gap: 2, padding: 3, borderRadius: 7, background: "rgba(1,13,29,.05)" }}>
        {IMPORT_ENTITIES.map(([k, label]) => <button key={k} type="button" onClick={() => c.setEntity(k)} style={{ flex: 1, height: 30, border: 0, borderRadius: 5, cursor: "pointer", font: `12.5px ${FONT}`, ...segStyle(c.entity === k) }}>{label}</button>)}
      </div>
      <span className="pretty" style={MUTED}>
        {c.entity === "carriers" ? "One row per carrier. A phone number is required; it is how Manceps matches existing carriers." : "One row per driver, with the carrier's phone so each driver lands on the right carrier. Import carriers first."}
        {" "}Trucks are added one at a time with Add a truck.
      </span>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <input ref={file} type="file" accept=".csv,.xlsx" onChange={(e) => { const f = e.target.files?.[0]; if (f) c.upload(f); e.target.value = ""; }} style={{ display: "none" }} />
        <button type="button" className="hv-primary" disabled={Boolean(c.busy)} onClick={() => file.current?.click()} style={{ ...BTN_PRIMARY, opacity: c.busy ? 0.6 : 1 }}>Choose a .csv or .xlsx file</button>
        <button type="button" className="hv-ink-border" onClick={() => void downloadTemplate(c.entity)} style={BTN_OUTLINE}>Download template</button>
      </div>
    </>
  );
}

/** Step 2: match file columns to fields. */
export function MappingStep({ c }: { c: ImportCtl }): JSX.Element {
  const fields = IMPORT_FIELDS[c.entity], problems = mappingProblems(c.entity, c.mapping);
  return (
    <>
      <span className="pretty" style={MUTED}>Match each column in {c.imp?.source_filename ?? "your file"} to a field. Columns set to "Don't import" are left out.</span>
      {c.imp?.ignored_consent_columns.length ? <span style={MUTED}>Consent columns are never imported: {c.imp.ignored_consent_columns.join(", ")}.</span> : null}
      <div style={{ display: "flex", flexDirection: "column" }}>
        {Object.keys(c.mapping).map((col) => (
          <div key={col} style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, alignItems: "center", padding: "6px 0", borderBottom: ROW_LINE }}>
            <span style={{ fontSize: 13.5, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{col}</span>
            <select value={c.mapping[col] ?? ""} onChange={(e) => c.setMapping({ ...c.mapping, [col]: e.target.value || null })} style={{ ...FIELD, height: 34 }}>
              <option value="">Don't import</option>
              {fields.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
            </select>
          </div>
        ))}
      </div>
      {problems.map((p) => <span key={p} style={{ fontSize: 13, color: "#8A5A12" }}>{p}</span>)}
      <div style={{ display: "flex", justifyContent: "flex-end" }}>
        <button type="button" className="hv-primary" disabled={Boolean(problems.length || c.busy)} onClick={c.saveMapping} style={{ ...BTN_PRIMARY, opacity: problems.length || c.busy ? 0.5 : 1 }}>Check rows</button>
      </div>
    </>
  );
}

/** Step 3: what the commit will do, row by row. */
export function PreviewStep({ c }: { c: ImportCtl }): JSX.Element {
  const p = c.preview, st = c.imp?.stats;
  const counts = p ? Object.entries(p.counts).filter(([, n]) => n > 0).map(([k, n]) => n + " " + k).join(" · ") : "";
  return (
    <>
      <span style={{ fontSize: 14 }}>{st ? st.rows + " rows · " + st.valid + " valid · " + st.invalid + " with problems" : ""}</span>
      {counts && <span style={MUTED}>Planned: {counts}</span>}
      {st && st.needs_approval > 0 && <span style={{ fontSize: 13, color: "#8A5A12" }}>{st.needs_approval} rows set fees or floors; they wait for the owner's approval.</span>}
      <label style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 13, color: "#3D4A5C" }}>When a row matches an existing record
        <select value={c.strategy} onChange={(e) => c.changeStrategy(e.target.value as DuplicateStrategy)} style={{ ...FIELD, height: 34 }}>
          {STRATEGIES.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
        </select>
      </label>
      <div style={{ display: "flex", flexDirection: "column", borderTop: ROW_LINE }}>
        {(p?.rows ?? []).slice(0, PREVIEW_ROWS).map((r) => (
          <div key={r.row_no} style={{ display: "flex", gap: 10, padding: "7px 0", borderBottom: ROW_LINE, fontSize: 13 }}>
            <span style={{ width: 54, color: "#8C9AAD" }}>Row {r.row_no}</span>
            <span style={{ width: 64 }}>{r.action}</span>
            <span style={{ flex: 1, minWidth: 0, color: r.errors.length ? "#B23A31" : "#64748A" }}>{r.errors.length ? r.errors.map((e) => e.message).join("; ") : r.reason ?? ""}</span>
          </div>
        ))}
      </div>
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
        <button type="button" className="hv-ink-border" onClick={c.editMapping} style={BTN_OUTLINE}>Change mapping</button>
        <button type="button" className="hv-primary" disabled={Boolean(c.busy) || !st?.valid} onClick={c.commit} style={{ ...BTN_PRIMARY, opacity: c.busy || !st?.valid ? 0.5 : 1 }}>Import {st?.valid ?? 0} rows</button>
      </div>
    </>
  );
}

/** Step 4: result, with undo while the window is open. */
export function DoneStep({ c }: { c: ImportCtl }): JSX.Element {
  const i = c.imp;
  if (!i) return <span style={MUTED}>Nothing imported.</span>;
  const s = i.stats, undone = i.status === "undone";
  const canUndo = i.status === "committed" && i.undo_until !== null && Date.parse(i.undo_until) > Date.now();
  return (
    <>
      <span style={{ fontSize: 16 }}>{undone ? "Import undone" : i.status === "failed" ? "Import failed" : "Import finished"}</span>
      {i.status === "failed" && <span style={{ fontSize: 13, color: "#B23A31" }}>{i.error ?? "The import failed."}</span>}
      {!undone && i.status !== "failed" && <span style={MUTED}>{s.created} created · {s.updated} updated · {s.merged} merged · {s.skipped} skipped · {s.rejected} rejected</span>}
      {undone && i.undo && <span style={MUTED}>{i.undo.removed} removed · {i.undo.restored} restored · {i.undo.skipped_modified} kept because they changed since</span>}
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
        {canUndo && <button type="button" className="hv-ink-border" disabled={Boolean(c.busy)} onClick={c.undo} style={BTN_OUTLINE}>Undo import</button>}
        <button type="button" className="hv-primary" onClick={() => setState({ panel: null })} style={BTN_PRIMARY}>Done</button>
      </div>
    </>
  );
}
