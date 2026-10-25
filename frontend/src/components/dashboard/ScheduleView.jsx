import { useState } from "react";
import { motion } from "framer-motion";
import { ChevronLeft, ChevronRight, ArrowRight, FastForward } from "lucide-react";
import { useStore } from "../../store/useStore";
import { executionService } from "../../services";
import { scheduleRows } from "../../lib/schedule";
import { openLink } from "../../lib/links";
import { hhmm } from "../../lib/format";
import { cn } from "../../lib/utils";

const DAYS = ["Mon 26", "Tue 27", "Wed 28", "Thu 29"];
const KIND = {
  job: "bg-[#2B2E30] text-white",
  proposed: "border-2 border-dashed border-[#AF6EFF] bg-[#AF6EFF]/15 text-[#6D28D9]",
  empty: "border-2 border-dotted border-[#9A9DA4] bg-white/50 text-[#4B4F55]",
  rest: "text-[#6B6F76] [background:repeating-linear-gradient(135deg,rgba(24,26,26,0.05)_0_6px,rgba(24,26,26,0.015)_6px_12px)]",
  available: "border border-dashed border-[#181A1A]/10 text-[#9A9DA4]",
  risk: "bg-[#FFC46D] text-[#6B3E00]",
  conflict: "border-2 border-[#E5484D] bg-[#E5484D]/10 text-[#C2282D]",
  window: "border-2 border-[#6CC24A] bg-[#A1E688]/30 text-[#2C6A18]",
};
const LANE = { 0: "top-[8px] h-[23px]", 1: "top-[35px] h-[23px]", undefined: "top-[8px] h-[50px]" };

