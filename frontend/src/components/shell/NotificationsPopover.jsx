import { Bell, CheckCircle2, ChevronRight } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "../ui/popover";
import { useStore } from "../../store/useStore";
import { openLink } from "../../lib/links";
import { stamp } from "../../lib/format";
import { dispatchService } from "../../services";
import { cn } from "../../lib/utils";
import { useState } from "react";

function Item({ n, onOpen }) {
  const resolved = n.status === "resolved";
  return (
    <button
      type="button"
      data-testid={`notification-item-${n.id}`}
      onClick={() => onOpen(n)}
      className={cn("group flex w-full items-start gap-2.5 rounded-xl px-2.5 py-2 text-left transition-colors hover:bg-[#181A1A]/[0.04]", resolved && "opacity-60")}
    >
      <span className={cn("mt-1.5 h-2 w-2 shrink-0 rounded-full", n.read ? "bg-transparent" : n.group === "needs_you" ? "bg-[#AF6EFF]" : "bg-[#181A1A]/40")} />
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-1.5 text-[13px] font-medium">
          {resolved && <CheckCircle2 className="h-3.5 w-3.5 text-[#4E9A33]" />}
          {n.title}
        </span>
        <span className="block truncate text-[12px] text-[#6B6F76]">{resolved ? "Resolved" : n.body}</span>
      </span>
      <span className="text-[11px] text-[#9A9DA4] tnum">{stamp(n.at)}</span>
      <ChevronRight className="mt-0.5 h-3.5 w-3.5 text-[#9A9DA4] opacity-0 transition-opacity group-hover:opacity-100" />
    </button>
  );
}

export function NotificationsPopover() {
  const list = useStore((s) => s.data.notifications);
  const [open, setOpen] = useState(false);
  const unread = list.filter((n) => !n.read).length;
  const sorted = [...list].sort((a, b) => b.at - a.at);
  const needs = sorted.filter((n) => n.group === "needs_you");
  const updates = sorted.filter((n) => n.group === "updates");
  const onOpen = (n) => {
    dispatchService.markNotificationRead(n.id);
    setOpen(false);
    openLink(n.link);
  };
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={`Notifications, ${unread} unread`}
          data-testid="notifications-bell"
          className="relative grid h-10 w-10 place-items-center rounded-[14px] bg-white/80 transition-colors hover:bg-white"
        >
          <Bell className="h-[18px] w-[18px]" strokeWidth={1.8} />
          {unread > 0 && (
            <span data-testid="notifications-unread-count" className="absolute -right-1 -top-1 grid h-[18px] min-w-[18px] place-items-center rounded-full bg-[#AF6EFF] px-1 text-[10.5px] font-semibold text-white tnum">
              {unread}
            </span>
          )}
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" sideOffset={10} className="w-[360px] rounded-[20px] border-white/90 bg-white/95 p-2 backdrop-blur-xl" data-testid="notifications-popover">
        <div className="flex items-center justify-between px-2.5 pb-1 pt-1.5">
          <span className="text-[14px] font-semibold">Notifications</span>
          <button type="button" className="text-[12px] font-medium text-[#7A35DB] hover:underline" onClick={dispatchService.markAllRead} data-testid="notifications-mark-all-read">
            Mark all read
          </button>
        </div>
        <div className="eyebrow px-2.5 pb-1 pt-2" data-testid="notifications-group-needs-you">Needs you</div>
        {needs.map((n) => <Item key={n.id} n={n} onOpen={onOpen} />)}
        <div className="mx-2.5 my-1.5 h-px bg-[#181A1A]/[0.06]" />
        <div className="eyebrow px-2.5 pb-1 pt-1" data-testid="notifications-group-updates">Updates</div>
        <div className="max-h-[280px] overflow-y-auto scroll-thin">
          {updates.map((n) => <Item key={n.id} n={n} onOpen={onOpen} />)}
        </div>
      </PopoverContent>
    </Popover>
  );
}
