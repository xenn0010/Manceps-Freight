import { useStore } from "../store/useStore";
import { toast } from "sonner";

export function openLink(link) {
  if (!link) return;
  const s = useStore.getState();
  const d = s.data;
  switch (link.type) {
    case "decision": {
      const p = d.proposals[link.id];
      s.focus(p.truckId, { type: "decision", id: link.id });
      break;
    }
    case "truck":
      s.focus(link.id, { type: "truck", id: link.id });
      break;
    case "call": {
      const c = d.calls[link.id];
      if (!c) return toast("No call yet", { description: "A call starts after you approve the terms" });
      s.focus(c.truckId || d.proposals[c.proposalId].truckId, { type: "call", id: link.id });
      break;
    }
    default:
      s.openPanel(link.type, link.id ?? null);
  }
}
