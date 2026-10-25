import { AlertTriangle, Lock, Clock3, Sparkles, ArrowRight, MessageSquare, Phone, CheckCircle2 } from "lucide-react";
import { useStore } from "../../store/useStore";
import { truckCommitments } from "../../lib/selectors";
import { money, stamp } from "../../lib/format";
import { openLink } from "../../lib/links";
import { exceptionService, feedbackService, liveCallService } from "../../services";
import { Field, Pill, TruckImage } from "../common/ui";
import { StopLine, TripProgress } from "../common/charts";
import { PanelShell, Section } from "./PanelShell";
import { TRUCK_PILL_TONE } from "../dashboard/TruckStrip";
import { truckCpm } from "../../lib/metrics";

function DelayHistory({ trip }) {
  return (
    <Section title="Delay history" testid="delay-history">
      <ol className="space-y-1.5">
        {trip.delayHistory.map((h, i) => (
          <li key={i} className="flex gap-2.5 rounded-2xl bg-white/80 px-3 py-2 text-[12.5px]" data-testid={`delay-history-${i}`}>
            <span className="w-10 shrink-0 text-[#6B6F76] tnum">{stamp(h.at)}</span>
            <span className="min-w-0 flex-1"><b className="font-medium">{h.label}</b> · {h.value}<span className="block text-[11px] text-[#9A9DA4]">{h.source}</span></span>
          </li>
        ))}
      </ol>
    </Section>
  );
}

function ExceptionBlock({ trip, data }) {
  const callId = trip.reapptCallId;
  const call = callId && data.calls[callId];
  const att = data.attention["ATT-102"];
  if (!trip.revision && att?.status === "delivered_late") {
    return (
      <div className="rounded-[18px] bg-[#181A1A]/[0.04] p-3.5 ring-1 ring-[#181A1A]/[0.06]" data-testid="exception-closed-late">
        <div className="flex items-center gap-2 text-[13.5px] font-semibold"><CheckCircle2 className="h-4 w-4 text-[#6B6F76]" /> Alert closed</div>
        <div className="mt-1 text-[12.5px] tnum">{att.resolution}</div>
      </div>
    );
  }
  if (trip.revision) {
    const ds = trip.revision.driverStatus;
    const live = data.calling?.mode === "live";
    return (
      <div className="rounded-[18px] bg-[#A1E688]/30 p-3.5 ring-1 ring-[#A1E688]" data-testid="exception-resolved">
        <div className="flex items-center gap-2 text-[13.5px] font-semibold"><CheckCircle2 className="h-4 w-4 text-[#2C6A18]" /> On track · rescheduled</div>
        <div className="mt-1 text-[12.5px] tnum">New window Mon {trip.revision.window} · ETA 15:30 · {trip.revision.source}</div>
        <div className="mt-2 flex flex-wrap gap-1.5">
          <Pill tone={ds === "acknowledged" ? "green" : ds === "sent" ? "purple" : "grey"} data-testid="ben-text-status">{ds === "acknowledged" ? "Ben Ortiz acknowledged" : ds === "sent" ? "Text sent to Ben Ortiz" : "Preparing driver text"}</Pill>
          <button type="button" onClick={() => openLink({ type: "thread", id: "CONV-DRV-102" })} className="text-[12px] font-medium text-[#7A35DB] hover:underline">Texts</button>
          {live && ds === "none" && <button type="button" data-testid="call-ben-button" onClick={() => liveCallService.request("D-102", "driver_window", { type: "trip", id: "L-201" })} className="rounded-lg bg-[#181A1A] px-2 py-0.5 text-[12px] font-medium text-white">Call Ben with new window</button>}
          {call && <button type="button" onClick={() => openLink({ type: "call", id: call.id })} className="text-[12px] font-medium text-[#7A35DB] hover:underline">Broker call</button>}
        </div>
      </div>
    );
  }
  return (
    <div className="space-y-2">
      <RiskBlock risk={trip.risk} />
      <p className="text-[12px] text-[#6B6F76]">Impact: delivery lands 30 min after the window closes; the receiver may refuse or charge. AI already emailed the broker at 09:35.</p>
      {call ? (
        <button type="button" data-testid="open-reappointment-call" onClick={() => openLink({ type: "call", id: call.id })} className="w-full rounded-[14px] bg-[#181A1A] py-2.5 text-[13px] font-semibold text-white">View broker call</button>
      ) : (
        <button type="button" data-testid="call-broker-appointment-button" onClick={() => { if (useStore.getState().data.calling?.mode === "live") return liveCallService.request("BRK-CENTRAL", "broker_reappointment", { type: "trip", id: "L-201" }); exceptionService.callBrokerForAppointment(); const id = useStore.getState().data.trips["L-201"].reapptCallId; if (id) openLink({ type: "call", id }); }} className="w-full rounded-[14px] bg-[#AF6EFF] py-2.5 text-[13px] font-semibold text-white hover:bg-[#9F5BF5]">Call broker for new appointment</button>
      )}
    </div>
  );
}

