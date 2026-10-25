import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "../ui/dialog";
import { Textarea } from "../ui/textarea";
import { useStore } from "../../store/useStore";
import { feedbackService } from "../../services";
import { Pill } from "../common/ui";
import { cn } from "../../lib/utils";

const MODES = [
  ["fact", "Correct a fact"],
  ["oneoff", "Just this decision"],
  ["rule", "Make it a rule"],
];
const SCOPES = (data) => [
  ...Object.values(data.drivers).map((d) => ({ scope: "driver", scopeLabel: `Driver: ${d.name}` })),
  ...Object.values(data.trucks).map((t) => ({ scope: "truck", scopeLabel: `Truck: ${t.unit}` })),
  { scope: "carrier", scopeLabel: `Carrier: ${data.carrier.name}` },
];

export function FeedbackDialog() {
  const fb = useStore((s) => s.transient.feedback);
  const data = useStore((s) => s.data);
  const [text, setText] = useState("");
  const [mode, setMode] = useState(null);
  const [scopeLabel, setScopeLabel] = useState("");
  useEffect(() => {
    if (fb?.open) {
      setText(fb.text || "");
      setMode(fb.mode || null);
      setScopeLabel("");
    }
  }, [fb?.open, fb?.text, fb?.mode]);
  if (!fb) return null;
  const a = feedbackService.analyze(text, fb.ctx || {}, data);
  const scope = scopeLabel || a.scopeLabel;
  const apply = () => {
    if (mode === "fact" && a.fact) feedbackService.correctFact(a.fact);
    if (mode === "oneoff") feedbackService.oneOff(fb.ctx || {}, text.trim());
    if (mode === "rule") feedbackService.applyRule({ scope: SCOPES(data).find((s) => s.scopeLabel === scope)?.scope || a.scope, scopeLabel: scope, text: a.ruleText, source: fb.ctx?.source || "Feedback" });
    feedbackService.close();
  };
  const canApply = text.trim() && mode && (mode !== "fact" || a.fact);
  return (
    <Dialog open={fb.open} onOpenChange={(v) => !v && feedbackService.close()}>
      <DialogContent className="max-w-[480px] rounded-[24px] border-white/90 bg-white/95 backdrop-blur-xl" data-testid="feedback-dialog">
        <DialogHeader>
          <DialogTitle>Give FreightOS feedback</DialogTitle>
          <DialogDescription>Tell the AI how to treat this so it learns the right lesson.</DialogDescription>
        </DialogHeader>
        <Textarea value={text} onChange={(e) => setText(e.target.value)} data-testid="feedback-text-input" placeholder="e.g. Driver available Tue 06:00" className="min-h-[64px] rounded-[14px] text-[13px]" />
        <div className="grid grid-cols-3 gap-2" role="radiogroup">
          {MODES.map(([id, label]) => (
            <button key={id} type="button" role="radio" aria-checked={mode === id} data-testid={`feedback-mode-${id}`} onClick={() => setMode(id)} className={cn("rounded-[14px] px-2 py-2.5 text-[12.5px] font-medium ring-1 transition-colors", mode === id ? "bg-[#AF6EFF] text-white ring-[#AF6EFF]" : "bg-white ring-[#181A1A]/10 hover:bg-[#181A1A]/[0.03]")}>{label}</button>
          ))}
        </div>
        {mode === "fact" && (
          <div className="rounded-[14px] bg-[#181A1A]/[0.04] p-3 text-[12.5px]" data-testid="feedback-fact-preview">
            {a.fact ? <>Update <b>{a.fact.label}</b>: <span className="line-through text-[#6B6F76]">{a.fact.old}</span> → <b>{a.fact.value}</b></> : "No fact recognised. Try “Driver available Tue 06:00”."}
          </div>
        )}
        {mode === "oneoff" && <div className="rounded-[14px] bg-[#181A1A]/[0.04] p-3 text-[12.5px]" data-testid="feedback-oneoff-preview">Logged on this decision only. No rule is created.</div>}
        {mode === "rule" && (
          <div className="space-y-2 rounded-[14px] bg-[#AF6EFF]/10 p-3 text-[12.5px]" data-testid="feedback-rule-preview">
            <div className="flex items-center gap-2"><span className="text-[#6B6F76]">Scope</span>
              <select value={scope} onChange={(e) => setScopeLabel(e.target.value)} data-testid="feedback-rule-scope" className="rounded-lg border border-[#181A1A]/10 bg-white px-2 py-1 text-[12.5px]">
                {SCOPES(data).map((s) => <option key={s.scopeLabel}>{s.scopeLabel}</option>)}
              </select>
            </div>
            <div><Pill tone="purple">Rule</Pill> <span className="font-medium" data-testid="feedback-rule-text">{a.ruleText}</span></div>
          </div>
        )}
        <div className="flex justify-end gap-2">
          <button type="button" data-testid="feedback-cancel" onClick={() => feedbackService.close()} className="rounded-[14px] bg-white px-4 py-2 text-[13px] font-medium ring-1 ring-[#181A1A]/10">Cancel</button>
          <button type="button" data-testid="feedback-apply" disabled={!canApply} onClick={apply} className="rounded-[14px] bg-[#181A1A] px-4 py-2 text-[13px] font-semibold text-white disabled:opacity-40">{mode === "rule" ? "Apply rule" : mode === "fact" ? "Apply correction" : "Save"}</button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
