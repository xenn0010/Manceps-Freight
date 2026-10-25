import { money } from "../lib/format";

// Call-script seam: builds the task spec the backend wraps into a transient Vapi assistant.
// The teammate's AI engine can replace build() without touching the call plumbing.
const bool = { type: "boolean" };
const str = { type: ["string", "null"] };
const schema = (props) => ({ type: "object", properties: props, required: Object.keys(props) });

const TASKS = {
  driver_instructions: (data, c) => ({
    objective: "Give Ava Reed tomorrow's pickup instructions for load L-102 and get her acknowledgment",
    facts: ["Load L-102: Los Angeles → Oakland, Tuesday, 53' dry van, Truck 101", "Pickup Tue 08:00–09:00 at the Los Angeles shipper", "Delivery Tue 16:00–17:00 in Oakland", "Truck 101 is back in San Francisco around Tue 18:00"],
    allowedOutcomes: ["acknowledged", "has a concern to pass to dispatch"],
    firstMessage: `Hi ${c.name.split(" ")[0]}, this is FreightOS, the AI dispatcher for Demo West Freight. Do you have a minute for tomorrow's load?`,
    schema: schema({ acknowledged: bool, concerns: str, notes: str }),
  }),
  driver_window: (data, c) => ({
    objective: "Tell Ben Ortiz the L-201 Stockton delivery moved to 15:30–16:30 today and get his acknowledgment",
    facts: ["L-201 Fresno → Stockton, Truck 102", "Broker confirmed the new Stockton window: Mon 15:30–16:30", "Release from the Fresno shipper around 12:30, ETA 15:30"],
    allowedOutcomes: ["acknowledged", "has a concern"],
    firstMessage: `Hi ${c.name.split(" ")[0]}, FreightOS here from Demo West Freight dispatch with an update on your Stockton delivery.`,
    schema: schema({ acknowledged: bool, notes: str }),
  }),
  broker_reappointment: () => ({
    objective: "Move the L-201 Stockton delivery appointment to 15:30–16:30 today",
    facts: ["Load L-201 Fresno → Stockton, carrier Demo West Freight, Truck 102", "Original delivery window Mon 14:00–15:00", "Shipper loading was delayed (short on labour), release 12:30", "New ETA 15:30; requesting 15:30–16:30"],
    allowedOutcomes: ["confirmed 15:30–16:30", "offered a different window", "declined"],
    firstMessage: "Hi, this is FreightOS calling for Demo West Freight about load L-201 into Stockton today. Do you have a moment?",
    schema: schema({ confirmed: bool, new_window: str, notes: str }),
  }),
  broker_confirmation: (data) => {
    const o = data.offers["O-1"];
    return {
      objective: `Confirm load O-1 Los Angeles → Oakland at ${money(o.rate)} all-in and ask for the signed rate confirmation`,
      facts: [`Rate ${money(o.rate)} all-in`, "Pickup Tue 08:00–09:00 Los Angeles", "Delivery Tue 16:00–17:00 Oakland", "53' dry van, Truck 101, driver Ava Reed"],
      allowedOutcomes: ["confirmed", "changed terms", "declined"],
      firstMessage: "Hi, this is FreightOS for Demo West Freight. I'm calling to confirm the Los Angeles to Oakland load for Tuesday.",
      schema: schema({ confirmed: bool, rate: { type: ["number", "null"] }, notes: str }),
    };
  },
  manual: (data, c, purpose) => ({
    objective: purpose || `Quick check-in with ${c.name} from dispatch`,
    facts: [`Calling on behalf of ${data.carrier.name} dispatch`],
    allowedOutcomes: ["acknowledged", "needs a callback"],
    firstMessage: `Hi ${c.name.split(" ")[0]}, this is FreightOS from Demo West Freight dispatch.`,
    schema: schema({ acknowledged: bool, notes: str }),
  }),
};

const REPLY = {
  driver_instructions: ["Sure, go ahead.", "Got it, 08:00 pickup in LA, Oakland by 16:00. Confirmed."],
  driver_window: ["Yeah?", "OK, 15:30 to 16:30 in Stockton. Thanks."],
  broker_reappointment: ["Sure, what's up with L-201?", "Let me check… yes, 15:30 to 16:30 works. I'll update the receiver."],
  broker_confirmation: ["Yes, go ahead.", "Confirmed at that rate. Sending the signed rate con now."],
  manual: ["Hi, sure.", "Sounds good, thanks."],
};
const RESULT = {
  driver_instructions: { acknowledged: true, concerns: null, notes: "Confirmed pickup and delivery times" },
  driver_window: { acknowledged: true, notes: "Confirmed 15:30–16:30" },
  broker_reappointment: { confirmed: true, new_window: "15:30–16:30", notes: "Receiver updated" },
  broker_confirmation: { confirmed: true, rate: null, notes: "Signed rate confirmation on its way" },
  manual: { acknowledged: true, notes: "Check-in complete" },
};

export const callScripts = {
  build: (type, data, contact, purpose) => ({ type, ...(TASKS[type] || TASKS.manual)(data, contact, purpose) }),
  simulatedLines: (task) => [
    { role: "ai", text: task.firstMessage },
    { role: "contact", text: REPLY[task.type]?.[0] || "Sure." },
    { role: "ai", text: `${task.objective}. ${task.facts.slice(0, 2).join(". ")}.` },
    { role: "contact", text: REPLY[task.type]?.[1] || "OK." },
    { role: "ai", text: "Thanks, that's all I needed. Have a good one." },
  ],
  simulatedResult: (task) => ({ summary: `Simulated: ${task.objective.toLowerCase()} — done.`, structuredData: RESULT[task.type] || RESULT.manual }),
};
