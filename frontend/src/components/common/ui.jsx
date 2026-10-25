import { useEffect, useState } from "react";
import { animate } from "framer-motion";
import { cn } from "../../lib/utils";

const TONES = {
  green: "bg-[#A1E688]/50 text-[#2C6A18]",
  purple: "bg-[#AF6EFF]/18 text-[#7A35DB]",
  amber: "bg-[#FFC46D]/55 text-[#8A5200]",
  red: "bg-[#E5484D]/12 text-[#C2282D]",
  grey: "bg-[#181A1A]/[0.06] text-[#4B4F55]",
  ink: "bg-[#181A1A] text-white",
  white: "bg-white text-[#181A1A] shadow-sm",
};

export const Pill = ({ tone = "grey", className, children, ...rest }) => (
  <span className={cn("inline-flex items-center gap-1 rounded-lg px-2 py-[3px] text-[11.5px] font-medium leading-4 whitespace-nowrap", TONES[tone], className)} {...rest}>
    {children}
  </span>
);

export const SimBadge = ({ label = "Simulated", className }) => (
  <span data-testid="simulated-badge" className={cn("inline-flex items-center gap-1 rounded-md border border-dashed border-[#181A1A]/20 px-1.5 py-[1px] text-[10px] font-medium uppercase tracking-[0.06em] text-[#6B6F76]", className)}>
    {label}
  </span>
);

export function AnimatedNumber({ value, format, className, testid }) {
  const [display, setDisplay] = useState(value);
  useEffect(() => {
    const c = animate(display, value, { duration: 0.8, ease: [0.22, 1, 0.36, 1], onUpdate: setDisplay });
    return () => c.stop();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);
  return (
    <span className={cn("tnum", className)} data-testid={testid} data-value={format(value)}>
      {format(Math.abs(display - value) < 0.05 ? value : display)}
    </span>
  );
}

export const TruckImage = ({ purple, className }) => (
  <img src={purple ? "/assets/truck-purple.png" : "/assets/truck-white.png"} alt="53' dry van" draggable={false} className={cn("select-none object-contain", className)} />
);

export const IconButton = ({ className, children, label, ...rest }) => (
  <button
    type="button"
    aria-label={label}
    title={label}
    className={cn("grid h-9 w-9 place-items-center rounded-xl bg-white/80 text-[#181A1A] shadow-[0_1px_2px_rgba(24,26,26,0.06)] transition-colors hover:bg-white", className)}
    {...rest}
  >
    {children}
  </button>
);

export const Field = ({ label, value, testid, tone }) => (
  <div className="rounded-2xl bg-white/70 px-3.5 py-2.5" data-testid={testid}>
    <div className="text-[11px] text-[#6B6F76]">{label}</div>
    <div className={cn("mt-0.5 text-[13.5px] font-medium tnum", tone === "red" && "text-[#C2282D]", tone === "amber" && "text-[#8A5200]")}>{value}</div>
  </div>
);
