import { motion } from "framer-motion";
import { FileText } from "lucide-react";
import { useStore } from "../../store/useStore";
import { openLink } from "../../lib/links";
import { stamp } from "../../lib/format";
import { PanelShell } from "./PanelShell";
import { cn } from "../../lib/utils";

const NAME = { ai: "FreightOS", broker: "Broker", driver: "Driver" };

export default function ThreadPanel({ id }) {
  const conv = useStore((s) => s.data.conversations[id]);
  if (!conv) return null;
  return (
    <PanelShell testid="thread-panel" eyebrow={conv.channel} title={conv.counterpart} simulated>
      <ol className="space-y-2.5" data-testid="thread-messages">
        {conv.messages.map((m) => (
          <motion.li key={m.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className={cn("flex", m.from === "ai" ? "justify-end" : "")} data-testid={`thread-message-${m.id}`}>
            <div className={cn("max-w-[86%] rounded-2xl px-3.5 py-2.5 text-[13px] leading-5", m.from === "ai" ? "rounded-br-md bg-[#AF6EFF]/15" : "rounded-bl-md bg-white ring-1 ring-[#181A1A]/[0.06]")}>
              <div className="mb-0.5 flex gap-2 text-[11px] font-medium text-[#6B6F76]">
                <span>{NAME[m.from]}</span>
                <span className="tnum">{stamp(m.at)}</span>
              </div>
              {m.text}
              {m.attachment && (
                <button type="button" onClick={() => openLink(m.attachment)} className="mt-2 flex items-center gap-1.5 rounded-xl bg-[#181A1A]/[0.04] px-2.5 py-1.5 text-[12px] font-medium hover:bg-[#181A1A]/[0.07]" data-testid="thread-attachment">
                  <FileText className="h-3.5 w-3.5 text-[#7A35DB]" /> {m.attachment.label}
                </button>
              )}
            </div>
          </motion.li>
        ))}
      </ol>
      <p className="text-center text-[11.5px] text-[#9A9DA4]">Simulated thread · no real messages are sent</p>
    </PanelShell>
  );
}