function ExecLog({ trip }) {
  if (!trip.execLog?.length) return null;
  return (
    <div className="mt-2 space-y-1" data-testid={`exec-log-${trip.id}`}>
      {trip.execLog.map((l, i) => (
        <div key={i} className="flex items-center gap-2 text-[12px]"><span className="w-12 text-[#6B6F76] tnum">{stamp(l.at)}</span><Pill tone={l.label === "Document received" ? "green" : "grey"}>{l.label}</Pill><span className="text-[#9A9DA4]">{l.source}</span></div>
      ))}
      {trip.podId && <button type="button" data-testid={`pod-link-${trip.id}`} onClick={() => openLink({ type: "document", id: trip.podId })} className="text-[12px] font-medium text-[#7A35DB] hover:underline">View POD →</button>}
    </div>
  );
}

function RiskBlock({ risk }) {
  return (
    <div className="rounded-[18px] bg-[#FFC46D]/30 p-3.5 ring-1 ring-[#FFC46D]/70" data-testid="truck-risk-block">
      <div className="flex items-center gap-2">
        <AlertTriangle className="h-4 w-4 text-[#8A5200]" />
        <span className="text-[13.5px] font-semibold">Delivery at risk</span>
        <Pill tone="red" className="ml-auto" data-testid="risk-missed-window">Misses window</Pill>
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2">
        <Field label="Release" value={`Mon ${risk.release}`} tone="amber" testid="risk-release" />
        <Field label="ETA" value={`Mon ${risk.eta}`} tone="red" testid="risk-eta" />
        <Field label="Window" value={risk.window} testid="risk-window" />
      </div>
      <div className="mt-2.5 flex items-center gap-2 text-[12.5px]">
        <Pill tone="amber" data-testid="risk-revised-appointment"><Clock3 className="h-3 w-3" /> {risk.note}</Pill>
        <span className="text-[#6B6F76]">Asked broker for {risk.requested}</span>
      </div>
    </div>
  );
}

function TripCard({ trip }) {
  const EXEC_PCT = { picked_up: 5, in_transit: 50, delivered: 100, document_received: 100 };
  const pct = trip.exec ? EXEC_PCT[trip.exec] ?? 100 : trip.id === "L-301" ? (trip.progressMiles / trip.loadedMiles) * 100 : trip.phase === "Unloading" ? 100 : 0;
  const left = trip.id === "L-301" ? `${trip.loadedMiles - trip.progressMiles} mi left` : `${trip.loadedMiles} mi`;
  const mid = trip.id === "L-301" ? "1 h 30 min" : trip.phase;
  const right = trip.eta ? `ETA ${trip.eta.replace("Mon ", "")}` : "Arrived";
  return (
    <div className="rounded-[18px] bg-white/80 p-4 ring-1 ring-[#181A1A]/[0.05]" data-testid={`trip-card-${trip.id}`}>
      <div className="mb-3 flex items-center justify-between">
        <span className="text-[16px] font-semibold tnum">{trip.id}</span>
        <Pill tone={trip.revision ? "green" : trip.risk ? "amber" : trip.id === "L-301" ? "green" : "grey"}>{trip.exec ? trip.exec.replace("_", " ") : trip.revision ? "On track · rescheduled" : trip.risk ? "At risk" : trip.id === "L-301" ? "In transit" : trip.phase}</Pill>
      </div>
      <TripProgress pct={pct} left={left} mid={mid} right={right} testid={`trip-progress-${trip.id}`} />
      <div className="mt-3.5">
        <StopLine stops={[trip.pickup, trip.delivery]} />
      </div>
      <div className="mt-3 flex justify-between text-[12px] text-[#6B6F76] tnum">
        <span>{trip.broker}</span>
        <span>{money(trip.revenue)} · {trip.loadedMiles} loaded · {trip.emptyMiles} empty</span>
      </div>
    </div>
  );
}

