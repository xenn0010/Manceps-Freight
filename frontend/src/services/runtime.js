import { produce } from "immer";
import { useStore } from "../store/useStore";
import * as engine from "./engine";
import { emit } from "./notify";

// Applies an engine transition to the store; only writes when the state actually changed.
export function run(fn) {
  const events = [];
  const state = useStore.getState();
  const next = produce({ data: state.data, clockMin: state.clockMin, chat: state.chat }, (d) => {
    fn(d, Date.now(), events);
  });
  if (next.data !== state.data || next.clockMin !== state.clockMin || next.chat !== state.chat) {
    useStore.setState(next);
  }
  emit(events);
  return events;
}

let timer = null;
export function startSimulation() {
  if (timer) return;
  timer = setInterval(() => run((d, now, events) => engine.tick(d, now, events)), 250);
}
