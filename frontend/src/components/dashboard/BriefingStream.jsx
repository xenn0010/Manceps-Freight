import { useEffect, useMemo, useRef } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Sparkles, Volume2, VolumeX, ArrowUpRight } from "lucide-react";
import { useStore } from "../../store/useStore";
import { openLink } from "../../lib/links";
import { openAttention } from "../../lib/selectors";
import { stamp } from "../../lib/format";
import { settingsService } from "../../services";
import { cn } from "../../lib/utils";

const lc = (s = "") => s.charAt(0).toLowerCase() + s.slice(1);
const FIRST_PERSON = [
  [/^seed-n1$/, () => "Truck 102 is running late: ETA 15:30 misses Stockton's 14:00–15:00 window."],
  [/^seed-n2$/, () => "I found a return load for Truck 101: LA → Oakland at $1,100, better than driving back empty."],
  [/^seed-n3$/, () => "Truck 103 is on track for Oakland, ETA 11:30."],
  [/^seed-n4$/, () => "The O-1 rate confirmation came in and matches the offer."],
  [/^seed-n5$/, () => "Truck 104 is off duty until Tue 07:00. I'm searching loads for it."],
  [/^call-start-/, (n) => `I'm calling Demo Pacific Broker: ${lc(n.body)}.`],
  [/^booked-/, (n) => `Booked Truck 101 on LA → Oakland. ${n.body}.`],
  [/^ack-/, () => "Ava Reed acknowledged tomorrow's pickup."],
  [/^reappt-start-/, () => "I'm calling Central Valley Brokers to move Truck 102 to 15:30–16:30."],
  [/^reappt-done/, () => "The broker confirmed 15:30–16:30 for Truck 102."],
  [/^ben-ack/, () => "Ben Ortiz acknowledged the new Stockton window."],
  [/^counter-/, (n) => `${n.body}. I need your review before booking.`],
  [/^terms-differ-/, () => "The written terms differ from the offer, so I've blocked booking until you review."],
  [/^late-L-201/, (n) => `I closed the Truck 102 alert: ${lc(n.body)}.`],
  [/^ev-/, (n) => `${n.body}.`],
  [/^rule-/, (n) => `Noted. I'll follow: “${n.body}”.`],
  [/^intake-/, (n) => `Added ${n.body} to the fleet.`],
];
export const briefText = (n) => n.say || FIRST_PERSON.find(([re]) => re.test(n.key || ""))?.[1](n) || `${n.title}: ${n.body}.`;
const ACTION = { decision: "Review load", truck: "Review delay", livecall: "Open call", document: "Open document" };
const isDecision = (n) => n.group === "needs_you" && n.status === "open";

function useSpeech(items, on) {
  const seen = useRef(null);
  useEffect(() => {
    if (!seen.current) {
      seen.current = new Set(items.map((n) => n.id));
      return;
    }
    items.forEach((n) => {
      if (seen.current.has(n.id)) return;
      seen.current.add(n.id);
      if (on && window.speechSynthesis) {
        const u = new SpeechSynthesisUtterance(briefText(n));
        u.rate = 1.05;
        window.speechSynthesis.speak(u);
        document.body.dataset.lastSpoken = briefText(n);
      }
    });
  }, [items, on]);
}

