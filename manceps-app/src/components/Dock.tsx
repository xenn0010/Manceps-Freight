import { agentOf } from "../agents";
import { openChat } from "../actions";
import { useAppState } from "../store";
import { AgentAvatar, DemoTag, FONT } from "./ui";

/**
 * Status line under the agent's name, from the live truck count.
 *
 * Args:
 *   trucks: Number of trucks in the fleet.
 *
 * Returns:
 *   What the agent is watching.
 */
export function agentLine(trucks: number): string {
  if (!trucks) return "Add a truck to get started";
  return "Watching " + trucks + (trucks === 1 ? " truck" : " trucks");
}

/** Dark pill toast centered above the dock; scripted demo activity carries a Demo tag. */
export function Toast(): JSX.Element | null {
  const s = useAppState();
  if (!s.toast || s.chat) return null;
  return (
    <div role="status" style={{ position: "absolute", left: "50%", bottom: s.view === "sheet" ? 72 : 104, zIndex: 8, transform: "translateX(-50%)", display: "flex", alignItems: "center", gap: 10, height: 40, padding: "0 14px 0 10px", borderRadius: 20, background: "rgba(1,13,29,.72)", backdropFilter: "blur(16px)", WebkitBackdropFilter: "blur(16px)", border: "1px solid rgba(255,255,255,.12)", color: "#F1F5F9", fontSize: 13.5, whiteSpace: "nowrap", boxShadow: "0 12px 28px -12px rgba(1,13,29,.5)", animation: "rise .25s cubic-bezier(0,0,.2,1)" }}>
      <span style={{ position: "relative", width: 8, height: 8, borderRadius: "50%", background: "#4C9BFF" }}>
        <span style={{ position: "absolute", inset: 0, borderRadius: "50%", background: "#4C9BFF", animation: "ping 1.4s cubic-bezier(0,0,.2,1) infinite" }} />
      </span>
      {s.toast.demo && <DemoTag dark />}
      {s.toast.text}
    </div>
  );
}

/** Collapsed "Ask <agent>" pill; slides left when a side panel is open. */
export function AskPill(): JSX.Element {
  const s = useAppState(), name = agentOf(s.agent).name;
  return (
    <button type="button" className="hv-pill" onClick={openChat} aria-label={"Talk to " + name} style={{ position: "absolute", left: s.sel || s.me ? "calc(50% - 190px)" : "50%", bottom: 28, transform: "translateX(-50%)", display: "flex", alignItems: "center", gap: 12, height: 60, padding: "0 22px 0 6px", borderRadius: 30, cursor: "pointer", background: "rgba(255,255,255,.58)", backdropFilter: "blur(22px) saturate(170%)", WebkitBackdropFilter: "blur(22px) saturate(170%)", border: "1px solid rgba(255,255,255,.75)", fontFamily: FONT, color: "#010D1D", boxShadow: "0 1px 2px rgba(1,13,29,.08),0 18px 40px -16px rgba(1,13,29,.35)", transition: "box-shadow .2s cubic-bezier(.4,0,.2,1)" }}>
      <span style={{ position: "relative", width: 48, height: 48, flexShrink: 0 }}>
        <span style={{ position: "absolute", inset: 0, borderRadius: "50%", background: "#2272AD", animation: "ping 2.2s cubic-bezier(0,0,.2,1) infinite" }} />
        <AgentAvatar size={48} style={{ position: "absolute", inset: 0, boxShadow: "0 0 0 2px #FFFFFF,0 0 0 4px #2272AD" }} />
      </span>
      <span style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 1, lineHeight: 1.2 }}>
        <span style={{ fontSize: 15 }}>Ask {name}</span>
        <span style={{ fontSize: 12, color: "#64748A" }}>{agentLine(s.trucks.length)}</span>
      </span>
      <span style={{ marginLeft: 6, fontSize: 11, padding: "3px 6px", borderRadius: 4, background: "rgba(1,13,29,.05)", color: "#64748A" }}>/</span>
    </button>
  );
}
