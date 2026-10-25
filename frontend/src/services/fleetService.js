import { run } from "./runtime";
import * as e3 from "./engine3";
import { useStore } from "../store/useStore";
import { parseIntake } from "../lib/intakeParser";

const setT = (patch) => useStore.getState().setTransient(patch);

// Fleet setup: record edits and guided intake. Swap `run` bodies for API calls when a backend exists.
export const fleetService = {
  save: (type, id, patch) => run((d) => e3.saveRecord(d, type, id, patch)),
  create: (kind, form) => run((d, now, ev) => e3.createFromIntake(d, kind, form, ev)),
  openDrawer: (type, id) => setT({ drawer: { type, id } }),
  closeDrawer: () => setT({ drawer: null }),
  openIntake: (kind = "truck") => setT({ intake: { open: true, kind } }),
  closeIntake: () => setT({ intake: { open: false, kind: "truck" } }),
};

export const intakeService = {
  parse: (kind, text) => parseIntake(kind, text, useStore.getState().data),
};

export const settingsService = {
  open: () => setT({ settingsOpen: true }),
  close: () => setT({ settingsOpen: false }),
  update: (key, value) => run((d) => e3.updateSetting(d, key, value)),
  toggleRule: (id) => run((d) => e3.toggleRule(d, id)),
  deleteRule: (id) => run((d) => e3.deleteRule(d, id)),
};
