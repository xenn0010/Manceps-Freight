import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import { immer } from "zustand/middleware/immer";
import { createSeed, START_CLOCK, SCHEMA_VERSION } from "../data/seed";

const defaultUi = () => ({
  view: "dashboard",
  mapMode: "map",
  selectedTruckId: null,
  panel: null,
  panelStack: [],
  fitNonce: 0,
  demoStep: 0,
});

export const initialState = () => ({
  data: createSeed(),
  clockMin: START_CLOCK,
  chat: { messages: [] },
  ui: defaultUi(),
});

const samePanel = (a, b) => a && b && a.type === b.type && a.id === b.id;

export const useStore = create(
  persist(
    immer((set) => ({
      ...initialState(),
      transient: { resetOpen: false, demoOpen: false, voice: { status: "idle", transcript: "" }, feedback: { open: false, text: "", ctx: {}, mode: null }, drawer: null, intake: { open: false, kind: "truck" }, settingsOpen: false, callConfirm: null },

      mutate: (fn) => set((s) => void fn(s)),
      reset: () =>
        set((s) => {
          Object.assign(s, initialState());
          s.ui.fitNonce = Date.now();
          s.transient.voice = { status: "idle", transcript: "" };
          s.transient.drawer = null;
        }),

      setView: (view) => set((s) => void (s.ui.view = view)),
      setMapMode: (mode) => set((s) => void (s.ui.mapMode = mode)),
      requestFit: () => set((s) => void (s.ui.fitNonce += 1)),

      focus: (truckId, panel, { resetStack = false } = {}) =>
        set((s) => {
          s.ui.view = "dashboard";
          if (truckId !== undefined) s.ui.selectedTruckId = truckId;
          if (resetStack) s.ui.panelStack = [];
          else if (s.ui.panel && !samePanel(s.ui.panel, panel)) s.ui.panelStack = [...s.ui.panelStack, s.ui.panel].slice(-6);
          s.ui.panel = panel;
        }),
      selectTruck: (id) =>
        set((s) => {
          s.ui.view = "dashboard";
          s.ui.selectedTruckId = id;
          s.ui.panel = { type: "truck", id };
          s.ui.panelStack = [];
        }),
      openPanel: (type, id = null) =>
        set((s) => {
          const panel = { type, id };
          if (samePanel(s.ui.panel, panel)) return;
          if (s.ui.panel) s.ui.panelStack = [...s.ui.panelStack, s.ui.panel].slice(-6);
          s.ui.panel = panel;
          s.ui.view = "dashboard";
        }),
      togglePanel: (type, id = null) =>
        set((s) => {
          if (samePanel(s.ui.panel, { type, id })) {
            s.ui.panel = s.ui.panelStack.pop() || null;
            return;
          }
          if (s.ui.panel) s.ui.panelStack = [...s.ui.panelStack, s.ui.panel].slice(-6);
          s.ui.panel = { type, id };
        }),
      back: () => set((s) => void (s.ui.panel = s.ui.panelStack.pop() || null)),
      closePanel: () =>
        set((s) => {
          s.ui.panel = null;
          s.ui.panelStack = [];
          s.ui.selectedTruckId = null;
        }),

      setTransient: (patch) => set((s) => void Object.assign(s.transient, patch)),
      setVoice: (voice) => set((s) => void (s.transient.voice = voice)),
    })),
    {
      name: "freightos-demo",
      version: SCHEMA_VERSION,
      storage: createJSONStorage(() => localStorage),
      partialize: (s) => ({ data: s.data, clockMin: s.clockMin, chat: s.chat, ui: s.ui }),
      migrate: () => initialState(),
    }
  )
);