export function ScheduleView() {
  const data = useStore((s) => s.data);
  const ui = useStore((s) => s.ui);
  const clock = useStore((s) => s.clockMin);
  const [range, setRange] = useState("3d");
  const [start, setStart] = useState(360);
  const vs = range === "3d" ? 360 : start;
  const ve = range === "3d" ? 4320 : start + 1440;
  const pct = (m) => ((m - vs) / (ve - vs)) * 100;
  const rows = scheduleRows(data, ui);
  const ticks = [];
  for (let m = Math.ceil(vs / 360) * 360; m <= ve; m += 360) ticks.push(m);

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="absolute inset-0 z-[5] flex flex-col bg-[#F3F4F6] px-4 pb-4 pt-16" data-testid="schedule-view">
      <div className="mb-2 flex items-center gap-2 pl-[120px]">
        <div className="flex gap-1 rounded-[12px] bg-white/80 p-1" role="tablist">
          {[["3d", "Mon–Wed"], ["1d", "24 h"]].map(([id, l]) => (
            <button key={id} type="button" role="tab" aria-selected={range === id} data-testid={`schedule-range-${id}`} onClick={() => setRange(id)} className={cn("rounded-[9px] px-2.5 py-1 text-[12px] font-medium", range === id ? "bg-[#181A1A] text-white" : "text-[#4B4F55]")}>{l}</button>
          ))}
        </div>
        {range === "1d" && (
          <>
            <button type="button" aria-label="Earlier" data-testid="schedule-prev" onClick={() => setStart(Math.max(360, start - 720))} className="grid h-7 w-7 place-items-center rounded-lg bg-white/80"><ChevronLeft className="h-4 w-4" /></button>
            <button type="button" aria-label="Later" data-testid="schedule-next" onClick={() => setStart(Math.min(2880, start + 720))} className="grid h-7 w-7 place-items-center rounded-lg bg-white/80"><ChevronRight className="h-4 w-4" /></button>
          </>
        )}
        <span className="ml-auto text-[11.5px] text-[#6B6F76]">Solid job · dashed purple proposed · dotted empty · hatched rest</span>
        <button type="button" data-testid="schedule-advance-time-button" onClick={() => executionService.advanceTime()} className="flex items-center gap-1.5 rounded-[12px] bg-[#181A1A] px-3 py-1.5 text-[12px] font-medium text-white hover:bg-[#2a2d2d]"><FastForward className="h-3.5 w-3.5" /> Advance time</button>
      </div>
      <div className="relative min-h-0 flex-1 overflow-hidden rounded-[18px] bg-white/70 p-3 pl-[120px]">
        <div className="relative h-6 text-[11px] text-[#6B6F76]" data-testid="schedule-scale">
          {ticks.filter((m) => pct(m) > 3).map((m) => (
            <span key={m} className="absolute -translate-x-1/2 whitespace-nowrap tnum" style={{ left: `${pct(m)}%` }}>
              {m % 1440 === 0 ? <b className="text-[#181A1A]" data-testid={`schedule-day-${DAYS[m / 1440].slice(0, 3).toLowerCase()}`}>{DAYS[m / 1440]}</b> : hhmm(m)}
            </span>
          ))}
          {vs < 1440 && <b className="absolute -left-[108px] text-[#181A1A]" data-testid="schedule-day-mon">{DAYS[0]}</b>}
        </div>
        <div className="relative">
          {ticks.filter((m) => m % 1440 === 0).map((m) => <span key={m} className="absolute inset-y-0 w-px bg-[#181A1A]/15" style={{ left: `${pct(m)}%` }} />)}
          {clock >= vs && clock <= ve && (
            <span className="absolute -top-1 bottom-0 z-10 w-[2px] bg-[#AF6EFF]" style={{ left: `${pct(clock)}%` }} data-testid="schedule-now-marker">
              <span className="absolute -top-5 left-1/2 -translate-x-1/2 rounded-md bg-[#AF6EFF] px-1.5 text-[10.5px] font-semibold text-white tnum">Now {hhmm(clock)}</span>
            </span>
          )}
          {rows.map((r) => {
            const t = data.trucks[r.truckId];
            const sel = ui.selectedTruckId === r.truckId;
            return (
              <div key={r.truckId} className={cn("relative h-[66px] border-b border-[#181A1A]/[0.06]", sel && "bg-[#AF6EFF]/[0.07]")} data-testid={`schedule-row-${t.unit}`} data-selected={sel}>
                <button type="button" onClick={() => useStore.getState().selectTruck(r.truckId)} className="absolute -left-[112px] top-3 w-[100px] text-left">
                  <div className={cn("text-[14px] font-semibold tnum", sel && "text-[#7A35DB]")}>#{t.unit}</div>
                  <div className="truncate text-[11.5px] text-[#6B6F76]">{data.drivers[t.driverId].name}</div>
                </button>
                {r.blocks.filter((x) => x.end > vs && x.start < ve).map((x) => {
                  const cutR = x.end > ve;
                  const cutL = x.start < vs;
                  const left = Math.max(0, pct(x.start));
                  const width = Math.min(100, pct(x.end)) - left;
                  return (
                    <button
                      key={x.id}
                      type="button"
                      title={x.label}
                      data-testid={`schedule-block-${x.id}`}
                      data-kind={x.kind}
                      onClick={() => openLink(x.link)}
                      className={cn("absolute flex items-center overflow-hidden rounded-[9px] px-2 text-left text-[11.5px] font-medium transition-[filter] hover:brightness-95", KIND[x.kind], LANE[x.lane])}
                      style={{ left: `calc(${left}% + 1px)`, width: `calc(${width}% - 2px)` }}
                    >
                      {cutL && <span className="mr-1">←</span>}
                      <span className="truncate">{x.label}</span>
                      {cutR && <span className="ml-auto flex shrink-0 items-center gap-0.5 pl-1 text-[10.5px] font-semibold" data-testid={`schedule-continues-${x.id}`}>continues <ArrowRight className="h-3 w-3" /></span>}
                    </button>
                  );
                })}
              </div>
            );
          })}
        </div>
      </div>
    </motion.div>
  );
}
