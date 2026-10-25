import { BookOpen } from "lucide-react";
import { useStore } from "../../store/useStore";
import { stamp } from "../../lib/format";
import { feedbackService } from "../../services";
import { Pill } from "../common/ui";
import { PanelShell, Section } from "./PanelShell";

export default function RulesPanel() {
  const data = useStore((s) => s.data);
  const rules = Object.values(data.rules).sort((a, b) => b.at - a.at);
  return (
    <PanelShell testid="rules-panel" eyebrow="Operating instructions" title="AI instructions">
      <button type="button" data-testid="rules-add-feedback" onClick={() => feedbackService.open("", { source: "AI instructions" }, "rule")} className="w-full rounded-[14px] bg-[#AF6EFF] py-2.5 text-[13px] font-semibold text-white">Add instruction</button>
      <Section title={`Rules · ${rules.filter((r) => r.status !== "inactive").length} active`} testid="rules-list">
        {rules.length === 0 ? (
          <p className="flex items-center gap-2 text-[12.5px] text-[#6B6F76]" data-testid="rules-empty"><BookOpen className="h-4 w-4" /> No rules yet. Choose “Make it a rule” on any feedback.</p>
        ) : (
          <ul className="space-y-2">
            {rules.map((r) => (
              <li key={r.id} className="rounded-2xl bg-white/85 p-3 ring-1 ring-[#181A1A]/[0.05]" data-testid={`rule-${r.id}`}>
                <div className="flex items-center gap-2"><Pill tone="purple">{r.scopeLabel}</Pill>{r.status === "inactive" && <Pill tone="grey" data-testid={`rule-inactive-${r.id}`}>Inactive</Pill>}<span className="ml-auto text-[11px] text-[#9A9DA4] tnum">{stamp(r.at)}</span></div>
                <div className="mt-1.5 text-[13px] font-medium">{r.text}</div>
                <div className="mt-0.5 text-[11.5px] text-[#6B6F76]">Source: {r.source}</div>
              </li>
            ))}
          </ul>
        )}
      </Section>
      <Section title="Fact corrections" testid="corrections-list">
        {data.corrections.length === 0 ? <p className="text-[12.5px] text-[#6B6F76]">None yet.</p> : (
          <ul className="space-y-1.5">
            {data.corrections.map((c) => (
              <li key={c.id} className="rounded-2xl bg-white/85 px-3 py-2 text-[12.5px]" data-testid={`correction-${c.id}`}>{c.label}: <span className="line-through text-[#6B6F76]">{c.old}</span> → <b>{c.value}</b> <span className="text-[#9A9DA4] tnum">· {stamp(c.at)}</span></li>
            ))}
          </ul>
        )}
      </Section>
    </PanelShell>
  );
}
