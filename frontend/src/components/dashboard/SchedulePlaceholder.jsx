import { motion } from "framer-motion";
import { CalendarRange } from "lucide-react";
import { useStore } from "../../store/useStore";
import { Pill } from "../common/ui";

export function SchedulePlaceholder() {
  const data = useStore((s) => s.data);
  const selected = useStore((s) => s.ui.selectedTruckId);
  const t = selected && data.trucks[selected];
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="absolute inset-0 z-[5] grid place-items-center bg-[#EEEFF1]/90 backdrop-blur-md" data-testid="schedule-placeholder">
      <div className="glass-solid w-[min(520px,80%)] p-6">
        <div className="flex items-center gap-2">
          <span className="grid h-9 w-9 place-items-center rounded-xl bg-[#AF6EFF]/18 text-[#7A35DB]"><CalendarRange className="h-[18px] w-[18px]" /></span>
          <div>
            <div className="text-[16px] font-semibold">Schedule</div>
            <div className="text-[12.5px] text-[#6B6F76]">Coming in next phase</div>
          </div>
          {t && <Pill tone="purple" className="ml-auto" data-testid="schedule-selected-truck">Truck {t.unit} selected</Pill>}
        </div>
        <div className="mt-5 space-y-2.5" aria-hidden="true">
          {Object.values(data.trucks).map((x, i) => (
            <div key={x.id} className="flex items-center gap-3">
              <span className={`w-10 text-[12px] font-medium tnum ${x.id === selected ? "text-[#7A35DB]" : "text-[#6B6F76]"}`}>#{x.unit}</span>
              <div className="relative h-5 flex-1 rounded-lg bg-[#181A1A]/[0.05]">
                <span className="shimmer absolute inset-y-1" style={{ left: `${8 + i * 9}%`, width: `${26 + ((i * 17) % 30)}%` }} />
              </div>
            </div>
          ))}
        </div>
        <p className="mt-4 text-[12.5px] text-[#6B6F76]">Rows per truck, day boundaries, now marker, rest blocks and tentative proposals arrive in Phase 2. Your selection is kept.</p>
      </div>
    </motion.div>
  );
}