function Commitment({ item, data }) {
  if (item.kind === "segment") {
    const s = item.segment;
    return (
      <li className="flex items-center gap-3 rounded-2xl border border-dashed border-[#181A1A]/15 px-3.5 py-2.5" data-testid={`commitment-${s.id}`}>
        <div className="min-w-0 flex-1">
          <div className="text-[13px] font-medium">Empty return · {s.origin} → {s.destination}</div>
          <div className="text-[11.5px] text-[#6B6F76] tnum">{s.miles} mi · {money(-s.miles * truckCpm(data, s.truckId))} · {s.reason}</div>
        </div>
        <Pill tone="grey">Planned</Pill>
      </li>
    );
  }
  if (item.kind === "offer") {
    const o = item.offer;
    return (
      <li>
        <button type="button" onClick={() => openLink({ type: "decision", id: "P-1" })} className="flex w-full items-center gap-3 rounded-2xl bg-[#AF6EFF]/10 px-3.5 py-2.5 text-left ring-1 ring-[#AF6EFF]/30 transition-colors hover:bg-[#AF6EFF]/15" data-testid={`commitment-${o.id}`}>
          <div className="min-w-0 flex-1">
            <div className="text-[13px] font-medium">{o.id} · {o.origin} → {o.destination} · {money(o.rate)}</div>
            <div className="text-[11.5px] text-[#6B6F76] tnum">PU {o.pickup.window} · DEL {o.delivery.window}</div>
          </div>
          <Pill tone="purple">{o.status === "awaiting_broker" ? "Awaiting broker" : "Proposed"}</Pill>
        </button>
      </li>
    );
  }
  const t = item.trip;
  return (
    <li className="rounded-2xl bg-white/80 px-3.5 py-2.5 ring-1 ring-[#181A1A]/[0.05]" data-testid={`commitment-${t.id}`}>
      <div className="flex items-center gap-2">
        <span className="text-[13px] font-semibold tnum">{t.id}</span>
        <span className="text-[13px]">{t.origin} → {t.destination}</span>
        {t.protected ? (
          <Pill tone="ink" className="ml-auto" data-testid={`protected-commitment-${t.id}`}><Lock className="h-3 w-3" /> Protected commitment</Pill>
        ) : (
          <Pill tone="green" className="ml-auto">Booked</Pill>
        )}
      </div>
      <div className="mt-1 text-[11.5px] text-[#6B6F76] tnum">PU {t.pickup.window} {t.pickup.place} · DEL {t.delivery.window} {t.delivery.place}</div>
    </li>
  );
}

