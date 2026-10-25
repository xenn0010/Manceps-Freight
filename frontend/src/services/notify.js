import { toast } from "sonner";
import { openLink } from "../lib/links";

// UI notification sink for service events (toasts). Swap or silence here.
export function emit(events) {
  events.forEach((e) => {
    const opts = {
      description: e.body,
      action: e.link ? { label: "View", onClick: () => openLink(e.link) } : undefined,
    };
    if (e.kind === "success") toast.success(e.title, opts);
    else toast(e.title, opts);
  });
}
