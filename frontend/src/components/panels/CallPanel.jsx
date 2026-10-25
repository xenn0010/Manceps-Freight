import { useEffect, useRef } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Pause, Play, Hand, PhoneCall, CheckCircle2, FileText, Sparkles } from "lucide-react";
import { useStore } from "../../store/useStore";
import { callService } from "../../services";
import { openLink } from "../../lib/links";
import { Pill } from "../common/ui";
import { PanelShell, Section } from "./PanelShell";
import { cn } from "../../lib/utils";

const SPEAKER = { ai: "FreightOS", system: "System" };

function statusOf(c) {
  if (c.status === "completed") return { label: "Completed", tone: "green" };
  if (c.status === "taken_over") return { label: "Dispatcher took over", tone: "ink" };
  if (c.paused) return { label: "Paused", tone: "amber" };
  return { label: "Live", tone: "purple" };
}

export default function CallPanel({ id }) {
  const data = useStore((s) => s.data);
  const c = data.calls[id];
  const doc = data.documents["DOC-RC-1"];
  const bottom = useRef(null);
  const lines = c ? callService.transcript(c) : [];
  const facts = c ? callService.facts(c) : [];
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [lines.length]);
  if (!c) return null;
  const st = statusOf(c);
  const live = c.status === "in_progress";
  const elapsed = c.lineIndex * 9 + 4;

  const footer = live ? (
    <div className="grid grid-cols-2 gap-2">
      <button type="button" data-testid={c.paused ? "call-resume-button" : "call-pause-button"} onClick={() => (c.paused ? callService.resume(id) : callService.pause(id))} className="flex items-center justify-center gap-1.5 rounded-[14px] bg-white py-2.5 text-[13px] font-medium ring-1 ring-[#181A1A]/10 hover:bg-[#181A1A]/[0.03]">
        {c.paused ? <Play className="h-4 w-4" /> : <Pause className="h-4 w-4" />} {c.paused ? "Resume" : "Pause"}
      </button>
      <button type="button" data-testid="call-take-over-button" onClick={() => callService.takeOver(id)} className="flex items-center justify-center gap-1.5 rounded-[14px] bg-[#181A1A] py-2.5 text-[13px] font-medium text-white">
        <Hand className="h-4 w-4" /> Take over
      </button>
    </div>
  ) : c.status === "taken_over" && !c.manualConfirmed ? (
    <button type="button" data-testid="call-log-confirmation-button" onClick={() => callService.logBrokerConfirmation(id)} className="w-full rounded-[14px] bg-[#AF6EFF] py-2.5 text-[13px] font-semibold text-white">
      Log broker's written confirmation
    </button>
  ) : (
    <button type="button" data-testid="call-open-decision-button" onClick={() => openLink(c.proposalId ? { type: "decision", id: c.proposalId } : { type: "truck", id: c.truckId })} className="w-full rounded-[14px] bg-white py-2.5 text-[13px] font-medium ring-1 ring-[#181A1A]/10">{c.proposalId ? "Back to decision" : "Back to truck"}</button>
  );

  return (
    <PanelShell testid="call-panel" eyebrow={c.kind === "reappointment" ? "Broker call · L-201 re-appointment" : "Broker call · O-1"} title={c.contact.company} simulated footer={footer}>
      <div className="flex items-center gap-3 rounded-[18px] bg-white/85 p-3.5 ring-1 ring-[#181A1A]/[0.05]" data-testid="call-contact">
        <span className="relative grid h-10 w-10 place-items-center rounded-xl bg-[#181A1A] text-white">
          {live && !c.paused && <span className="ping-soft absolute inset-0 rounded-xl bg-[#AF6EFF]/60" />}
          <PhoneCall className="relative h-4 w-4" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-[14px] font-semibold">{c.contact.name}</div>
          <div className="text-[12px] text-[#6B6F76] tnum">{c.contact.company} · {c.contact.phone}</div>
        </div>
        <div className="text-right">
          <Pill tone={st.tone} data-testid="call-status">{st.label}</Pill>
          <div className="mt-1 text-[11.5px] text-[#6B6F76] tnum">0:{String(Math.min(elapsed, 59)).padStart(2, "0")}</div>
        </div>
      </div>
      <div className="rounded-[14px] bg-[#181A1A]/[0.04] px-3.5 py-2.5 text-[12.5px]" data-testid="call-objective">
        <span className="text-[#6B6F76]">Objective · </span>{c.objective}
      </div>
      <Section title="Transcript" testid="call-transcript" right={<span className="text-[11.5px] text-[#6B6F76] tnum">{lines.length}/{callService.totalLines(c)}</span>}>
        <ol className="space-y-2">
          <AnimatePresence initial={false}>
            {lines.map((l, i) => (
              <motion.li key={i} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }} data-testid={`transcript-line-${i + 1}`}
                className={cn("rounded-2xl px-3.5 py-2 text-[13px] leading-5", l.speaker === "ai" ? "mr-6 bg-[#AF6EFF]/12" : l.speaker === "broker" ? "ml-6 bg-white/90 ring-1 ring-[#181A1A]/[0.05]" : "bg-[#A1E688]/35 text-center text-[12.5px] font-medium")}>
                {l.speaker !== "system" && <div className="mb-0.5 text-[11px] font-medium text-[#6B6F76]">{SPEAKER[l.speaker] || c.contact.name}</div>}
                {l.text}
              </motion.li>
            ))}
          </AnimatePresence>
          {live && !c.paused && <li className="mr-24 h-9 shimmer !rounded-2xl" aria-label="Speaking" data-testid="transcript-typing" />}
          {c.paused && <li className="text-center text-[12px] text-[#8A5200]" data-testid="transcript-paused">Paused · transcript on hold</li>}
          <li ref={bottom} />
        </ol>
      </Section>
      <Section title="Extracted facts" testid="call-facts">
        <ul className="grid grid-cols-2 gap-2">
          {facts.map((f) => (
            <motion.li key={f.key} initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} className="rounded-2xl bg-white/85 px-3 py-2 ring-1 ring-[#181A1A]/[0.05]" data-testid={`call-fact-${f.key}`}>
              <div className="flex items-center gap-1 text-[11px] text-[#6B6F76]"><CheckCircle2 className="h-3 w-3 text-[#4E9A33]" /> {f.label}</div>
              <div className="text-[12.5px] font-medium tnum">{f.value}</div>
            </motion.li>
          ))}
          {facts.length === 0 && <li className="col-span-2 flex items-center gap-2 text-[12px] text-[#6B6F76]"><Sparkles className="h-3.5 w-3.5 text-[#AF6EFF]" /> Listening for rate and windows…</li>}
        </ul>
      </Section>
      <Section title="Outcome" testid="call-outcome">
        <div className={cn("flex items-center gap-2 rounded-[14px] px-3.5 py-2.5 text-[13px] font-medium", c.outcome ? "bg-[#A1E688]/35" : "bg-[#181A1A]/[0.04] text-[#6B6F76]")} data-testid="call-outcome-value">
          {c.outcome ? <CheckCircle2 className="h-4 w-4 text-[#2C6A18]" /> : null}
          {c.outcome || "Waiting for written confirmation"}
        </div>
      </Section>
      {c.kind !== "reappointment" && <Section title="Written terms vs offer" testid="call-terms-comparison">
        <table className="w-full text-[12px] tnum">
          <thead><tr className="text-left text-[11px] text-[#6B6F76]"><th className="pb-1 font-medium" /><th className="pb-1 font-medium">Offer</th><th className="pb-1 font-medium">Written</th><th /></tr></thead>
          <tbody>
            {doc.fields.slice(0, 4).map((f) => (
              <tr key={f.label} className="border-t border-[#181A1A]/[0.06]">
                <td className="py-1.5 pr-2 text-[#4B4F55]">{f.label}</td>
                <td className="py-1.5 pr-2">{f.offer}</td>
                <td className="py-1.5 pr-2">{f.written}</td>
                <td className="py-1.5"><CheckCircle2 className="h-3.5 w-3.5 text-[#4E9A33]" /></td>
              </tr>
            ))}
          </tbody>
        </table>
        <button type="button" data-testid="call-open-document" onClick={() => openLink({ type: "document", id: doc.id })} className="mt-2 inline-flex items-center gap-1.5 text-[12px] font-medium text-[#7A35DB] hover:underline">
          <FileText className="h-3.5 w-3.5" /> Open rate confirmation
        </button>
      </Section>}
    </PanelShell>
  );
}