export default function TruckPanel({ id }) {
  const data = useStore((s) => s.data);
  const t = data.trucks[id];
  const driver = data.drivers[t.driverId];
  const trip = t.currentTripId && data.trips[t.currentTripId];
  const commitments = truckCommitments(data, id);
  const proposal = Object.values(data.proposals).find((p) => p.truckId === id && ["proposal_ready", "changes_requested", "terms_approved", "awaiting_broker"].includes(p.status));
  return (
    <PanelShell testid="truck-panel" eyebrow={`Truck ${t.unit}`} title={`Truck ${t.unit} · ${driver.name}`}>
      <div className="relative flex items-end justify-between overflow-hidden rounded-[18px] bg-gradient-to-b from-white/40 to-white/90 px-4 pb-2 pt-3">
        <div>
          <Pill tone={TRUCK_PILL_TONE[t.health]} data-testid="truck-panel-status-pill">{t.pill}</Pill>
          <div className="mt-1.5 text-[12.5px] text-[#6B6F76]">{t.location}</div>
        </div>
        <TruckImage purple className="h-[64px] w-[62%]" />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <Field label="Equipment" value={t.equipment} testid="truck-equipment" />
        <Field label="Current status" value={t.status} testid="truck-current-status" />
        <Field label="Truck availability" value={t.id === "T-101" ? `Released ${t.truckAvailableAt}` : t.truckAvailableAt} testid="truck-availability" />
        <Field label="Driver availability" value={driver.availableAt === "On duty" ? "On duty now" : `Available ${driver.availableAt}`} testid="driver-availability" />
      </div>
      {trip?.risk && <ExceptionBlock trip={trip} data={data} />}
      {trip && (
        <Section title="Current trip" testid="truck-current-trip">
          <TripCard trip={trip} />
          <ExecLog trip={trip} />
          {trip.id === "L-301" && !trip.exec && <p className="mt-2 text-[12px] text-[#2C6A18]" data-testid="truck-on-track-note">On track · ETA 11:30 inside window 11:00–13:00</p>}
        </Section>
      )}
      {trip?.delayHistory && <DelayHistory trip={trip} />}
      {commitments.filter((c) => c.kind === "trip" && c.trip.execLog).map((c) => <ExecLog key={c.trip.id} trip={c.trip} />)}
      {t.id === "T-104" && (
        <div className="rounded-[18px] bg-white/80 p-4" data-testid="truck-104-searching">
          <div className="flex items-center gap-2 text-[13px] font-medium"><Sparkles className="h-4 w-4 text-[#AF6EFF]" /> {data.search104.progress}</div>
          <div className="mt-3 space-y-2"><div className="shimmer h-3 w-4/5" /><div className="shimmer h-3 w-3/5" /></div>
          <p className="mt-2.5 text-[12px] text-[#6B6F76]">Candidate: {data.search104.candidate.lane} · {data.search104.candidate.window} · {money(data.search104.candidate.rate)} (info only)</p>
        </div>
      )}
      <Section title="Upcoming commitments" testid="truck-commitments">
        {commitments.length ? (
          <ul className="space-y-2">{commitments.map((c, i) => <Commitment key={i} item={c} data={data} />)}</ul>
        ) : (
          <p className="text-[12.5px] text-[#6B6F76]">No upcoming commitments.</p>
        )}
      </Section>
      <div className="flex gap-2">
        {proposal && (
          <button type="button" data-testid="open-decision-button" onClick={() => openLink({ type: "decision", id: proposal.id })} className="flex flex-1 items-center justify-center gap-1.5 rounded-[14px] bg-[#AF6EFF] py-2.5 text-[13.5px] font-semibold text-white hover:bg-[#9F5BF5]">
            Open return-load decision <ArrowRight className="h-4 w-4" />
          </button>
        )}
        {data.conversations[`CONV-DRV-${t.unit}`] && (
          <button type="button" data-testid="open-driver-thread" onClick={() => openLink({ type: "thread", id: `CONV-DRV-${t.unit}` })} className="flex items-center gap-1.5 rounded-[14px] bg-white/85 px-3 py-2.5 text-[13px] font-medium hover:bg-white">
            <MessageSquare className="h-4 w-4" /> Texts
          </button>
        )}
        {t.driverId && (
          <button type="button" data-testid="call-driver-button" onClick={() => liveCallService.request(t.driverId, "manual", null, `Check in with ${data.drivers[t.driverId]?.name} about Truck ${t.unit}`)} className="flex items-center gap-1.5 rounded-[14px] bg-white/85 px-3 py-2.5 text-[13px] font-medium hover:bg-white">
            <Phone className="h-4 w-4" /> Call
          </button>
        )}
        <button type="button" data-testid="truck-feedback-button" onClick={() => feedbackService.open("", { truckId: id, source: `Truck ${t.unit} panel` })} className="rounded-[14px] bg-white/85 px-3 py-2.5 text-[13px] font-medium hover:bg-white">Feedback</button>
      </div>
      {data.corrections.filter((c) => c.truckId === id).map((c) => (
        <div key={c.id} className="rounded-[14px] bg-[#181A1A]/[0.04] px-3 py-2 text-[12px]" data-testid={`truck-correction-${c.id}`}>Corrected {c.label}: <span className="line-through text-[#6B6F76]">{c.old}</span> → <b>{c.value}</b> · {stamp(c.at)}</div>
      ))}
    </PanelShell>
  );
}
