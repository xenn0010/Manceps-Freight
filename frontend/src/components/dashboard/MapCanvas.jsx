import { useEffect, useMemo, useRef, useState } from "react";
import { Plus, Minus, Maximize2, Map as MapIcon, CalendarRange, Sparkles } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { useStore } from "../../store/useStore";
import { createMapAdapter } from "../../map/mapAdapter";
import { buildMapFeatures } from "../../map/features";
import { aiSummary } from "../../lib/selectors";
import { IconButton, Pill } from "../common/ui";
import { MapLegend } from "./MapLegend";
import { ScheduleView } from "./ScheduleView";
import { executionService } from "../../services/phase2Services";
import { FastForward, BookOpen } from "lucide-react";
import { cn } from "../../lib/utils";

function ModeSwitch() {
  const mode = useStore((s) => s.ui.mapMode);
  const setMapMode = useStore((s) => s.setMapMode);
  const opts = [
    { id: "map", label: "Map", icon: MapIcon },
    { id: "schedule", label: "Schedule", icon: CalendarRange },
  ];
  return (
    <div className="flex gap-1 rounded-[14px] bg-white/80 p-1 shadow-sm backdrop-blur" role="tablist" data-testid="map-schedule-switch">
      {opts.map(({ id, label, icon: Icon }) => (
        <button
          key={id}
          type="button"
          role="tab"
          aria-selected={mode === id}
          data-testid={`mode-${id}`}
          onClick={() => setMapMode(id)}
          className={cn("flex items-center gap-1.5 rounded-[10px] px-3 py-1.5 text-[12.5px] font-medium transition-colors", mode === id ? "bg-[#181A1A] text-white" : "text-[#4B4F55] hover:bg-white")}
        >
          <Icon className="h-3.5 w-3.5" /> {label}
        </button>
      ))}
    </div>
  );
}

function AiPill() {
  const data = useStore((s) => s.data);
  const togglePanel = useStore((s) => s.togglePanel);
  return (
    <button type="button" data-testid="ai-activity-summary" onClick={() => togglePanel("activity")} className="flex max-w-full items-center gap-2 rounded-[14px] bg-white/85 py-1.5 pl-1.5 pr-3 text-[12.5px] shadow-sm backdrop-blur transition-colors hover:bg-white">
      <span className="relative grid h-6 w-6 shrink-0 place-items-center rounded-[9px] bg-[#AF6EFF] text-white">
        <span className="ping-soft absolute inset-0 rounded-[9px] bg-[#AF6EFF]/60" />
        <Sparkles className="relative h-3.5 w-3.5" />
      </span>
      <span className="truncate font-medium" data-testid="ai-activity-summary-text">{aiSummary(data)}</span>
      <span className="shrink-0 text-[#7A35DB]">Activity</span>
    </button>
  );
}

function Tooltip({ hover, data }) {
  if (!hover) return null;
  const t = data.trucks[hover.id];
  const tone = { on_track: "green", risk: "amber", working: "grey", idle: "grey" }[t.health];
  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      className="pointer-events-none absolute z-20 w-max -translate-x-1/2 rounded-[14px] bg-white/95 px-3 py-2 shadow-[0_12px_28px_-12px_rgba(24,26,26,0.35)] backdrop-blur"
      style={{ left: hover.x, top: hover.y - 74 }}
      data-testid="truck-tooltip"
    >
      <div className="flex items-center gap-2 text-[13px] font-semibold">
        Truck {t.unit} <span className="font-normal text-[#6B6F76]">·</span> <span data-testid="truck-tooltip-driver">{data.drivers[t.driverId].name}</span>
      </div>
      <div className="mt-0.5 flex items-center gap-1.5 text-[12px]">
        <Pill tone={tone} className="text-[10.5px]">{t.pill}</Pill>
        <span className="text-[#4B4F55]" data-testid="truck-tooltip-status">{t.statusShort}</span>
      </div>
    </motion.div>
  );
}

