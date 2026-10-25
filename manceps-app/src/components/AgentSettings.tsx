import { useState } from "react";
import { AGENT_NAME_MAX, DEFAULT_AGENT_NAME, PERSONAS, agentOf, cleanAgentName, initialsOf, type AgentSelection } from "../agents";
import { showToast } from "../actions";
import { saveAgentSelection } from "../demo";
import { setState, useAppState } from "../store";
import { DemoTag, FIELD, FONT, PersonaPhoto } from "./ui";

function choose(sel: AgentSelection): void {
  setState({ agent: sel });
  if (!saveAgentSelection(sel)) showToast("Saved for this visit only; this browser blocks storage");
}

/** Persona picker and rename field. Kept in this browser until the backend stores agent settings. */
export function AgentSettings(): JSX.Element {
  const s = useAppState(), cur = agentOf(s.agent);
  const [draft, setDraft] = useState(cur.name);
  const commit = (): void => {
    const name = cleanAgentName(draft);
    setDraft(name);
    if (name !== cur.name) choose({ ...s.agent, name });
  };
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, padding: "11px 0", borderBottom: "1px solid rgba(1,13,29,.06)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ fontSize: 14, flex: 1 }}>Your AI dispatcher</span>
        <DemoTag />
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,minmax(0,1fr))", gap: 6 }}>
        {PERSONAS.map((p) => {
          const on = p.id === s.agent.personaId;
          return (
            <button key={p.id} type="button" title={p.fullName + " · " + p.description} aria-pressed={on} onClick={() => choose({ ...s.agent, personaId: p.id })} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6, padding: "10px 4px 8px", borderRadius: 8, cursor: "pointer", fontFamily: FONT, color: "#010D1D", background: on ? "#EEF5FB" : "#FFFFFF", border: on ? "1.5px solid #2272AD" : "1px solid rgba(1,13,29,.1)" }}>
              <PersonaPhoto src={p.avatar} initials={initialsOf(p.fullName)} size={40} />
              <span style={{ fontSize: 11.5, lineHeight: 1.2, textAlign: "center" }}>{p.fullName.split(" ")[0]}</span>
              <span style={{ fontSize: 10.5, lineHeight: 1.2, color: "#64748A", textAlign: "center" }}>{p.role}</span>
            </button>
          );
        })}
      </div>
      <span className="pretty" style={{ fontSize: 12, color: "#64748A" }}>{cur.persona.description}</span>
      <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 12, color: "#64748A" }}>
        Name it goes by
        <input value={draft} maxLength={AGENT_NAME_MAX} placeholder={DEFAULT_AGENT_NAME} onChange={(e) => setDraft(e.target.value)} onBlur={commit} onKeyDown={(e) => { if (e.key === "Enter") commit(); }} style={FIELD} />
      </label>
      <span style={{ fontSize: 11.5, color: "#8C9AAD" }}>It always tells drivers and brokers that it's an AI.</span>
    </div>
  );
}
