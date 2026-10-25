import { useState } from "react";
import { motion } from "framer-motion";
import { ArrowUpRight } from "lucide-react";
import { useStore } from "../../store/useStore";
import { openLink } from "../../lib/links";
import { stamp } from "../../lib/format";
import { aiSummary } from "../../lib/selectors";
import { Pill } from "../common/ui";
import { PanelShell } from "./PanelShell";
import { cn } from "../../lib/utils";

const SOURCE = { ai: ["AI", "purple"], dispatcher: ["You", "ink"], broker: ["Broker", "grey"], driver: ["Driver", "green"], system: ["System", "grey"] };
const TABS = [["all", "All"], ["ai", "AI"], ["dispatcher", "You"], ["external", "Brokers & drivers"]];

export default function ActivityPanel() {
  const data = useStore((s) => s.data);
  const [tab, setTab] = useState("all");
  const all = [...data.activity].sort((a, b) => b.seq - a.seq);
  const match = (a) => tab === "all" || (tab === "external" ? ["broker", "driver"].includes(a.source) : a.source === tab);
  const list = all.filter(match);
  return (
    <PanelShell testid="activity-panel" eyebrow="AI activity" title="Activity feed">
      <div className="rounded-[14px] bg-[#AF6EFF]/10 px-3.5 py-2.5 text-[12.5px] font-medium text-[#5B21B6]" data-testid="activity-summary">{aiSummary(data)}</div>
      <div className="rounded-[16px] bg-white/85 p-3.5 ring-1 ring-[#181A1A]/[0.05]" data-testid="truck-104-search-progress">
        <div className="flex items-center gap-2 text-[13px] font-semibold">Truck 104 search <span className="text-[12px] font-normal text-[#6B6F76]">· {data.search104.progress}</span></div>
        <ul className="mt-2 space-y-1 text-[12px]">
          {data.search104.steps.map((s) => <li key={s.label} className="flex items-center gap-2"><Pill tone={s.status === "done" ? "green" : "amber"} className="text-[10.5px]">{s.status === "done" ? "Done" : "Waiting"}</Pill>{s.label}</li>)}
        </ul>
        <div className="mt-2 rounded-xl bg-[#181A1A]/[0.04] px-2.5 py-1.5 text-[12px] tnum" data-testid="truck-104-candidate">Candidate · {data.search104.candidate.lane} · {data.search104.candidate.window} · ${data.search104.candidate.rate} · {data.search104.candidate.broker}</div>
      </div>
      <div className="flex gap-1 rounded-[14px] bg-[#181A1A]/[0.04] p-1" role="tablist">
        {TABS.map(([id, label]) => {
          const count = all.filter((a) => id === "all" || (id === "external" ? ["broker", "driver"].includes(a.source) : a.source === id)).length;
          return (
            <button key={id} type="button" role="tab" aria-selected={tab === id} data-testid={`activity-tab-${id}`} onClick={() => setTab(id)} className={cn("flex flex-1 items-center justify-center gap-1 rounded-[10px] px-2 py-1.5 text-[12px] font-medium transition-colors", tab === id ? "bg-white shadow-sm" : "text-[#6B6F76] hover:text-[#181A1A]")}>
              {label} <span className="text-[11px] text-[#9A9DA4] tnum">{count}</span>
            </button>
          );
        })}
      </div>
      <ol className="space-y-1.5" data-testid="activity-list">
        {list.map((a, i) => {
          const [label, tone] = SOURCE[a.source] || SOURCE.system;
          return (
            <motion.li key={a.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i, 8) * 0.025 }}>
              <button type="button" onClick={() => openLink(a.link)} data-testid={`activity-item-${a.id}`} className="group flex w-full items-start gap-3 rounded-2xl bg-white/80 px-3.5 py-2.5 text-left ring-1 ring-[#181A1A]/[0.04] transition-colors hover:bg-white">
                <span className="w-11 shrink-0 pt-0.5 text-[11.5px] text-[#6B6F76] tnum">{stamp(a.at)}</span>
                <span className="min-w-0 flex-1 text-[13px] leading-5">{a.text}</span>
                <Pill tone={tone} className="text-[10.5px]">{label}</Pill>
                <ArrowUpRight className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#9A9DA4] opacity-0 transition-opacity group-hover:opacity-100" />
              </button>
            </motion.li>
          );
        })}
      </ol>
    </PanelShell>
  );
}
