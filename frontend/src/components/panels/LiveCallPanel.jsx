import { useEffect, useRef } from "react";
import { PhoneOff, Hand, RotateCcw, PlayCircle } from "lucide-react";
import { useStore } from "../../store/useStore";
import { liveCallService } from "../../services";
import { Pill } from "../common/ui";
import { PanelShell, Section } from "./PanelShell";
import { cn } from "../../lib/utils";

const STEPS = [["dialing", "Dialing"], ["ringing", "Ringing"], ["in_progress", "In call"], ["ended", "Ended"]];
const ACTIVE = ["dialing", "ringing", "in_progress"];

export default function LiveCallPanel({ id }) {
  const c = useStore((s) => s.data.liveCalls[id]);
  const end = useRef(null);
  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [c?.transcript?.length]);
  if (!c) return <PanelShell testid="livecall-panel" eyebrow="Call" title="Call not found" />;
  const idx = c.status === "failed" ? -1 : STEPS.findIndex(([k]) => k === c.status);
  const active = ACTIVE.includes(c.status);
  const sd = c.structuredData || {};
  return (
    <PanelShell testid="livecall-panel" eyebrow={`${c.contact.role === "broker" ? "Broker" : "Driver"} call · ${c.id}`} title={`${c.contact.name}${c.contact.role === "broker" ? ` · ${c.contact.company}` : ""}`}>
      <div className="flex flex-wrap items-center gap-1.5">
        <Pill tone={c.mode === "live" ? "red" : "grey"} data-testid="livecall-mode-badge">{c.mode === "live" ? "● Live call" : "Simulated"}</Pill>
        <Pill tone={c.status === "failed" ? "red" : c.status === "ended" ? "green" : "purple"} data-testid="livecall-status">{c.status === "failed" ? "Failed" : STEPS.find(([k]) => k === c.status)?.[1]}</Pill>
        {c.to && <span className="text-[11.5px] text-[#6B6F76] tnum">{c.to}</span>}
      </div>
      <p className="mt-3 rounded-[14px] bg-white/80 px-3.5 py-2.5 text-[12.5px]" data-testid="livecall-objective"><b>Objective:</b> {c.task.objective}</p>
      <div className="mt-3 flex gap-1" data-testid="livecall-steps">
        {STEPS.map(([k, l], i) => <div key={k} className={cn("h-1.5 flex-1 rounded-full", i <= idx ? "bg-[#AF6EFF]" : "bg-[#181A1A]/10")} title={l} />)}
      </div>
      {c.status === "failed" && (
        <div className="mt-3 rounded-[16px] bg-[#E5484D]/10 p-3.5" data-testid="livecall-failed">
          <div className="text-[13px] font-semibold text-[#C2262B]">Call didn't connect: {c.error}</div>
          <p className="mt-0.5 text-[12px] text-[#6B6F76]">Nothing in the plan changed.</p>
          <div className="mt-2.5 flex gap-2">
            <button type="button" data-testid="livecall-retry" onClick={() => liveCallService.retry(id)} className="flex items-center gap-1.5 rounded-[12px] bg-[#181A1A] px-3 py-2 text-[12.5px] font-semibold text-white"><RotateCcw className="h-3.5 w-3.5" /> Retry</button>
            <button type="button" data-testid="livecall-run-simulated" onClick={() => liveCallService.runSimulated(id)} className="flex items-center gap-1.5 rounded-[12px] bg-white px-3 py-2 text-[12.5px] font-semibold"><PlayCircle className="h-3.5 w-3.5" /> Run simulated call</button>
          </div>
        </div>
      )}
      <Section title="Transcript" testid="livecall-transcript">
        {!c.transcript?.length && <p className="text-[12.5px] text-[#6B6F76]">{active ? "Waiting for the call to connect…" : "No transcript."}</p>}
        <ul className="space-y-2">
          {(c.transcript || []).map((l, i) => (
            <li key={i} className={cn("max-w-[88%] rounded-[14px] px-3 py-2 text-[12.5px]", l.role === "ai" ? "bg-[#AF6EFF]/12 text-[#3B2160]" : "ml-auto bg-white")} data-testid={`livecall-line-${i}`}>
              <div className="mb-0.5 text-[10.5px] font-semibold text-[#6B6F76]">{l.role === "ai" ? "FreightOS" : c.contact.name}</div>
              {l.text}
            </li>
          ))}
        </ul>
        <div ref={end} />
      </Section>
      {c.applied && c.status !== "failed" && (
        <Section title="Outcome" testid="livecall-outcome">
          <div className="text-[13px] font-semibold" data-testid="livecall-outcome-text">{c.outcome}</div>
          {c.summary && <p className="mt-1 text-[12px] text-[#6B6F76]">{c.summary}</p>}
          <dl className="mt-2 grid grid-cols-2 gap-1.5 text-[12px]">
            {Object.entries(sd).map(([k, v]) => (
              <div key={k} className="rounded-[10px] bg-white/80 px-2.5 py-1.5"><dt className="text-[10.5px] text-[#6B6F76]">{k.replace(/_/g, " ")}</dt><dd className="font-medium">{v === true ? "Yes" : v === false ? "No" : v ?? "—"}</dd></div>
            ))}
          </dl>
        </Section>
      )}
      {active && (
        <div className="mt-3 flex gap-2">
          <button type="button" data-testid="livecall-take-over" onClick={() => liveCallService.end(id, true)} className="flex flex-1 items-center justify-center gap-1.5 rounded-[14px] bg-white/85 py-2.5 text-[13px] font-medium"><Hand className="h-4 w-4" /> Take over</button>
          <button type="button" data-testid="livecall-end" onClick={() => liveCallService.end(id)} className="flex flex-1 items-center justify-center gap-1.5 rounded-[14px] bg-[#E5484D] py-2.5 text-[13px] font-semibold text-white"><PhoneOff className="h-4 w-4" /> End call</button>
        </div>
      )}
    </PanelShell>
  );
}
