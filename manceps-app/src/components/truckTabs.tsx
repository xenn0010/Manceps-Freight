import type { TruckView } from "../live/mappers";
import { nameParts } from "../logic/derive";
import { STATUS } from "../data";
import { FACT_GRID, Fact } from "./ui";

const MUTED = { fontSize: 13.5, color: "#64748A" } as const;

/** Load tab: loads are not served by the backend yet, so a truck shows none. */
export function LoadTab(): JSX.Element {
  return <span style={MUTED}>No loads yet. Booked loads for this truck will show here.</span>;
}

/** Driver tab: the drivers of this truck's carrier, from /v1/drivers. */
export function DriverTab({ t }: { t: TruckView }): JSX.Element {
  if (!t.drivers.length) return <span style={MUTED}>No driver yet. Add one in the Sheet's Drivers tab, or import drivers.</span>;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {t.drivers.map((d) => {
        const st = STATUS[d.status] ?? ["#F1F5F9", "#3D4A5C"];
        return (
          <div key={d.id} style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <span style={{ width: 44, height: 44, borderRadius: "50%", background: "#010D1D", color: "#FFFFFF", display: "grid", placeItems: "center", fontSize: 14, flexShrink: 0 }}>{nameParts(d.name || "?").initials.slice(0, 2).toUpperCase()}</span>
            <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 1 }}>
              <span style={{ fontSize: 16 }}>{d.name || "Unnamed driver"}</span>
              <span style={{ fontSize: 12.5, color: "#64748A" }}>{d.phone || "No phone on file"}</span>
            </div>
            {d.status && <span style={{ fontSize: 12, padding: "3px 8px", borderRadius: 5, background: st[0], color: st[1] }}>{d.status}</span>}
          </div>
        );
      })}
    </div>
  );
}

/** Truck tab: equipment facts from /v1/trucks. */
export function EquipTab({ t }: { t: TruckView }): JSX.Element {
  const facts: [string, string][] = [["Unit", t.unit], ["Equipment", t.equipment || "Not set"], ["Plate", t.plate || "Not set"], ["Max weight", t.maxWeight || "Not set"], ["VIN", t.vin || "Not set"], ["Carrier", t.carrier]];
  return <div style={FACT_GRID}>{facts.map(([k, v]) => <Fact key={k} k={k} v={v} tabular />)}</div>;
}

/** Route tab: the backend has no truck locations yet. */
export function RouteTab(): JSX.Element {
  return <span style={MUTED}>No live location yet. The route shows here once this truck reports its position.</span>;
}
