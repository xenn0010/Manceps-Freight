import { useEffect, useState } from "react";
import { Lock, Trash2, BookOpen } from "lucide-react";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "../ui/sheet";
import { Switch } from "../ui/switch";
import { useStore } from "../../store/useStore";
import { settingsService, feedbackService } from "../../services";
import { Pill } from "../common/ui";
import { cn } from "../../lib/utils";

const sel = "h-9 rounded-[10px] border border-[#181A1A]/10 bg-white px-2.5 text-[13px] outline-none focus:border-[#AF6EFF]";

function Row({ label, hint, children, testid }) {
  return (
    <div className="flex items-center gap-3 py-3" data-testid={testid}>
      <div className="min-w-0 flex-1">
        <div className="text-[13px] font-medium">{label}</div>
        {hint && <div className="text-[11.5px] text-[#6B6F76]">{hint}</div>}
      </div>
      {children}
    </div>
  );
}

function FloorInput({ value }) {
  const [v, setV] = useState(String(value));
  useEffect(() => setV(String(value)), [value]);
  const bad = !(Number(v) > 0);
  const commit = () => !bad && settingsService.update("negotiationFloor", Math.round(Number(v) * 100) / 100);
  return (
    <div className="text-right">
      <div className="flex items-center gap-1">
        <span className="text-[13px] text-[#6B6F76]">$</span>
        <input data-testid="settings-floor-input" type="number" step="0.05" value={v} onChange={(e) => setV(e.target.value)} onBlur={commit} onKeyDown={(e) => e.key === "Enter" && commit()} className={cn(sel, "w-20 text-right tnum", bad && "border-[#E5484D]")} />
        <span className="text-[12px] text-[#6B6F76]">/mi</span>
      </div>
      {bad && <p className="mt-1 text-[11px] text-[#C2262B]" data-testid="settings-floor-error">Enter a positive amount</p>}
    </div>
  );
}

export function AiSettingsSheet() {
  const open = useStore((s) => s.transient.settingsOpen);
  const s = useStore((st) => st.data.settings);
  const rulesMap = useStore((st) => st.data.rules);
  const rules = Object.values(rulesMap).sort((a, b) => b.at - a.at);
  return (
    <Sheet open={!!open} onOpenChange={(o) => !o && settingsService.close()}>
      <SheetContent side="right" className="w-[440px] overflow-y-auto border-l-0 bg-[#F4F5F7] p-6 sm:max-w-[440px] scroll-thin" data-testid="ai-settings-sheet">
        <SheetHeader className="text-left">
          <div className="eyebrow">Operating instructions</div>
          <SheetTitle className="text-[20px] font-semibold tracking-tight">AI settings</SheetTitle>
          <SheetDescription className="text-[12px] text-[#6B6F76]">Applied to the next simulated action. Every change is logged.</SheetDescription>
        </SheetHeader>
        <div className="mt-4 divide-y divide-[#181A1A]/[0.06] rounded-[18px] bg-white/85 px-4 ring-1 ring-[#181A1A]/[0.05]">
          <Row label="Negotiation floor" hint="AI won't push a counter below this" testid="settings-floor"><FloorInput value={s.negotiationFloor} /></Row>
          <Row label="Max counter steps" hint="Rounds of counter-offers per load" testid="settings-max-steps">
            <select data-testid="settings-max-steps-select" className={sel} value={s.maxCounterSteps} onChange={(e) => settingsService.update("maxCounterSteps", Number(e.target.value))}>
              {[0, 1, 2, 3, 4].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </Row>
          <Row label="Auto-contact brokers" hint="Let AI email and call brokers during load search" testid="settings-auto-contact">
            <Switch data-testid="settings-auto-contact-switch" checked={s.autoContactBrokers} onCheckedChange={(v) => settingsService.update("autoContactBrokers", v)} />
          </Row>
          <Row label="Require approval before booking" hint={<span className="flex items-center gap-1"><Lock className="h-3 w-3" /> Locked on in demo</span>} testid="settings-require-approval">
            <Switch data-testid="settings-require-approval-switch" checked disabled aria-readonly />
          </Row>
          <Row label="Driver message tone" hint="Used for simulated driver texts" testid="settings-tone">
            <select data-testid="settings-tone-select" className={sel} value={s.driverTone} onChange={(e) => settingsService.update("driverTone", e.target.value)}>
              {["Friendly", "Concise", "Formal"].map((t) => <option key={t}>{t}</option>)}
            </select>
          </Row>
        </div>
        <div className="mt-5 flex items-center gap-2">
          <div className="eyebrow">Rules · {rules.filter((r) => r.status !== "inactive").length} active</div>
          <button type="button" data-testid="settings-add-rule" onClick={() => feedbackService.open("", { source: "AI settings" }, "rule")} className="ml-auto text-[12px] font-medium text-[#7A35DB] hover:underline">Add rule</button>
        </div>
        <ul className="mt-2 space-y-2" data-testid="settings-rules-list">
          {rules.length === 0 && <li className="flex items-center gap-2 rounded-[14px] bg-white/70 px-3.5 py-3 text-[12.5px] text-[#6B6F76]" data-testid="settings-rules-empty"><BookOpen className="h-4 w-4" /> No rules yet.</li>}
          {rules.map((r) => {
            const on = r.status !== "inactive";
            return (
              <li key={r.id} className={cn("flex items-center gap-3 rounded-[14px] bg-white/85 px-3.5 py-3 ring-1 ring-[#181A1A]/[0.05]", !on && "opacity-60")} data-testid={`settings-rule-${r.id}`}>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5"><Pill tone="purple">{r.scopeLabel}</Pill>{!on && <Pill tone="grey" data-testid={`settings-rule-inactive-${r.id}`}>Inactive</Pill>}</div>
                  <div className="mt-1 text-[12.5px] font-medium">{r.text}</div>
                </div>
                <Switch data-testid={`settings-rule-toggle-${r.id}`} checked={on} onCheckedChange={() => settingsService.toggleRule(r.id)} />
                <button type="button" aria-label="Delete rule" data-testid={`settings-rule-delete-${r.id}`} onClick={() => settingsService.deleteRule(r.id)} className="grid h-8 w-8 place-items-center rounded-lg text-[#6B6F76] hover:bg-[#E5484D]/10 hover:text-[#C2262B]"><Trash2 className="h-4 w-4" /></button>
              </li>
            );
          })}
        </ul>
      </SheetContent>
    </Sheet>
  );
}