export function BriefingToggle() {
  const open = useStore((s) => s.ui.briefingOpen !== false);
  const pending = useStore((s) => s.data.notifications.filter(isDecision).length);
  return (
    <button type="button" data-testid="briefing-toggle" aria-pressed={open} aria-label="AI briefing" onClick={() => useStore.getState().mutate((s) => void (s.ui.briefingOpen = !open))}
      className={cn("relative grid h-10 w-10 place-items-center rounded-full transition-colors", open ? "bg-[#181A1A] text-white" : "bg-white/80 hover:bg-white")}>
      <Sparkles className="h-[17px] w-[17px]" />
      {pending > 0 && <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-[#AF6EFF] ring-2 ring-white" data-testid="briefing-pending-dot" />}
    </button>
  );
}

export function BriefingStream() {
  const notes = useStore((s) => s.data.notifications);
  const speak = useStore((s) => !!s.data.settings.speakUpdates);
  const open = useStore((s) => s.ui.briefingOpen !== false);
  const attention = useStore((s) => s.data.attention);
  const chips = useMemo(() => openAttention({ attention }), [attention]);
  const items = useMemo(() => notes.map((n, i) => ({ n, i })).sort((a, b) => b.n.at - a.n.at || b.i - a.i).map(({ n }) => n), [notes]);
  useSpeech(notes, speak);
  if (!open) return null;
  return (
    <section className="absolute bottom-[132px] left-3 top-[60px] z-[6] flex w-[288px] flex-col" data-testid="briefing-stream" aria-label="AI briefing" aria-live="polite">
      <div className="glass flex items-center gap-2 !rounded-[16px] px-3 py-2">
        <span className="relative flex h-2 w-2"><span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[#AF6EFF] opacity-60" /><span className="relative h-2 w-2 rounded-full bg-[#AF6EFF]" /></span>
        <span className="text-[12.5px] font-semibold">Briefing</span>
        <span className="text-[11px] text-[#6B6F76]">from FreightOS</span>
        <button type="button" data-testid="briefing-speak-toggle" aria-pressed={speak} title="Speak updates" onClick={() => settingsService.update("speakUpdates", !speak)} className={cn("ml-auto grid h-7 w-7 place-items-center rounded-lg", speak ? "bg-[#AF6EFF] text-white" : "hover:bg-[#181A1A]/[0.06]")}>
          {speak ? <Volume2 className="h-3.5 w-3.5" /> : <VolumeX className="h-3.5 w-3.5" />}
        </button>
        <button type="button" data-testid="briefing-all" onClick={() => openLink({ type: "activity" })} className="text-[11.5px] font-medium text-[#7A35DB] hover:underline">All</button>
      </div>
      {chips.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1.5" data-testid="attention-chips">
          {chips.map((a) => (
            <button key={a.id} type="button" data-testid={`attention-chip-${a.id}`} onClick={() => openLink(a.link || { type: "truck", id: a.truckId })}
              className="glass flex items-center gap-1.5 !rounded-full px-2.5 py-1 text-[11.5px] font-semibold hover:bg-white">
              <span className={cn("h-1.5 w-1.5 rounded-full", a.priority <= 1 ? "bg-[#E5484D]" : "bg-[#AF6EFF]")} />
              {a.title} · Truck {a.truckId.replace("T-", "")}
            </button>
          ))}
        </div>
      )}
      <ul className="mt-1.5 min-h-0 flex-1 space-y-1.5 overflow-hidden [mask-image:linear-gradient(to_bottom,black_80%,transparent)]">
        <AnimatePresence initial={false}>
          {items.slice(0, 3).map((n) => (
            <motion.li key={n.id} layout initial={{ opacity: 0, y: -8, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.28 }}>
              <div role="button" tabIndex={0} data-testid={`briefing-item-${n.id}`} onClick={() => n.link && openLink(n.link)} onKeyDown={(e) => e.key === "Enter" && n.link && openLink(n.link)}
                className={cn("glass group cursor-pointer !rounded-[16px] px-3 py-2.5 transition-colors hover:bg-white", isDecision(n) && "ring-1 ring-[#AF6EFF]/40")}>
                <div className="flex items-start gap-2">
                  <p className="min-w-0 flex-1 text-[12.5px] leading-snug text-[#2B2E30]" data-testid="briefing-text">{briefText(n)}</p>
                  <span className="shrink-0 text-[10.5px] text-[#9A9DA4] tnum">{stamp(n.at)}</span>
                </div>
                {isDecision(n) && n.link && (
                  <button type="button" data-testid={`briefing-action-${n.id}`} onClick={(e) => (e.stopPropagation(), openLink(n.link))} className="mt-2 flex items-center gap-1 rounded-[10px] bg-[#181A1A] px-2.5 py-1 text-[11.5px] font-semibold text-white hover:bg-[#2a2d2d]">
                    {ACTION[n.link.type] || "Open"} <ArrowUpRight className="h-3 w-3" />
                  </button>
                )}
              </div>
            </motion.li>
          ))}
        </AnimatePresence>
      </ul>
    </section>
  );
}
