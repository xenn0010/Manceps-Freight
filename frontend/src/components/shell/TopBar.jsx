import { LayoutGrid, Truck, Mic, RotateCcw, Clock3, SlidersHorizontal } from "lucide-react";
import { motion } from "framer-motion";
import { useStore } from "../../store/useStore";
import { headerSummary } from "../../lib/selectors";
import { clockLabel } from "../../lib/format";
import { voiceService, settingsService } from "../../services";
import { NotificationsPopover } from "./NotificationsPopover";
import { DemoScriptPopover } from "./DemoScriptPopover";
import { IconButton } from "../common/ui";
import { cn } from "../../lib/utils";

const NAV = [
  { id: "dashboard", label: "Dashboard", icon: LayoutGrid },
  { id: "fleet", label: "Fleet", icon: Truck },
];

function PillNav() {
  const view = useStore((s) => s.ui.view);
  const setView = useStore((s) => s.setView);
  return (
    <nav className="flex items-center gap-2" aria-label="Primary">
      {NAV.map(({ id, label, icon: Icon }) => {
        const active = view === id;
        return (
          <button
            key={id}
            type="button"
            data-testid={`nav-${id}`}
            aria-current={active ? "page" : undefined}
            aria-label={label}
            title={label}
            onClick={() => setView(id)}
            className={cn(
              "flex h-11 items-center gap-2 rounded-[14px] transition-[background-color,box-shadow,padding] duration-200",
              active ? "bg-white px-4 shadow-[0_2px_8px_-2px_rgba(24,26,26,0.12)]" : "w-11 justify-center bg-white/45 hover:bg-white/80"
            )}
          >
            <Icon className="h-[18px] w-[18px]" strokeWidth={1.8} />
            {active && <span className="text-[14.5px] font-medium">{label}</span>}
          </button>
        );
      })}
    </nav>
  );
}

function MicButton() {
  const status = useStore((s) => s.transient.voice.status);
  const live = status !== "idle";
  return (
    <button
      type="button"
      data-testid="header-mic-button"
      onClick={() => voiceService.toggle()}
      aria-pressed={live}
      className={cn(
        "relative flex h-10 items-center gap-2 whitespace-nowrap rounded-[14px] pl-2 pr-3.5 text-[13.5px] font-medium transition-colors",
        live ? "bg-[#AF6EFF] text-white" : "bg-[#181A1A] text-white hover:bg-[#2a2d2d]"
      )}
    >
      <span className="relative grid h-7 w-7 place-items-center rounded-[10px] bg-white/15">
        {live && <span className="ping-soft absolute inset-0 rounded-[10px] bg-white/40" />}
        <Mic className="h-4 w-4" />
      </span>
      {live ? "Listening… tap to stop" : "Talk to FreightOS"}
    </button>
  );
}

export function TopBar() {
  const data = useStore((s) => s.data);
  const clockMin = useStore((s) => s.clockMin);
  const setTransient = useStore((s) => s.setTransient);
  return (
    <header className="flex h-[68px] shrink-0 items-center gap-3" data-testid="top-bar">
      <div className="flex min-w-0 flex-1 basis-0 items-center gap-3">
        <div className="flex items-center gap-2" data-testid="brand-logo">
          <svg width="26" height="26" viewBox="0 0 26 26" aria-hidden="true">
            <path d="M8 2h10l6 6v10l-6 6H8l-6-6V8z" fill="none" stroke="#181A1A" strokeWidth="3.2" strokeLinejoin="round" />
          </svg>
          <span className="whitespace-nowrap text-[18px] font-semibold tracking-tight">FreightOS.</span>
        </div>
        <span className="h-7 w-px bg-[#181A1A]/10" />
        <div className="min-w-0 leading-tight">
          <div className="flex items-center gap-2">
            <span className="whitespace-nowrap text-[14px] font-semibold" data-testid="company-name">{data.carrier.name}</span>
            <span className="whitespace-nowrap rounded-md bg-white/70 px-1.5 py-[1px] text-[11.5px] font-medium tnum" data-testid="truck-count">{Object.keys(data.trucks).length} trucks</span>
          </div>
          <div className="truncate text-[12px] text-[#6B6F76]" data-testid="status-summary">{headerSummary(data)}</div>
        </div>
      </div>
      <PillNav />
      <div className="flex flex-1 basis-0 items-center justify-end gap-1.5">
        <motion.div
          key={clockMin}
          initial={{ opacity: 0.4 }}
          animate={{ opacity: 1 }}
          className="flex h-10 items-center gap-1.5 whitespace-nowrap rounded-[14px] bg-white/60 px-3 text-[12.5px] font-medium tnum"
          data-testid="scenario-clock"
        >
          <Clock3 className="h-3.5 w-3.5 text-[#6B6F76]" />
          {clockLabel(clockMin)}
        </motion.div>
        <span className="whitespace-nowrap rounded-lg bg-[#AF6EFF]/18 px-2 py-1 text-[11px] font-semibold uppercase tracking-[0.06em] text-[#7A35DB]" data-testid="demo-data-badge">
          Demo data
        </span>
        <MicButton />
        <IconButton label="AI settings" data-testid="header-ai-settings-button" onClick={() => settingsService.open()}>
          <SlidersHorizontal className="h-[17px] w-[17px]" />
        </IconButton>
        <NotificationsPopover />
        <DemoScriptPopover />
        <IconButton label="Reset demo" data-testid="reset-demo-button" onClick={() => setTransient({ resetOpen: true })}>
          <RotateCcw className="h-[17px] w-[17px]" />
        </IconButton>
        <div className="ml-1 hidden items-center gap-2 min-[1440px]:flex" data-testid="user-chip">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-[#181A1A] text-[12px] font-semibold text-white">JD</span>
          <div className="hidden whitespace-nowrap leading-tight min-[1600px]:block">
            <div className="text-[13px] font-medium">Jordan Diaz</div>
            <div className="text-[11.5px] text-[#6B6F76]">Dispatcher</div>
          </div>
        </div>
      </div>
    </header>
  );
}
