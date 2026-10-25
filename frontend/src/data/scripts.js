export const CALL_CONTACT = { name: "Maya Lin", company: "Demo Pacific Broker", phone: "(555) 014-2290" };
export const CALL_OBJECTIVE = "Confirm O-1 at $1,100 and get the signed rate confirmation";

export const CALL_SCRIPT = [
  { speaker: "ai", text: "Hi Maya, FreightOS calling for Demo West Freight about your Tuesday LA to Oakland load." },
  { speaker: "broker", text: "Hi! Yes, the packaged goods, 30,000 pounds. Still open." },
  { speaker: "ai", text: "We'll take it at $1,100 all-in, pickup Tuesday 08:00 to 09:00 in Carson." },
  { speaker: "broker", text: "Works for me. Delivery is Oakland, 16:00 to 17:00 the same day." },
  { speaker: "ai", text: "Confirmed. Truck 101, 53-foot dry van, driver Ava Reed." },
  { speaker: "broker", text: "Perfect. Sending the signed rate confirmation now." },
  { speaker: "system", text: "Signed rate confirmation received · terms match offer" },
];

export const CALL_FACTS = [
  { key: "rate", label: "Rate", value: "$1,100 all-in", atLine: 3 },
  { key: "pu", label: "Pickup", value: "Tue 08:00–09:00 · Carson", atLine: 3 },
  { key: "del", label: "Delivery", value: "Tue 16:00–17:00 · Oakland", atLine: 4 },
  { key: "equip", label: "Equipment", value: "53' dry van · Ava Reed", atLine: 5 },
  { key: "written", label: "Written terms", value: "Signed rate confirmation", atLine: 7 },
];

export const DRIVER_INSTRUCTIONS =
  "New load L-102 for Tue: PU 08:00–09:00 Carson (LA), DEL 16:00–17:00 Oakland, then empty to SF yard by 18:00. 30,000 lb packaged goods. Reply OK to confirm.";
export const DRIVER_ACK = "OK, got it. Rolling at 07:00 Tue, I'll be in Carson by 08:00.";

export const EXAMPLE_COMMANDS = ["What needs me?", "Explain Truck 101's plan", "Find a return load"];

const usd = (n) => `$${n.toLocaleString("en-US")}`;
const o1Script = (rate) => ({
  lines: CALL_SCRIPT.map((l, i) => (i === 2 ? { ...l, text: `We'll take it at ${usd(rate)} all-in, pickup Tuesday 08:00 to 09:00 in Carson.` } : l)),
  facts: CALL_FACTS.map((f) => (f.key === "rate" ? { ...f, value: `${usd(rate)} all-in` } : f)),
});
export const REAPPT_CONTACT = { name: "Luis Romero", company: "Central Valley Brokers", phone: "(555) 017-3384" };
export const REAPPT_OBJECTIVE = "Move the L-201 Stockton delivery to 15:30–16:30";
const REAPPT = {
  lines: [
    { speaker: "ai", text: "Hi Luis, FreightOS for Demo West Freight about L-201 into Stockton today." },
    { speaker: "broker", text: "Right, the 14:00 to 15:00 appointment. You're running late?" },
    { speaker: "ai", text: "Loading slipped to 12:30 at the shipper, so our ETA is 15:30. Can we move to 15:30 to 16:30?" },
    { speaker: "broker", text: "Let me check with the receiver… yes, 15:30 to 16:30 works." },
    { speaker: "ai", text: "Great. Please send the updated appointment in writing." },
    { speaker: "system", text: "New window 15:30–16:30 confirmed" },
  ],
  facts: [
    { key: "delay", label: "Delay reason", value: "Loading released 12:30", atLine: 3 },
    { key: "eta", label: "ETA", value: "Mon 15:30", atLine: 3 },
    { key: "window", label: "New window", value: "Mon 15:30–16:30", atLine: 4 },
    { key: "written", label: "Written", value: "Appointment updated", atLine: 6 },
  ],
};
export const callScript = (c) => (c.script === "reappt" ? REAPPT : o1Script(c.rate || 1100));
export const BEN_TEXT = "Stockton appointment moved to 15:30–16:30 today. Same consignee. Reply OK to confirm.";
export const BEN_ACK = "OK, 15:30–16:30 Stockton. Thanks.";
export const VOICE_PRESET = "Find a return load for Truck 101";
