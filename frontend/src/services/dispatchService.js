import { run } from "./runtime";
import * as engine from "./engine";
import { useStore } from "../store/useStore";
import { voiceService } from "./voiceService";
import { toast } from "sonner";

// Dispatch actions (proposals, bookings, demo lifecycle). Replace bodies with API calls later.
export const dispatchService = {
  approve: (proposalId) => run((d, now, ev) => engine.approve(d, proposalId, now, ev)),
  reject: (proposalId, reason) => run((d, now, ev) => engine.reject(d, proposalId, reason, now, ev)),
  requestChanges: (proposalId, note, target) => run((d, now, ev) => engine.requestChanges(d, proposalId, note, now, ev, target)),
  takeOver: (proposalId) => run((d, now, ev) => engine.takeOverProposal(d, proposalId, ev)),
  handBack: (proposalId) => run((d, now, ev) => engine.handBack(d, proposalId, ev)),
  markNotificationRead: (id) =>
    useStore.getState().mutate((s) => {
      const n = s.data.notifications.find((x) => x.id === id);
      if (n) n.read = true;
    }),
  markAllRead: () => useStore.getState().mutate((s) => s.data.notifications.forEach((n) => (n.read = true))),
  resetDemo: () => {
    voiceService.cancel(true);
    toast.dismiss();
    useStore.getState().reset();
    toast("Demo reset", { description: "Back to Mon 26 Oct · 10:00 PT" });
  },
};
