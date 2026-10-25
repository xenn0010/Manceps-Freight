import { useEffect, useRef, type FormEvent, type KeyboardEvent } from "react";
import { agentOf } from "../agents";
import { setChatFocus } from "../actions";
import { ANSWERS, ask, presetName } from "../demo";
import { getState, setState, useAppState } from "../store";
import { agentLine } from "./Dock";
import { AgentAvatar, BLUE_SHELL, DemoTag, FONT, ICON_CLOSE, ICON_SEND, Icon } from "./ui";

const SHIELD = ["M12 3l7 3v5c0 4.5-3 8.5-7 10-4-1.5-7-5.5-7-10V6z", "M9 12l2 2 4-4"];

function ChatHeader(): JSX.Element {
  const s = useAppState();
  return (
    <div style={{ height: 60, display: "flex", alignItems: "center", gap: 12, padding: "0 8px 0 10px" }}>
      <AgentAvatar size={40} style={{ boxShadow: "0 0 0 2px rgba(255,255,255,.7)" }}>
        <span style={{ position: "absolute", right: -1, bottom: -1, width: 10, height: 10, borderRadius: "50%", background: "#2FD084", boxShadow: "0 0 0 2px #2272AD" }} />
      </AgentAvatar>
      <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 1, lineHeight: 1.2 }}>
        <span style={{ fontSize: 15, color: "#FFFFFF", display: "flex", alignItems: "center", gap: 8 }}>{agentOf(s.agent).name}<DemoTag dark /></span>
        <span style={{ fontSize: 12, color: "#E2E8F0" }}>{agentLine(s.trucks.length)}</span>
      </div>
      <button type="button" className="hv-glass" onClick={() => setState({ permOpen: true })} style={{ height: 36, display: "flex", alignItems: "center", gap: 8, padding: "0 14px 0 10px", border: 0, borderRadius: 18, background: "rgba(255,255,255,.18)", color: "#FFFFFF", font: `13px ${FONT}`, cursor: "pointer", whiteSpace: "nowrap" }}><Icon d={SHIELD} join />{presetName(s.perm)}</button>
      <button type="button" className="hv-ghost" onClick={() => setState({ chat: false })} aria-label="Close" style={{ width: 40, height: 40, border: 0, borderRadius: 6, background: "transparent", color: "#FFFFFF", cursor: "pointer", display: "grid", placeItems: "center" }}><Icon d={ICON_CLOSE} size={20} /></button>
    </div>
  );
}

function Messages(): JSX.Element | null {
  const s = useAppState();
  if (!s.msgs.length) return null;
  return (
    <div style={{ maxHeight: 240, overflow: "auto", display: "flex", flexDirection: "column", gap: 10, paddingBottom: 4 }}>
      {s.msgs.map((m, i) => (
        <div key={i} style={{ display: "flex", justifyContent: m.me ? "flex-end" : "flex-start", animation: "up .2s cubic-bezier(0,0,.2,1)" }}>
          <span className="pretty" style={{ maxWidth: "84%", padding: "9px 12px", borderRadius: 8, fontSize: 14, lineHeight: 1.5, background: m.me ? "#010D1D" : "#F1F5F9", color: m.me ? "#F1F5F9" : "#010D1D" }}>{m.text}</span>
        </div>
      ))}
    </div>
  );
}

function onKey(e: KeyboardEvent<HTMLTextAreaElement>): void {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(getState().text); }
}

function onSubmit(e: FormEvent): void {
  e.preventDefault();
  ask(getState().text);
}

/** Expanded chat with the agent: history, text box, suggestion chips and send. Answers are demo text. */
export function ChatPanel(): JSX.Element {
  const s = useAppState(), ta = useRef<HTMLTextAreaElement>(null), name = agentOf(s.agent).name;
  useEffect(() => { setChatFocus(() => ta.current?.focus()); return () => setChatFocus(null); }, []);
  return (
    <div style={BLUE_SHELL}>
      <ChatHeader />
      <form onSubmit={onSubmit} style={{ borderRadius: 10, background: "rgba(255,255,255,.84)", padding: "14px 14px 12px 18px", display: "flex", flexDirection: "column", gap: 12 }}>
        <Messages />
        <textarea ref={ta} value={s.text} onChange={(e) => setState({ text: e.target.value })} onKeyDown={onKey} rows={2} placeholder="What do you need? “Find a load for 104”, “Is 102 on time?”" style={{ border: 0, resize: "none", font: `16px/1.5 ${FONT}`, color: "#010D1D", background: "transparent", outline: "none", padding: 0 }} />
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div className="no-scrollbar" style={{ flex: 1, display: "flex", gap: 6, overflowX: "auto" }}>
            {Object.keys(ANSWERS).map((q) => (
              <button key={q} type="button" className="hv-chip" onClick={() => ask(q)} style={{ flexShrink: 0, height: 32, padding: "0 12px", border: "1px solid rgba(1,13,29,.1)", borderRadius: 16, background: "#FFFFFF", color: "#3D4A5C", font: `13px ${FONT}`, cursor: "pointer", whiteSpace: "nowrap" }}>{q}</button>
            ))}
          </div>
          <span style={{ height: 44, display: "flex", alignItems: "center", gap: 10, padding: "0 14px", borderRadius: 22, background: "rgba(255,255,255,.55)", fontSize: 14, whiteSpace: "nowrap" }}><AgentAvatar size={20} />{name} · Dispatch</span>
          <button type="submit" aria-label="Send" style={{ width: 48, height: 48, flexShrink: 0, border: 0, borderRadius: "50%", cursor: "pointer", display: "grid", placeItems: "center", color: "#FFFFFF", background: "linear-gradient(180deg,#3A86C2,#1B5E94)", boxShadow: "0 0 0 3px rgba(34,114,173,.18),0 8px 18px -6px rgba(27,94,148,.6)", opacity: s.text.trim() ? 1 : 0.5, transition: "opacity .2s" }}><Icon d={ICON_SEND} size={20} join /></button>
        </div>
      </form>
    </div>
  );
}
