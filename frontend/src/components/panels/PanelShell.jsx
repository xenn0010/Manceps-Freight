import { ArrowLeft, X } from "lucide-react";
import { useStore } from "../../store/useStore";
import { SimBadge } from "../common/ui";

export function PanelShell({ testid, eyebrow, title, simulated, headerRight, footer, children }) {
  const canBack = useStore((s) => s.ui.panelStack.length > 0);
  const back = useStore((s) => s.back);
  const closePanel = useStore((s) => s.closePanel);
  return (
    <div className="glass-solid flex h-full flex-col overflow-hidden !rounded-[22px]" data-testid={testid}>
      <header className="flex items-start gap-2 px-5 pb-3 pt-4">
        {canBack && (
          <button type="button" aria-label="Back" data-testid="panel-back-button" onClick={back} className="-ml-1 mt-0.5 grid h-8 w-8 place-items-center rounded-xl hover:bg-[#181A1A]/[0.05]">
            <ArrowLeft className="h-4 w-4" />
          </button>
        )}
        <div className="min-w-0 flex-1">
          {eyebrow && <div className="eyebrow truncate">{eyebrow}</div>}
          <h2 className="mt-0.5 truncate text-[18px] font-semibold tracking-tight" data-testid={`${testid}-title`}>{title}</h2>
        </div>
        {simulated && <SimBadge className="mt-1.5" label={simulated === true ? "Simulated" : simulated} />}
        {headerRight}
        <button type="button" aria-label="Close panel" data-testid="panel-close-button" onClick={closePanel} className="-mr-1 grid h-8 w-8 place-items-center rounded-xl hover:bg-[#181A1A]/[0.05]">
          <X className="h-4 w-4" />
        </button>
      </header>
      <div className="scroll-thin min-h-0 flex-1 space-y-4 overflow-y-auto px-5 pb-5">{children}</div>
      {footer && <footer className="border-t border-[#181A1A]/[0.06] bg-white/60 px-5 py-3.5">{footer}</footer>}
    </div>
  );
}

export const Section = ({ title, right, children, testid }) => (
  <section data-testid={testid}>
    <div className="mb-2 flex items-center justify-between">
      <h3 className="text-[13px] font-semibold">{title}</h3>
      {right}
    </div>
    {children}
  </section>
);
