import { run } from "./runtime";
import * as e2 from "./engine2";
import { reviewAndBook } from "./engine";
import { useStore } from "../store/useStore";

// Phase 2 services: exceptions, execution timeline, terms guard, feedback/rules.
export const exceptionService = {
  callBrokerForAppointment: () => run((d, now, ev) => e2.startReappointment(d, now, ev)),
};

export const executionService = {
  advanceTime: () => run((d, now, ev) => e2.advanceTime(d, ev)),
};

export const termsService = {
  simulateTermsDiffer: () => run((d, now, ev) => e2.simulateTermsDiffer(d, ev)),
  markReviewed: () => run((d, now, ev) => reviewAndBook(d, now, ev)),
};

const DRIVER_NAMES = ["Ava Reed", "Ben Ortiz", "Chloe Chen", "Daniel Brooks"];

export const feedbackService = {
  open: (text = "", ctx = {}, mode = null) => useStore.getState().setTransient({ feedback: { open: true, text, ctx, mode } }),
  close: () => useStore.getState().setTransient({ feedback: { open: false, text: "", ctx: {}, mode: null } }),
  analyze(text, ctx, data) {
    const truckId = ctx.truckId || "T-101";
    const truck = data.trucks[truckId];
    let fact = null;
    const drv = text.match(/driver (?:is )?available\s+(.+)/i);
    const trk = text.match(/truck (?:is )?(?:released|available)\s+(.+)/i);
    if (drv) fact = { entity: "drivers", id: truck.driverId, field: "availableAt", label: "Driver availability", value: drv[1].trim(), truckId };
    else if (trk) fact = { entity: "trucks", id: truckId, field: "truckAvailableAt", label: "Truck availability", value: trk[1].trim(), truckId };
    if (fact) fact.old = data[fact.entity][fact.id][fact.field];
    const first = DRIVER_NAMES.find((n) => new RegExp(`\\b${n.split(" ")[0]}\\b`, "i").test(text));
    const unit = text.match(/truck\s*(10[1-4])/i);
    const scope = first ? { scope: "driver", scopeLabel: `Driver: ${first}` } : unit ? { scope: "truck", scopeLabel: `Truck: ${unit[1]}` } : { scope: "carrier", scopeLabel: `Carrier: ${data.carrier.name}` };
    const ruleText = text.trim().replace(/^./, (c) => c.toUpperCase()).replace(/\.?$/, ".");
    return { fact, ...scope, ruleText };
  },
  correctFact: (fact) => run((d) => e2.correctFact(d, fact)),
  applyRule: (rule) => run((d, now, ev) => e2.addRule(d, rule, ev)),
  oneOff: (ctx, text) => run((d) => e2.oneOff(d, ctx, text)),
};
