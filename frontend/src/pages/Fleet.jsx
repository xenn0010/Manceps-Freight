import { useState } from "react";
import { ArrowLeft, Plus, SlidersHorizontal, Lock } from "lucide-react";
import { useStore } from "../store/useStore";
import { Pill } from "../components/common/ui";
import { TRUCK_PILL_TONE } from "../components/dashboard/TruckStrip";
import { fleetService, settingsService } from "../services";
import { money } from "../lib/format";
import { cn } from "../lib/utils";

const TABS = [["carriers", "Carriers", "carrier"], ["trucks", "Trucks", "truck"], ["drivers", "Drivers", "driver"], ["commitments", "Commitments", "trip"]];
const STATUS_TONE = { active: "green", confirmed: "grey", cancelled: "red" };

function tables(data) {
  const unit = (id) => (data.trucks[id] ? `#${data.trucks[id].unit}` : "Unassigned");
  return {
    carriers: {
      rows: [data.carrier, ...Object.values(data.carriers)],
      cols: [
        ["Carrier", (c) => <b>{c.name}</b>], ["Contact", (c) => `${c.contactName || "—"}${c.phone ? ` · ${c.phone}` : ""}`], ["Home base", (c) => c.homeBase || "—"],
        ["Max deadhead", (c) => `${c.maxDeadhead} mi`], ["Min rate", (c) => `$${Number(c.minRatePerMile).toFixed(2)}/mi`],
        ["Trucks", (c) => Object.values(data.trucks).filter((t) => t.carrierId === c.id).length],
      ],
    },
    trucks: {
      rows: Object.values(data.trucks),
      cols: [
        ["Unit", (t) => <b className="tnum">#{t.unit}</b>], ["Driver", (t) => data.drivers[t.driverId]?.name], ["Location", (t) => t.location],
        ["Status", (t) => <span className="flex items-center gap-1.5"><Pill tone={TRUCK_PILL_TONE[t.health]}>{t.pill}</Pill>{t.opStatus === "Out of service" && <Pill tone="red">Out of service</Pill>}</span>],
        ["Truck availability", (t) => t.truckAvailableAt], ["Driver availability", (t) => data.drivers[t.driverId]?.availableAt], ["Cost", (t) => `$${Number(t.costPerMile).toFixed(2)}/mi`],
      ],
    },
    drivers: {
      rows: Object.values(data.drivers),
      cols: [["Driver", (d) => <b>{d.name}</b>], ["Phone", (d) => d.phone || "—"], ["Truck", (d) => unit(d.truckId)], ["Driver availability", (d) => d.availableAt], ["Home", (d) => d.homeLocation || "—"]],
    },
    commitments: {
      rows: Object.values(data.trips).sort((a, b) => a.id.localeCompare(b.id)),
      cols: [
        ["Load", (t) => <span className="flex items-center gap-1.5"><b className="tnum">{t.id}</b>{t.protected && <Pill tone="ink"><Lock className="h-3 w-3" /> Protected</Pill>}</span>],
        ["Truck", (t) => unit(t.truckId)], ["Lane", (t) => `${t.origin} → ${t.destination}`], ["Pickup", (t) => t.pickup.window], ["Delivery", (t) => t.delivery.window],
        ["Status", (t) => <Pill tone={STATUS_TONE[t.status] || "grey"}>{t.status}</Pill>], ["Rate", (t) => money(t.revenue)], ["Broker", (t) => t.broker || "—"],
      ],
    },
  };
}

export default function FleetPage() {
  const data = useStore((s) => s.data);
  const setView = useStore((s) => s.setView);
  const [tab, setTab] = useState("trucks");
  const all = tables(data);
  const { rows, cols } = all[tab];
  const type = TABS.find((t) => t[0] === tab)[2];
  return (
    <main className="glass min-h-0 flex-1 overflow-auto p-6 scroll-thin" data-testid="fleet-page">
      <div className="flex items-center gap-3">
        <h1 className="text-[22px] font-semibold tracking-tight">Fleet</h1>
        <div className="ml-4 flex gap-1 rounded-[14px] bg-[#181A1A]/[0.04] p-1" role="tablist" aria-label="Fleet records">
          {TABS.map(([id, label]) => (
            <button key={id} type="button" role="tab" aria-selected={tab === id} data-testid={`fleet-tab-${id}`} onClick={() => setTab(id)} className={cn("flex items-center gap-1.5 rounded-[10px] px-3.5 py-1.5 text-[13px] font-medium transition-colors", tab === id ? "bg-[#181A1A] text-white" : "text-[#4B4F55] hover:bg-white/80")}>
              {label}
              <span className={cn("rounded-md px-1.5 text-[11px] tnum", tab === id ? "bg-white/20" : "bg-white/80")} data-testid={`fleet-tab-count-${id}`}>{all[id].rows.length}</span>
            </button>
          ))}
        </div>
        <div className="ml-auto flex items-center gap-2">
          <button type="button" data-testid="fleet-ai-settings-button" onClick={() => settingsService.open()} className="flex items-center gap-1.5 rounded-[14px] bg-white/85 px-3.5 py-2 text-[13px] font-medium hover:bg-white"><SlidersHorizontal className="h-4 w-4" /> AI settings</button>
          <button type="button" data-testid="fleet-add-button" onClick={() => fleetService.openIntake(type)} className="flex items-center gap-1.5 rounded-[14px] bg-[#AF6EFF] px-3.5 py-2 text-[13px] font-semibold text-white hover:bg-[#9F5BF5]"><Plus className="h-4 w-4" /> Add</button>
          <button type="button" data-testid="fleet-back-to-dashboard" onClick={() => setView("dashboard")} className="flex items-center gap-1.5 rounded-[14px] bg-white/85 px-3.5 py-2 text-[13px] font-medium hover:bg-white"><ArrowLeft className="h-4 w-4" /> Back to map</button>
        </div>
      </div>
      <table className="mt-5 w-full border-separate border-spacing-y-1.5 text-[13px]" data-testid={`fleet-table-${tab}`}>
        <thead>
          <tr className="text-left text-[11.5px] text-[#6B6F76]">{cols.map(([h]) => <th key={h} className="px-4 pb-1 font-medium">{h}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} tabIndex={0} data-testid={`fleet-row-${r.id}`} onClick={() => fleetService.openDrawer(type, r.id)} onKeyDown={(e) => e.key === "Enter" && fleetService.openDrawer(type, r.id)} className="cursor-pointer bg-white/80 transition-colors hover:bg-white">
              {cols.map(([h, f], i) => (
                <td key={h} className={cn("px-4 py-3 text-[#2B2E30] tnum", i === 0 && "rounded-l-[14px]", i === cols.length - 1 && "rounded-r-[14px]")}>{f(r)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-3 text-[11.5px] text-[#9A9DA4]">Click a row to edit. Add opens the guided intake for {TABS.find((t) => t[0] === tab)[1].toLowerCase()}.</p>
    </main>
  );
}
