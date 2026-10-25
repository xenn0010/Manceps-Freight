import { useEffect, useRef } from "react";
import { motion } from "framer-motion";
import { Sparkles, ArrowRight, ArrowUpRight, AlertTriangle } from "lucide-react";
import { useStore } from "../../store/useStore";
import { aiService, feedbackService } from "../../services";
import { openLink } from "../../lib/links";
import { stamp } from "../../lib/format";
import { PanelShell } from "./PanelShell";
import { cn } from "../../lib/utils";

function AiMessage({ m }) {
  return (
    <div className="space-y-2.5" data-testid={`chat-ai-${m.intent}`}>
      <p className="text-[13.5px] leading-[1.55]">{m.text}</p>
      {m.items?.length > 0 && (
        <ul className="space-y-1.5">
          {m.items.map((it, i) => (
            <li key={i}>
              <button type="button" data-testid={`chat-item-link-${i + 1}`} onClick={() => openLink(it.link)} className={cn("flex w-full items-center gap-2.5 rounded-2xl px-3 py-2.5 text-left transition-colors", it.tone === "high" ? "bg-[#FFC46D]/35 hover:bg-[#FFC46D]/50" : "bg-white hover:bg-white/70 ring-1 ring-[#181A1A]/[0.06]")}>
                {it.tone === "high" ? <AlertTriangle className="h-4 w-4 text-[#8A5200]" /> : <Sparkles className="h-4 w-4 text-[#AF6EFF]" />}
                <span className="min-w-0 flex-1">
                  <span className="block text-[13px] font-semibold">{it.label}</span>
                  <span className="block text-[11.5px] text-[#6B6F76] tnum">{it.sub}</span>
                </span>
                <ArrowRight className="h-4 w-4 text-[#6B6F76]" />
              </button>
            </li>
          ))}
        </ul>
      )}
      {m.bullets && (
        <ul className="list-disc space-y-0.5 pl-4 text-[12.5px] text-[#3f4247]">{m.bullets.map((b) => <li key={b}>{b}</li>)}</ul>
      )}
      {m.evidence && (
        <div className="flex flex-wrap gap-1.5" data-testid="chat-evidence">
          {m.evidence.map((e) => (
            <button key={e.label} type="button" onClick={() => openLink(e.link)} className="inline-flex items-center gap-1 rounded-lg bg-white px-2 py-1 text-[11.5px] font-medium ring-1 ring-[#181A1A]/[0.06] hover:bg-[#181A1A]/[0.03]">
              {e.label} <ArrowUpRight className="h-3 w-3 text-[#9A9DA4]" />
            </button>
          ))}
        </div>
      )}
      {m.cta && (
        <button type="button" data-testid="chat-open-decision" onClick={() => openLink(m.cta.link)} className="inline-flex items-center gap-1.5 rounded-xl bg-[#AF6EFF] px-3 py-2 text-[12.5px] font-semibold text-white hover:bg-[#9F5BF5]">
          {m.cta.label} <ArrowRight className="h-3.5 w-3.5" />
        </button>
      )}
      {m.feedback && (
        <div className="flex flex-wrap gap-1.5" data-testid="chat-feedback-options">
          {[["fact", "Correct a fact"], ["oneoff", "Just this decision"], ["rule", "Make it a rule"]].map(([id, l]) => (
            <button key={id} type="button" data-testid={`chat-feedback-${id}`} onClick={() => feedbackService.open(m.feedback.text, { truckId: "T-101", proposalId: "P-1", source: "Chat" }, id)} className="rounded-xl bg-white px-2.5 py-1.5 text-[12px] font-medium ring-1 ring-[#181A1A]/[0.08] hover:bg-[#181A1A]/[0.03]">{l}</button>
          ))}
        </div>
      )}
      {m.suggestions && (
        <div className="flex flex-wrap gap-1.5" data-testid="chat-fallback-suggestions">
          {m.suggestions.map((s) => (
            <button key={s} type="button" onClick={() => aiService.ask(s)} className="rounded-xl bg-white px-2.5 py-1.5 text-[12px] font-medium ring-1 ring-[#181A1A]/[0.08] hover:bg-[#181A1A]/[0.03]">{s}</button>
          ))}
        </div>
      )}
    </div>
  );
}

export default function ChatPanel() {
  const chat = useStore((s) => s.chat);
  const thinking = aiService.isThinking(chat);
  const end = useRef(null);
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [chat.messages.length]);
  return (
    <PanelShell testid="chat-panel" eyebrow="Ask FreightOS" title="Conversation" simulated="Scripted AI">
      {chat.messages.length === 0 && <p className="text-[13px] text-[#6B6F76]">Ask anything in the bar below, or tap an example.</p>}
      {chat.messages.map((m) => (
        <motion.div key={m.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }} className={m.role === "user" ? "flex justify-end" : ""}>
          {m.role === "user" ? (
            <div className="max-w-[85%] rounded-2xl rounded-br-md bg-[#181A1A] px-3.5 py-2 text-[13.5px] text-white" data-testid="chat-user-message">{m.text}</div>
          ) : (
            <div className="rounded-2xl rounded-tl-md bg-[#181A1A]/[0.035] p-3.5">
              <div className="mb-1.5 flex items-center gap-1.5 text-[11px] font-medium text-[#6B6F76]"><Sparkles className="h-3 w-3 text-[#AF6EFF]" /> FreightOS · {stamp(m.at)}</div>
              <AiMessage m={m} />
            </div>
          )}
        </motion.div>
      ))}
      {thinking && (
        <div className="space-y-2 rounded-2xl bg-[#181A1A]/[0.035] p-3.5" data-testid="chat-thinking">
          <div className="flex items-center gap-1.5 text-[11px] font-medium text-[#7A35DB]"><Sparkles className="h-3 w-3" /> AI is working…</div>
          <div className="shimmer h-3 w-11/12" />
          <div className="shimmer h-3 w-3/4" />
          <div className="shimmer h-3 w-1/2" />
        </div>
      )}
      <div ref={end} />
    </PanelShell>
  );
}
