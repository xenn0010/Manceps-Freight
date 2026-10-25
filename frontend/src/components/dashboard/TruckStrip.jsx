import { motion } from "framer-motion";
import { useStore } from "../../store/useStore";
import { Pill, TruckImage } from "../common/ui";
import { cn } from "../../lib/utils";

export const TRUCK_PILL_TONE = { working: "grey", risk: "amber", on_track: "green", idle: "grey" };

export function TruckStrip() {
  const data = useStore((s) => s.data);
  const selected = useStore((s) => s.ui.selectedTruckId);
  const selectTruck = useStore((s) => s.selectTruck);
  const closePanel = useStore((s) => s.closePanel);
  const offerLive = ["proposed", "awaiting_broker"].includes(data.offers["O-1"].status);
  return (
    <section className="grid h-[76px] shrink-0 gap-3" style={{ gridTemplateColumns: `repeat(${Object.keys(data.trucks).length}, minmax(0, 1fr))` }} data-testid="truck-strip" aria-label="Trucks">
      {Object.values(data.trucks).map((t) => {
        const isSel = selected === t.id;
        const driver = data.drivers[t.driverId];
        return (
          <motion.button
            key={t.id}
            type="button"
            data-testid={`truck-card-${t.unit}`}
            aria-pressed={isSel}
            onClick={() => (isSel ? closePanel() : selectTruck(t.id))}
            animate={{ y: isSel ? -3 : 0 }}
            transition={{ type: "spring", stiffness: 420, damping: 30 }}
            className={cn(
              "relative flex items-center overflow-hidden rounded-[18px] pl-4 text-left transition-[background-color,box-shadow,opacity] duration-200",
              isSel ? "bg-white shadow-[0_16px_32px_-16px_rgba(24,26,26,0.35)] ring-1 ring-[#AF6EFF]/40" : "bg-white/45 hover:bg-white/75",
              selected && !isSel && "opacity-70"
            )}
          >
            <div className="relative z-10 min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className={cn("text-[16px] font-semibold tnum", !isSel && "text-[#181A1A]/80")}>#{t.unit}</span>
                <Pill tone={TRUCK_PILL_TONE[t.health]} className="text-[10.5px]">{t.pill}</Pill>
                {t.id === "T-101" && offerLive && <Pill tone="purple" className="text-[10.5px]" data-testid="truck-card-101-proposed">Proposed</Pill>}
              </div>
              <div className="mt-0.5 truncate text-[12px] text-[#6B6F76]">{driver?.name} · {t.equipment}</div>
            </div>
            <TruckImage purple={isSel} className={cn("relative -mr-3 h-[58px] max-w-[210px] object-right", Object.keys(data.trucks).length > 4 ? "w-[34%]" : "w-[46%]")} />
          </motion.button>
        );
      })}
    </section>
  );
}
