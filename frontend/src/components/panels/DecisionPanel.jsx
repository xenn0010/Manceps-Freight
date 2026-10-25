import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ChevronDown, CheckCircle2, FileText, MessageSquare, PhoneCall, Hand, XCircle, Lock, ArrowUpRight } from "lucide-react";
import { useStore } from "../../store/useStore";
import { offerEconomics, previewMetrics, truckCpm } from "../../lib/metrics";
import { STATUS_LABEL, stepReached } from "../../lib/selectors";
import { money, signedMoney, pct, num } from "../../lib/format";
import { openLink } from "../../lib/links";
import { dispatchService, termsService, feedbackService } from "../../services";
import { Pill } from "../common/ui";

function VersionDiff({ p, offer, seg, cpm }) {
  const cur = p.versions[p.versions.length - 1];
  const prev = p.versions[p.versions.length - 2];
  const ec = (rate) => offerEconomics({ ...offer, rate }, seg, cpm);
  const a = ec(prev.rate);
  const b = ec(cur.rate);
  const rows = [["Rate", money(prev.rate), money(cur.rate)], ["Contribution", money(a.contribution), money(b.contribution)], ["vs empty return", signedMoney(a.delta), signedMoney(b.delta)]];
  return (
    <div className="rounded-[18px] bg-white/85 p-3.5 ring-1 ring-[#AF6EFF]/30" data-testid="version-diff">
      <div className="flex items-center gap-2 text-[13px] font-semibold">v{prev.version} → v{cur.version} <span className="text-[11.5px] font-normal text-[#6B6F76]">{cur.source} · asked {money(cur.target)}</span>
        {p.reviewRequired && <Pill tone="amber" className="ml-auto" data-testid="review-required-chip">Review required</Pill>}
      </div>
      <table className="mt-2 w-full text-[12.5px] tnum"><tbody>
        {rows.map(([k, x, y]) => <tr key={k} className="border-t border-[#181A1A]/[0.06]"><td className="py-1.5 text-[#4B4F55]">{k}</td><td className="py-1.5 text-[#9A9DA4] line-through">{x}</td><td className="py-1.5 font-semibold" data-testid={`diff-${k.split(" ")[0].toLowerCase()}`}>{y}</td></tr>)}
      </tbody></table>
      <p className="mt-1.5 text-[11px] text-[#6B6F76]">The v{prev.version} approval no longer applies.</p>
    </div>
  );
}
import { StopLine } from "../common/charts";
import { Textarea } from "../ui/textarea";
import { PanelShell, Section } from "./PanelShell";
import { StatusStepper } from "./StatusStepper";
import { cn } from "../../lib/utils";

function Disclosure({ title, testid, children, defaultOpen = false, right }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-[18px] bg-white/75 ring-1 ring-[#181A1A]/[0.05]">
      <button type="button" aria-expanded={open} data-testid={`${testid}-toggle`} onClick={() => setOpen(!open)} className="flex w-full items-center gap-2 px-4 py-3 text-left">
        <span className="text-[13px] font-semibold">{title}</span>
        <span className="ml-auto">{right}</span>
        <ChevronDown className={cn("h-4 w-4 transition-transform", open && "rotate-180")} />
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.22 }} className="overflow-hidden" data-testid={testid}>
            <div className="px-4 pb-4">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

const EvidenceLink = ({ icon: Icon, label, link, testid }) => (
  <button type="button" data-testid={testid} onClick={() => openLink(link)} className="inline-flex items-center gap-1.5 rounded-xl bg-white/85 px-2.5 py-1.5 text-[12px] font-medium ring-1 ring-[#181A1A]/[0.06] transition-colors hover:bg-white">
    <Icon className="h-3.5 w-3.5 text-[#7A35DB]" /> {label} <ArrowUpRight className="h-3 w-3 text-[#9A9DA4]" />
  </button>
);

