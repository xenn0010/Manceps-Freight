import { motion } from "framer-motion";
import { Check } from "lucide-react";
import { STEPS } from "../../lib/selectors";
import { cn } from "../../lib/utils";

export function StatusStepper({ reached, halted }) {
  return (
    <ol className="grid grid-cols-3 gap-x-2 gap-y-2.5" data-testid="status-stepper" data-reached={reached}>
      {STEPS.map((label, i) => {
        const done = i < reached;
        const current = i === reached - 1;
        const final = reached === STEPS.length;
        return (
          <li key={label} data-testid={`stepper-step-${i + 1}`} data-state={done ? (current && !final ? "current" : "done") : "todo"} className="min-w-0">
            <div className="relative h-[6px] overflow-hidden rounded-full bg-[#181A1A]/[0.08]">
              <motion.span
                initial={false}
                animate={{ scaleX: done ? 1 : 0 }}
                transition={{ duration: 0.5, delay: done ? i * 0.05 : 0, ease: [0.22, 1, 0.36, 1] }}
                className={cn("absolute inset-0 origin-left rounded-full", halted ? "bg-[#9A9DA4]" : "bg-[#AF6EFF]")}
              />
              {current && !final && !halted && <span className="shimmer absolute inset-0 !rounded-full opacity-70" />}
            </div>
            <div className={cn("mt-1.5 flex items-center gap-1 text-[11px] leading-[14px]", done ? "font-medium text-[#181A1A]" : "text-[#9A9DA4]")}>
              {done && !current && <Check className="mt-[1px] h-2.5 w-2.5 shrink-0" />}
              {done && current && final && <Check className="mt-[1px] h-2.5 w-2.5 shrink-0" />}
              <span className="truncate">{label}</span>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
