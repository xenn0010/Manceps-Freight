import { ListChecks, Check } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "../ui/popover";
import { useStore } from "../../store/useStore";
import { DEMO_STEPS, DEMO_SCENARIOS, demoScript } from "../../services";
import { cn } from "../../lib/utils";

const Kbd = ({ children }) => <kbd className="rounded-md border border-[#181A1A]/15 bg-white px-1.5 py-[1px] text-[10.5px] font-medium">{children}</kbd>;

export function DemoScriptPopover() {
  const open = useStore((s) => s.transient.demoOpen);
  const step = useStore((s) => s.ui.demoStep);
  const setTransient = useStore((s) => s.setTransient);
  return (
    <Popover open={open} onOpenChange={(v) => setTransient({ demoOpen: v })}>
      <PopoverTrigger asChild>
        <button type="button" aria-label="Demo script" title="Demo script (D)" data-testid="demo-script-button" className="grid h-10 w-10 place-items-center rounded-[14px] bg-white/80 transition-colors hover:bg-white">
          <ListChecks className="h-[18px] w-[18px]" strokeWidth={1.8} />
        </button>
      </PopoverTrigger>
      <PopoverContent align="center" sideOffset={10} className="w-[320px] rounded-[20px] border-white/90 bg-white/95 p-3 backdrop-blur-xl" data-testid="demo-script-panel">
        <div className="flex items-center justify-between px-1">
          <span className="text-[14px] font-semibold">Demo script</span>
          <span className="text-[11.5px] text-[#6B6F76] tnum">{Math.min(step, DEMO_STEPS.length)}/{DEMO_STEPS.length}</span>
        </div>
        <ol className="mt-2 space-y-0.5">
          {DEMO_STEPS.map((s, i) => (
            <li key={s.id}>
              <button
                type="button"
                data-testid={`demo-step-${s.id}`}
                onClick={() => demoScript.runStep(i)}
                className={cn("flex w-full items-center gap-2.5 rounded-xl px-2 py-1.5 text-left transition-colors hover:bg-[#181A1A]/[0.04]", i === step && "bg-[#AF6EFF]/10")}
              >
                <span className={cn("grid h-5 w-5 shrink-0 place-items-center rounded-full text-[10.5px] font-semibold tnum", i < step ? "bg-[#181A1A] text-white" : i === step ? "bg-[#AF6EFF] text-white" : "bg-[#181A1A]/[0.07]")}>
                  {i < step ? <Check className="h-3 w-3" /> : i + 1}
                </span>
                <span className="min-w-0">
                  <span className="block text-[12.5px] font-medium">{s.label}</span>
                  <span className="block text-[11px] text-[#6B6F76]">{s.hint}</span>
                </span>
              </button>
            </li>
          ))}
        </ol>
        <div className="mt-2 border-t border-[#181A1A]/[0.06] px-1 pt-2">
          <div className="eyebrow mb-1">Scenarios</div>
          <div className="flex flex-wrap gap-1.5">
            {DEMO_SCENARIOS.map((s) => (
              <button key={s.id} type="button" data-testid={`demo-scenario-${s.id}`} onClick={s.run} className="rounded-xl bg-[#181A1A]/[0.05] px-2.5 py-1.5 text-[12px] font-medium hover:bg-[#181A1A]/[0.09]">{s.label}</button>
            ))}
          </div>
        </div>
        <div className="mt-2 flex items-center justify-between gap-2 border-t border-[#181A1A]/[0.06] px-1 pt-2.5">
          <span className="text-[11px] text-[#6B6F76]"><Kbd>N</Kbd> / <Kbd>→</Kbd> next · <Kbd>⇧R</Kbd> reset</span>
          <button
            type="button"
            data-testid="demo-next-step-button"
            disabled={step >= DEMO_STEPS.length}
            onClick={() => demoScript.next()}
            className="rounded-xl bg-[#AF6EFF] px-3 py-1.5 text-[12.5px] font-semibold text-white transition-opacity disabled:opacity-40"
          >
            Next step
          </button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