export function MapCanvas() {
  const ref = useRef(null);
  const api = useRef(null);
  const data = useStore((s) => s.data);
  const selected = useStore((s) => s.ui.selectedTruckId);
  const fitNonce = useStore((s) => s.ui.fitNonce);
  const mode = useStore((s) => s.ui.mapMode);
  const [hover, setHover] = useState(null);
  const features = useMemo(() => buildMapFeatures(data, selected), [data, selected]);
  const featuresRef = useRef(features);
  featuresRef.current = features;

  useEffect(() => {
    api.current = createMapAdapter(ref.current, {
      onTruckHover: (id, pt) => setHover(id ? { id, ...pt } : null),
      onTruckClick: (id) => useStore.getState().selectTruck(id),
      onBackgroundClick: () => {
        const s = useStore.getState();
        if (s.ui.selectedTruckId) s.closePanel();
      },
    });
    return () => api.current.destroy();
  }, []);

  useEffect(() => {
    api.current.setRoutes(features.routes);
    api.current.setStops(features.stops);
    api.current.setTrucks(features.trucks);
  }, [features]);

  useEffect(() => {
    const f = featuresRef.current;
    if (selected) api.current.fitTo(f.focus[selected], { maxZoom: 7.6 });
    else api.current.fitTo(f.fleet, { maxZoom: 7.2 });
  }, [selected, fitNonce]);

  const fitFleet = () => {
    if (selected) api.current.fitTo(featuresRef.current.focus[selected], { maxZoom: 7.6 });
    else api.current.fitTo(featuresRef.current.fleet, { maxZoom: 7.2 });
  };

  return (
    <section className="glass relative min-h-0 flex-1 overflow-hidden !rounded-[22px] !bg-[#EEEFF1]" data-testid="map-canvas">
      <div className="absolute inset-0">
        <div ref={ref} className="h-full w-full" data-testid="map-container" />
      </div>
      <Tooltip hover={hover} data={data} />
      <div className="pointer-events-none absolute inset-x-3 top-3 z-10 flex items-start justify-between gap-3">
        <div className="pointer-events-auto"><ModeSwitch /></div>
        <div className="pointer-events-auto min-w-0 flex-1 flex justify-center"><AiPill /></div>
        {mode === "map" && <div className="pointer-events-auto flex flex-col gap-1.5" data-testid="map-controls">
          <IconButton label="Zoom in" data-testid="map-zoom-in" onClick={() => api.current.zoomIn()}><Plus className="h-4 w-4" /></IconButton>
          <IconButton label="Zoom out" data-testid="map-zoom-out" onClick={() => api.current.zoomOut()}><Minus className="h-4 w-4" /></IconButton>
          <IconButton label={selected ? "Fit selected truck" : "Fit fleet"} data-testid="map-fit-fleet" onClick={fitFleet}><Maximize2 className="h-4 w-4" /></IconButton>
        </div>}
      </div>
      {mode === "map" && <div className="absolute bottom-3 left-3 z-10"><MapLegend /></div>}
      {mode === "map" && <div className="absolute right-3 top-[156px] z-[6] flex flex-col items-end gap-1.5">
        <button type="button" data-testid="ai-instructions-button" onClick={() => useStore.getState().togglePanel("rules")} className="flex items-center gap-1.5 rounded-[12px] bg-white/90 px-3 py-2 text-[12.5px] font-medium shadow-sm hover:bg-white">
          <BookOpen className="h-3.5 w-3.5" /> AI instructions <span className="text-[#9A9DA4] tnum">{Object.keys(data.rules).length}</span>
        </button>
        <button type="button" data-testid="advance-time-button" onClick={() => executionService.advanceTime()} className="flex items-center gap-1.5 rounded-[12px] bg-[#181A1A] px-3 py-2 text-[12.5px] font-medium text-white shadow-sm hover:bg-[#2a2d2d]">
          <FastForward className="h-3.5 w-3.5" /> Advance time
        </button>
      </div>}
      <AnimatePresence>{mode === "schedule" && <ScheduleView />}</AnimatePresence>
    </section>
  );
}
