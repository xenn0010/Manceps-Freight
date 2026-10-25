import { useStore } from "../../store/useStore";
import { planLedger, summarize, previewMetrics } from "../../lib/metrics";
import { isAwaitingConfirmation } from "../../lib/selectors";
import { money, num, pct } from "../../lib/format";
import { Pill } from "../common/ui";
import { PanelShell } from "./PanelShell";
import { cn } from "../../lib/utils";

const TITLES = { revenue: "Booked revenue", costs: "After trip costs (est.)", empty: "Empty driving" };

export default function MetricPanel({ id }) {
  const data = useStore((s) => s.data);
  const cpm = data.carrier.costPerMile;
  const items = planLedger(data);
  const m = summarize(items, cpm);
  const rates = [...new Set(items.map((i) => i.cpm ?? cpm))].sort();
  const p = data.proposals["P-1"];
  const preview = isAwaitingConfirmation(p) ? previewMetrics(data, p.offerId) : null;

  const cols = {
    revenue: [["Revenue", (i) => money(i.revenue)]],
    costs: [["Miles", (i) => num(i.loadedMiles + i.emptyMiles)], ["Revenue", (i) => money(i.revenue)], ["Cost", (i) => money((i.loadedMiles + i.emptyMiles) * (i.cpm ?? cpm))]],
    empty: [["Loaded", (i) => num(i.loadedMiles)], ["Empty", (i) => num(i.emptyMiles)]],
  }[id];
  const totals = {
    revenue: [money(m.revenue)],
    costs: [num(m.totalMiles), money(m.revenue), money(m.cost)],
    empty: [num(m.loadedMiles), num(m.emptyMiles)],
  }[id];
  const formula = {
    revenue: `${items.filter((i) => i.revenue).map((i) => money(i.revenue)).join(" + ")} = ${money(m.revenue)}`,
    costs: `${money(m.revenue)} − ${money(m.cost)} = ${money(m.afterCosts)} ${rates.length === 1 ? `at $${rates[0].toFixed(2)}/mi (${num(m.totalMiles)} mi × $${rates[0].toFixed(2)})` : `at per-truck rates (${rates.map((r) => `$${r.toFixed(2)}`).join(", ")}/mi · ${num(m.totalMiles)} mi)`}`,
    empty: `${num(m.emptyMiles)} of ${num(m.totalMiles)} planned miles = ${pct(m.emptyPct)}`,
  }[id];
  const previewText = preview && { revenue: money(preview.revenue), costs: money(preview.afterCosts), empty: `${pct(preview.emptyPct)} (${num(preview.emptyMiles)} of ${num(preview.totalMiles)} mi)` }[id];

  return (
    <PanelShell testid="metric-panel" eyebrow="Current plan · breakdown" title={TITLES[id]}>
      <div className="rounded-[18px] bg-[#181A1A] p-4 text-white" data-testid="metric-formula">
        <div className="text-[11px] uppercase tracking-[0.08em] text-white/60">Formula</div>
        <div className="mt-1 text-[14px] font-medium leading-6 tnum">{formula}</div>
      </div>
      {preview && (
        <div className="flex items-center gap-2 rounded-[14px] bg-[#AF6EFF]/12 px-3.5 py-2.5 text-[12.5px]" data-testid="metric-panel-preview">
          <Pill tone="purple">Preview</Pill> After broker confirms: <span className="font-semibold tnum">{previewText}</span>
        </div>
      )}
      <div className="overflow-hidden rounded-[18px] bg-white/85 ring-1 ring-[#181A1A]/[0.05]">
        <table className="w-full text-[12.5px] tnum" data-testid="metric-breakdown-table">
          <thead>
            <tr className="text-left text-[11px] text-[#6B6F76]">
              <th className="px-3.5 py-2.5 font-medium">Trip / segment</th>
              {cols.map(([h]) => <th key={h} className="px-2 py-2.5 text-right font-medium">{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {items.map((i) => (
              <tr key={i.id} className="border-t border-[#181A1A]/[0.05]" data-testid={`breakdown-row-${i.id}`}>
                <td className={cn("px-3.5 py-2", i.kind === "segment" && "text-[#6B6F76]")}>{i.label}</td>
                {cols.map(([h, f]) => <td key={h} className={cn("px-2 py-2 text-right", id === "empty" && h === "Empty" && i.emptyMiles >= 100 && "font-semibold text-[#8A5200]")}>{f(i)}</td>)}
              </tr>
            ))}
            <tr className="border-t border-[#181A1A]/10 bg-[#181A1A]/[0.03] font-semibold" data-testid="breakdown-total">
              <td className="px-3.5 py-2.5">Total</td>
              {totals.map((t, k) => <td key={k} className="px-2 py-2.5 text-right">{t}</td>)}
            </tr>
          </tbody>
        </table>
      </div>
      <p className="text-[12px] leading-5 text-[#6B6F76]">
        Derived from the shared trip and segment ledger at each truck's $/mi (default $1.80, edit in Fleet). Covers active trips, confirmed pickups in the next 48 h and required repositioning. Booked revenue is not cash collected.
      </p>
    </PanelShell>
  );
}
