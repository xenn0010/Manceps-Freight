import { EXAMPLE_COMMANDS } from "../data/scripts";
import { openAttention } from "../lib/selectors";
import { offerEconomics, truckCpm } from "../lib/metrics";
import { money, signedMoney } from "../lib/format";

export function matchIntent(text) {
  const t = text.toLowerCase();
  if (/^(never|always|don'?t|do not|avoid|prefer|only)\b|\brule\b|driver available|truck (released|available)/.test(t)) return "feedback";
  if (/needs? me|need my|attention|what.*(need|urgent)/.test(t)) return "needs_me";
  if (/(explain|plan).*101|101.*plan/.test(t)) return "explain_101";
  if (/return load|backhaul|find.*load/.test(t)) return "find_return";
  return "fallback";
}

const EVIDENCE = [
  { label: "Broker offer thread", link: { type: "thread", id: "CONV-O1" } },
  { label: "Rate confirmation", link: { type: "document", id: "DOC-RC-1" } },
];

function returnLoadAnswer(data, intent) {
  const p = data.proposals["P-1"];
  const decision = { label: "Open decision", link: { type: "decision", id: "P-1" } };
  if (p.status === "booked") {
    return {
      intent,
      text: "Truck 101's return load is booked: L-102 LA→Oakland Tue for $1,100. Ava Reed reaches SF by Tue 18:00, protecting the Wed 08:00 L-103 pickup.",
      bullets: ["+$1,046 planned contribution vs the empty return", "Broker confirmed in writing"],
      evidence: [...EVIDENCE, ...(p.callId ? [{ label: "Broker call", link: { type: "call", id: p.callId } }] : [])],
      cta: decision,
    };
  }
  if (p.status === "rejected") {
    return { intent, text: "You rejected O-1, so Truck 101 keeps the 400 mi empty return to SF (-$720).", evidence: EVIDENCE, cta: decision };
  }
  const o = data.offers["O-1"];
  const e = offerEconomics(o, data.segments["SEG-101-RET"], truckCpm(data, "T-101"));
  const lead =
    intent === "explain_101"
      ? "Truck 101 is unloading in LA (released Mon 12:00, Ava available Tue 07:00) and must be in SF for protected L-103 Wed 08:00. Instead of a 400 mi empty return, I recommend O-1:"
      : "Best return load for Truck 101:";
  return {
    intent,
    text: `${lead} Demo Pacific Broker, LA→Oakland Tue for ${money(o.rate)}. That's ${signedMoney(e.delta)} planned contribution vs the empty return, and Truck 101 is in SF by Tue 18:00.`,
    bullets: ["LA→Phoenix $1,600 ruled out: Wed delivery conflicts with L-103", "Written terms match the offer"],
    evidence: EVIDENCE,
    cta: decision,
  };
}

export function buildAnswer(data, text) {
  const intent = matchIntent(text);
  if (intent === "feedback") return { intent, text: "Got it. How should I treat this?", feedback: { text } };
  if (intent === "needs_me") {
    const items = openAttention(data).map((a) => ({
      label: `${a.title} · Truck ${data.trucks[a.truckId].unit}`, sub: a.summary, link: a.link, tone: a.severity,
    }));
    return {
      intent,
      text: items.length ? `${items.length} item${items.length > 1 ? "s" : ""} need${items.length > 1 ? "" : "s"} you:` : "Nothing needs you right now. FreightOS is handling the rest.",
      items,
    };
  }
  if (intent === "explain_101" || intent === "find_return") return returnLoadAnswer(data, intent);
  return { intent, text: "I can't help with that yet. In this demo I can answer:", suggestions: EXAMPLE_COMMANDS };
}
