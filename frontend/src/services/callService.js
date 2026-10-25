import { run } from "./runtime";
import * as engine from "./engine";
import { callScript } from "../data/scripts";

// Simulated broker/driver calls. A real telephony backend would stream transcript lines instead.
export const callService = {
  pause: (callId) => run((d, now) => engine.pauseCall(d, callId, true, now)),
  resume: (callId) => run((d, now) => engine.pauseCall(d, callId, false, now)),
  takeOver: (callId) => run((d, now, ev) => engine.takeOverCall(d, callId, ev)),
  logBrokerConfirmation: (callId) => run((d, now, ev) => engine.logBrokerConfirmation(d, callId, now, ev)),
  transcript: (call) => callScript(call).lines.slice(0, call.lineIndex),
  facts: (call) => callScript(call).facts.filter((f) => call.lineIndex >= f.atLine),
  totalLines: (call) => callScript(call).lines.length,
};
