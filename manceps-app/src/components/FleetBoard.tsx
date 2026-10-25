import { pick } from "../actions";
import { reloadFleet } from "../live/fleet";
import type { TruckView } from "../live/mappers";
import { setState, useAppState } from "../store";
import { BTN_OUTLINE, BTN_PRIMARY, ENTER, FONT, GLASS, Icon } from "./ui";

const TRUCK_ICON = "M3 6h11v10H3zM14 9h4l3 3v4h-7M7 19a2 2 0 1 0 0-.01M17 19a2 2 0 1 0 0-.01";
const LIST_MAX_H = "calc(100vh - 420px)";

/** "Add a truck" and "Import" buttons used by the board and every empty state. */
export function FleetActions({ compact = false }: { compact?: boolean }): JSX.Element {
  const h = compact ? 34 : 40;
  return (
    <div style={{ display: "flex", gap: 8 }}>
      <button type="button" className="hv-primary" onClick={() => setState({ panel: "addTruck" })} style={{ ...BTN_PRIMARY, height: h, flex: 1 }}>Add a truck</button>
      <button type="button" className="hv-ink-border" onClick={() => setState({ panel: "import" })} style={{ ...BTN_OUTLINE, height: h, flex: 1 }}>Import</button>
    </div>
  );
}

function TruckRow({ t, on }: { t: TruckView; on: boolean }): JSX.Element {
  const sub = [t.equipment, t.drivers.map((d) => d.name).filter(Boolean).join(", ") || "No driver yet"].filter(Boolean).join(" · ");
  return (
    <button type="button" className="hv-need" onClick={() => pick(t.id)} style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 16px", border: 0, borderTop: "1px solid rgba(1,13,29,.06)", background: on ? "rgba(34,114,173,.1)" : "transparent", cursor: "pointer", textAlign: "left", fontFamily: FONT, color: "#010D1D" }}>
      <span style={{ minWidth: 44, height: 26, padding: "0 8px", boxSizing: "border-box", borderRadius: 5, background: on ? "#2272AD" : "#FFFFFF", color: on ? "#FFFFFF" : "#010D1D", display: "grid", placeItems: "center", fontSize: 12.5, boxShadow: "0 4px 12px -6px rgba(1,13,29,.45)" }}>{t.unit}</span>
      <span style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 1 }}>
        <span style={{ fontSize: 13.5, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{t.carrier}</span>
        <span style={{ fontSize: 12, color: "#64748A", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{sub}</span>
      </span>
    </button>
  );
}

function Empty(): JSX.Element {
  return (
    <div style={{ padding: "4px 16px 16px", display: "flex", flexDirection: "column", gap: 12 }}>
      <span className="pretty" style={{ fontSize: 18, lineHeight: 1.25, letterSpacing: "-0.01em" }}>No trucks yet</span>
      <span className="pretty" style={{ fontSize: 13.5, lineHeight: 1.5, color: "#3D4A5C" }}>Add your first truck, or import your carriers and drivers from a spreadsheet.</span>
      <FleetActions />
    </div>
  );
}

function Failed({ error }: { error: string }): JSX.Element {
  return (
    <div style={{ padding: "4px 16px 16px", display: "flex", flexDirection: "column", gap: 10 }}>
      <span style={{ fontSize: 13.5, color: "#B23A31" }}>{error}</span>
      <button type="button" className="hv-ink-border" onClick={() => void reloadFleet()} style={BTN_OUTLINE}>Try again</button>
    </div>
  );
}

/** Live fleet board on the map: every truck from /v1/trucks, or a clean empty state. */
export function FleetBoard(): JSX.Element | null {
  const s = useAppState();
  if (s.view === "sheet" || s.sel) return null;
  const n = s.trucks.length;
  return (
    <div style={{ width: 340, borderRadius: 12, ...GLASS, overflow: "hidden", animation: ENTER, pointerEvents: "auto", display: "flex", flexDirection: "column" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "14px 16px 10px" }}>
        <Icon d={TRUCK_ICON} stroke="#64748A" join />
        <span style={{ fontSize: 12, letterSpacing: ".015em", color: "#64748A", flex: 1 }}>Fleet{s.fleetStatus === "ready" ? " · " + n + (n === 1 ? " truck" : " trucks") : ""}</span>
      </div>
      {s.fleetStatus === "loading" || s.fleetStatus === "idle" ? <span style={{ padding: "0 16px 16px", fontSize: 13.5, color: "#64748A" }}>Loading your fleet…</span> : null}
      {s.fleetStatus === "error" && <Failed error={s.fleetError ?? "Couldn't load your fleet."} />}
      {s.fleetStatus === "ready" && !n && <Empty />}
      {s.fleetStatus === "ready" && n > 0 && (
        <>
          <div style={{ maxHeight: LIST_MAX_H, minHeight: 0, overflow: "auto", display: "flex", flexDirection: "column" }}>
            {s.trucks.map((t) => <TruckRow key={t.id} t={t} on={s.sel === t.id} />)}
          </div>
          <div style={{ padding: "10px 16px 14px", borderTop: "1px solid rgba(1,13,29,.06)", display: "flex", flexDirection: "column", gap: 8 }}>
            <FleetActions compact />
            <span style={{ fontSize: 11.5, color: "#8C9AAD" }}>Trucks appear on the map once live locations are connected.</span>
          </div>
        </>
      )}
    </div>
  );
}