function Economics({ e, offer }) {
  const rows = [
    ["Revenue", money(offer.rate), "$0"],
    ["Miles", `${e.miles} mi`, `${e.altMiles} mi`],
    ["", `${offer.loadedMiles} loaded · ${offer.emptyToPickup} + ${offer.emptyAfter} empty`, "all empty"],
    ["Cost @ $1.80/mi", money(e.cost), money(e.altCost)],
    ["Contribution", money(e.contribution), money(e.altContribution)],
  ];
  return (
    <table className="w-full text-[12.5px] tnum" data-testid="economics-table">
      <thead>
        <tr className="text-left text-[11px] text-[#6B6F76]">
          <th className="pb-1.5 font-medium" />
          <th className="pb-1.5 font-medium">O-1 return load</th>
          <th className="pb-1.5 font-medium">Empty return</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(([k, a, b], i) => (
          <tr key={i} className={cn(i === 4 && "font-semibold", k && "border-t border-[#181A1A]/[0.06]")}>
            <td className="py-1.5 pr-2 text-[#4B4F55]">{k}</td>
            <td className={cn("py-1.5", !k && "pt-0 text-[11px] text-[#6B6F76]")}>{a}</td>
            <td className={cn("py-1.5", !k && "pt-0 text-[11px] text-[#6B6F76]", i === 4 && "text-[#C2282D]")}>{b}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function PreviewBlock({ data, offerId, label }) {
  const m = previewMetrics(data, offerId);
  return (
    <div className="rounded-[18px] bg-[#AF6EFF]/10 p-3.5 ring-1 ring-[#AF6EFF]/25" data-testid="decision-preview">
      <div className="flex items-center gap-2 text-[12px] font-medium text-[#7A35DB]"><Pill tone="purple">Preview</Pill> {label}</div>
      <div className="mt-2 grid grid-cols-3 gap-2 text-[12px] tnum">
        <div><div className="text-[#6B6F76]">Booked revenue</div><div className="text-[15px] font-semibold" data-testid="decision-preview-revenue">{money(m.revenue)}</div></div>
        <div><div className="text-[#6B6F76]">After trip costs</div><div className="text-[15px] font-semibold" data-testid="decision-preview-costs">{money(m.afterCosts)}</div></div>
        <div><div className="text-[#6B6F76]">Empty driving</div><div className="text-[15px] font-semibold" data-testid="decision-preview-empty">{pct(m.emptyPct)}</div><div className="text-[10.5px] text-[#6B6F76]">{num(m.emptyMiles)} of {num(m.totalMiles)} mi</div></div>
      </div>
    </div>
  );
}

function Actions({ p }) {
  const [mode, setMode] = useState(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [target, setTarget] = useState("1200");
  const [cls, setCls] = useState("oneoff");
  const open = ["proposal_ready", "changes_requested"].includes(p.status);
  if (p.handledBy === "dispatcher") {
    const callTaken = p.callId && useStore.getState().data.calls[p.callId]?.status === "taken_over";
    return (
      <div className="space-y-2.5" data-testid="decision-handled-by-you">
        <div className="flex items-center gap-2 rounded-[14px] bg-[#181A1A] px-3.5 py-2.5 text-[13px] font-medium text-white"><Hand className="h-4 w-4" /> You're handling this · AI paused on this task</div>
        {!callTaken && !["booked", "rejected"].includes(p.status) && (
          <button type="button" data-testid="hand-back-button" onClick={() => dispatchService.handBack(p.id)} className="w-full rounded-[14px] bg-white py-2.5 text-[13px] font-medium ring-1 ring-[#181A1A]/10 hover:bg-[#181A1A]/[0.03]">Hand back to AI</button>
        )}
      </div>
    );
  }
  if (!open) return null;
  if (mode) {
    const isReject = mode === "reject";
    const ok = text.trim() || (!isReject && Number(target) > 0);
    const submit = () => {
      if (isReject) {
        const reason = text.trim();
        dispatchService.reject(p.id, reason);
        if (cls === "rule") feedbackService.open(reason, { proposalId: p.id, truckId: p.truckId, source: "Reject reason" }, "rule");
        else feedbackService.oneOff({ proposalId: p.id }, reason);
      } else dispatchService.requestChanges(p.id, text, Number(target) || null);
      setMode(null);
      setText("");
    };
    return (
      <div className="space-y-2.5" data-testid={`${mode}-form`}>
        {!isReject && (
          <label className="flex items-center gap-2 text-[12.5px]">
            <span className="text-[#6B6F76]">Target rate $</span>
            <input type="number" value={target} onChange={(e) => setTarget(e.target.value)} data-testid="changes-target-rate-input" className="w-28 rounded-xl border border-[#181A1A]/10 bg-white px-2.5 py-1.5 text-[13px] tnum" />
          </label>
        )}
        <Textarea
          autoFocus
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={isReject ? "Reason for rejecting (required)" : "Note for the broker (optional)"}
          data-testid={`${mode}-reason-input`}
          className="min-h-[64px] rounded-[14px] bg-white text-[13px]"
        />
        {isReject && (
          <div className="flex gap-1.5 text-[12px]" role="radiogroup">
            {[["oneoff", "Just this decision"], ["rule", "Make it a rule"]].map(([id, l]) => (
              <button key={id} type="button" role="radio" aria-checked={cls === id} data-testid={`reject-class-${id}`} onClick={() => setCls(id)} className={cn("rounded-xl px-2.5 py-1.5 font-medium ring-1", cls === id ? "bg-[#181A1A] text-white ring-[#181A1A]" : "bg-white ring-[#181A1A]/10")}>{l}</button>
            ))}
          </div>
        )}
        <div className="flex gap-2">
          <button type="button" onClick={() => { setMode(null); setText(""); }} className="flex-1 rounded-[14px] bg-white py-2.5 text-[13px] font-medium ring-1 ring-[#181A1A]/10" data-testid={`${mode}-cancel-button`}>Cancel</button>
          <button
            type="button"
            disabled={!ok}
            data-testid={`${mode}-confirm-button`}
            onClick={submit}
            className={cn("flex-1 rounded-[14px] py-2.5 text-[13px] font-semibold text-white transition-opacity disabled:cursor-not-allowed disabled:opacity-40", isReject ? "bg-[#181A1A]" : "bg-[#AF6EFF]")}
          >
            {isReject ? "Reject proposal" : "Send request"}
          </button>
        </div>
      </div>
    );
  }
  return (
    <div className="space-y-2">
      <button
        type="button"
        data-testid="approve-request-confirmation-button"
        disabled={busy || p.termsFlag === "differ"}
        onClick={() => {
          setBusy(true);
          dispatchService.approve(p.id);
        }}
        className="w-full rounded-[14px] bg-[#AF6EFF] py-3 text-[14px] font-semibold text-white shadow-[0_10px_24px_-12px_rgba(175,110,255,0.9)] transition-colors hover:bg-[#9F5BF5] disabled:opacity-60"
      >
        Approve and request confirmation
      </button>
      <div className="grid grid-cols-3 gap-2">
        {p.status === "proposal_ready" ? (
          <button type="button" data-testid="request-changes-button" onClick={() => setMode("changes")} className="rounded-[14px] bg-white py-2 text-[12.5px] font-medium ring-1 ring-[#181A1A]/10 hover:bg-[#181A1A]/[0.03]">Request changes</button>
        ) : (
          <span className="grid place-items-center rounded-[14px] bg-[#181A1A]/[0.04] text-[11.5px] text-[#6B6F76]">Changes sent</span>
        )}
        <button type="button" data-testid="reject-button" onClick={() => setMode("reject")} className="rounded-[14px] bg-white py-2 text-[12.5px] font-medium ring-1 ring-[#181A1A]/10 hover:bg-[#181A1A]/[0.03]">Reject</button>
        <button type="button" data-testid="take-over-button" onClick={() => dispatchService.takeOver(p.id)} className="rounded-[14px] bg-white py-2 text-[12.5px] font-medium ring-1 ring-[#181A1A]/10 hover:bg-[#181A1A]/[0.03]">Take over</button>
      </div>
    </div>
  );
}

function StatusLine({ p, data }) {
  const call = p.callId && data.calls[p.callId];
  if (p.status === "rejected") return <div className="flex items-center gap-2 rounded-[14px] bg-[#181A1A]/[0.05] px-3.5 py-2.5 text-[13px]" data-testid="decision-rejected"><XCircle className="h-4 w-4" /> Rejected · “{p.rejectReason}”</div>;
  if (p.status === "changes_requested") return <div className="rounded-[14px] bg-[#FFC46D]/30 px-3.5 py-2.5 text-[13px]" data-testid="decision-changes-requested">Changes requested · “{p.changeNote}” {p.targetRate ? <span className="text-[#6B6F76]">Waiting for the broker's counter…</span> : null}</div>;
  if (!call && !["booked"].includes(p.status)) return null;
  return (
    <div className="flex flex-wrap items-center gap-2" data-testid="decision-status-chips">
      <Pill tone={p.status === "booked" ? "green" : "purple"} data-testid="booking-status-chip">{p.status === "booked" ? <CheckCircle2 className="h-3 w-3" /> : null}{p.status === "booked" ? "Booked" : STATUS_LABEL[p.status]}</Pill>
      {p.status === "booked" && (
        <Pill tone={p.driverStatus === "acknowledged" ? "green" : p.driverStatus === "instructions_sent" ? "purple" : "grey"} data-testid="driver-status-chip">
          {p.driverStatus === "acknowledged" ? "Driver acknowledged · Ava Reed" : p.driverStatus === "instructions_sent" ? "Driver instructions sent" : "Preparing driver instructions"}
        </Pill>
      )}
      {call && <button type="button" data-testid="open-call-button" onClick={() => openLink({ type: "call", id: call.id })} className="ml-auto inline-flex items-center gap-1.5 rounded-xl bg-[#181A1A] px-2.5 py-1.5 text-[12px] font-medium text-white"><PhoneCall className="h-3.5 w-3.5" /> {call.status === "in_progress" ? "Live call" : "View call"}</button>}
    </div>
  );
}

export default function DecisionPanel({ id }) {
  const data = useStore((s) => s.data);
  const p = data.proposals[id];
  const offer = data.offers[p.offerId];
  const alt = data.offers["O-2"];
  const seg = data.segments[p.replacesSegmentId];
  const e = offerEconomics(offer, seg, truckCpm(data, offer.truckId));
  const doc = data.documents[offer.documentId];
  const call = p.callId && data.calls[p.callId];
  const awaiting = ["terms_approved", "awaiting_broker"].includes(p.status);
  return (
    <PanelShell testid="decision-panel" eyebrow={`Return load · Truck 101 · v${p.version}`} title={`Book ${offer.origin === "Los Angeles" ? "LA" : offer.origin} → ${offer.destination} · ${money(offer.rate)}`} simulated="Demo data" footer={<Actions key={`${p.status}-${p.handledBy}`} p={p} />}>
      <StatusStepper reached={stepReached(p)} halted={["rejected", "changes_requested"].includes(p.status) || p.handledBy === "dispatcher"} />
      <StatusLine p={p} data={data} />
      <div className="rounded-[20px] bg-white/85 p-4 ring-1 ring-[#181A1A]/[0.05]" data-testid="decision-lead">
        <div className="flex items-center gap-2">
          <Pill tone="purple">Recommended</Pill>
          <span className="text-[12px] text-[#6B6F76]">{offer.broker} · {offer.pickup.window.slice(0, 3)}</span>
        </div>
        <div className="mt-3 grid grid-cols-2 gap-3">
          <div className="wash-green rounded-2xl p-3">
            <div className="text-[26px] font-semibold leading-8 tracking-tight tnum" data-testid="decision-delta">{signedMoney(e.delta)}</div>
            <div className="text-[12px] text-[#3f4247]">planned contribution vs empty return</div>
          </div>
          <div className="rounded-2xl bg-[#181A1A]/[0.04] p-3">
            <div className="text-[17px] font-semibold leading-8 tnum" data-testid="decision-schedule-fit">In SF {offer.arriveSf}</div>
            <div className="text-[12px] text-[#3f4247]">protects Wed 08:00 pickup <Lock className="inline h-3 w-3" /></div>
          </div>
        </div>
        <p className="mt-2.5 text-[11.5px] text-[#6B6F76]" data-testid="decision-contribution-note">{signedMoney(e.delta)} is improved planned contribution, not extra revenue or realized savings.</p>
      </div>
      {p.versions?.length > 1 && <VersionDiff p={p} offer={offer} seg={seg} cpm={truckCpm(data, offer.truckId)} />}
      {p.termsFlag && (
        <div className={cn("rounded-[18px] p-3.5 ring-1", p.termsFlag === "differ" ? "bg-[#E5484D]/10 ring-[#E5484D]/40" : "bg-[#181A1A]/[0.04] ring-[#181A1A]/10")} data-testid="terms-differ-warning">
          <div className="flex items-center gap-2 text-[13px] font-semibold"><XCircle className="h-4 w-4 text-[#C2282D]" /> Written terms differ</div>
          <div className="mt-1 text-[12px] text-[#4B4F55]">Rate con: {doc.fields[0].written} vs agreed {money(offer.rate)}. {p.termsFlag === "differ" ? "Booking is blocked until you review." : "Reviewed by you."}</div>
          {p.termsFlag === "differ" && <button type="button" data-testid="terms-reviewed-button" onClick={() => termsService.markReviewed()} className="mt-2 rounded-xl bg-[#181A1A] px-3 py-1.5 text-[12px] font-semibold text-white">Reviewed</button>}
        </div>
      )}
      {!["booked", "rejected"].includes(p.status) && <PreviewBlock data={data} offerId={offer.id} label={awaiting ? "Applies once the broker confirms in writing" : "Effect on the plan if booked"} />}
      <Disclosure title="Economics" testid="decision-economics" right={<span className="text-[12px] text-[#6B6F76] tnum">{money(e.contribution)} vs {money(e.altContribution)}</span>}>
        <Economics e={e} offer={offer} />
      </Disclosure>
      <Disclosure title="Schedule fit" testid="decision-schedule" right={<span className="text-[12px] text-[#6B6F76]">{offer.restHours} h rest + {offer.bufferHours} h buffer</span>}>
        <StopLine stops={[
          { place: "Truck released", window: "Mon 12:00 · Vernon, LA" },
          { place: "Ava available", window: "Tue 07:00" },
          { place: "Pickup Carson", window: offer.pickup.window },
          { place: "Deliver Oakland", window: offer.delivery.window },
          { place: "In SF yard", window: `${offer.arriveSf} · then ${offer.restHours} h rest + ${offer.bufferHours} h buffer` },
          { place: "L-103 pickup SF (protected)", window: "Wed 08:00–09:00" },
        ]} />
      </Disclosure>
      <Disclosure title="Alternatives" testid="decision-alternatives" right={<Pill tone="grey">2</Pill>}>
        <ul className="space-y-2">
          <li className="rounded-2xl bg-[#181A1A]/[0.03] p-3" data-testid="alternative-O-2">
            <div className="flex items-center gap-2 text-[13px] font-medium">LA → Phoenix · {money(alt.rate)} <Pill tone="red" className="ml-auto">Unsuitable</Pill></div>
            <div className="mt-1 text-[12px] text-[#4B4F55]">{alt.broker} · {alt.reason}</div>
            <button type="button" data-testid="alternative-preview-schedule" onClick={() => useStore.getState().mutate((s) => { s.ui.inspectAlt = true; s.ui.mapMode = "schedule"; })} className="mt-2 text-[12px] font-medium text-[#7A35DB] hover:underline">Preview conflict on schedule →</button>
          </li>
          <li className="rounded-2xl bg-[#181A1A]/[0.03] p-3" data-testid="alternative-empty-return">
            <div className="flex items-center gap-2 text-[13px] font-medium">Empty return LA → SF <span className="ml-auto text-[#C2282D] tnum">{money(e.altContribution)}</span></div>
            <div className="mt-1 text-[12px] text-[#4B4F55] tnum">{e.altMiles} mi · $0 revenue · {money(e.altCost)} cost</div>
          </li>
        </ul>
      </Disclosure>
      <Section title="Load terms" testid="decision-terms">
        <div className="grid grid-cols-2 gap-x-4 gap-y-2 rounded-[18px] bg-white/75 p-4 text-[12.5px] ring-1 ring-[#181A1A]/[0.05]">
          {[
            ["Broker", offer.broker], ["Equipment", offer.equipment],
            ["Pickup", `${offer.pickup.window} · LA`], ["Delivery", `${offer.delivery.window} · Oakland`],
            ["Commodity", offer.commodity], ["Weight", `${num(offer.weight)} lb`],
          ].map(([k, v]) => (
            <div key={k}><div className="text-[11px] text-[#6B6F76]">{k}</div><div className="font-medium tnum">{v}</div></div>
          ))}
        </div>
        <button type="button" data-testid="written-terms-match-link" onClick={() => openLink({ type: "document", id: doc.id })} className="mt-2 flex w-full items-center gap-2 rounded-[14px] bg-[#A1E688]/35 px-3.5 py-2.5 text-left text-[13px] font-medium transition-colors hover:bg-[#A1E688]/50">
          <CheckCircle2 className="h-4 w-4 text-[#2C6A18]" /> Written terms match offer
          <span className="ml-auto flex items-center gap-1 text-[12px] text-[#2C6A18]">Rate confirmation <ArrowUpRight className="h-3 w-3" /></span>
        </button>
      </Section>
      <Section title="Evidence" testid="decision-evidence">
        <div className="flex flex-wrap gap-2">
          <EvidenceLink icon={MessageSquare} label="Broker offered $1,100" link={{ type: "thread", id: "CONV-O1" }} testid="evidence-broker-thread" />
          <EvidenceLink icon={FileText} label="Rate confirmation" link={{ type: "document", id: doc.id }} testid="evidence-rate-confirmation" />
          {call && <EvidenceLink icon={PhoneCall} label={call.outcome || "Broker call"} link={{ type: "call", id: call.id }} testid="evidence-call" />}
          <button type="button" data-testid="decision-feedback-button" onClick={() => feedbackService.open("", { proposalId: p.id, truckId: p.truckId, source: "Decision O-1" })} className="rounded-xl px-2.5 py-1.5 text-[12px] font-medium text-[#7A35DB] hover:underline">Give feedback</button>
        </div>
      </Section>
    </PanelShell>
  );
}
