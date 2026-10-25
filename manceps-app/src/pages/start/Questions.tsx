import { AgentFaceView } from "../../components/ThreeViews";
import { isAnswered, isPicked, pickCard } from "../../logic/onboarding";
import { AGENTS, QS, type Question } from "./content";
import { FONT, Glyph, INPUT, LABEL, bizShown, type StageProps } from "./shared";

function Cards({ q, s, set }: StageProps & { q: Extract<Question, { type: "cards" }> }): JSX.Element {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(220px,1fr))", gap: 12 }}>
      {q.opts.map(([label, sub, icon]) => {
        const on = isPicked(s.ans, q.key, label), border = on ? "#2272AD" : "rgba(1,13,29,.12)";
        return (
          <button key={label} type="button" className="o-blue-border" onClick={() => set((x) => ({ ans: pickCard(x.ans, q.key, q.multi, label) }))} style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 14, minHeight: 132, padding: 18, borderRadius: 8, cursor: "pointer", textAlign: "left", fontFamily: FONT, color: "#010D1D", background: "#FFFFFF", border: `1px solid ${border}`, boxShadow: on ? "0 0 0 1px #2272AD" : "none", transition: "border-color .2s,box-shadow .2s" }}>
            <div style={{ width: "100%", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ width: 36, height: 36, borderRadius: 6, background: "#EEF4FA", color: "#2272AD", display: "grid", placeItems: "center" }}><Glyph d={icon} size={20} /></span>
              <span style={{ width: 18, height: 18, borderRadius: q.multi ? 5 : "50%", border: `1.5px solid ${border}`, background: on ? "#2272AD" : "#FFFFFF", display: "grid", placeItems: "center", color: "#FFFFFF", fontSize: 11 }}>{on ? "✓" : ""}</span>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <span style={{ fontSize: 16 }}>{label}</span>
              <span style={{ fontSize: 13, lineHeight: 1.45, color: "#64748A" }}>{sub}</span>
            </div>
          </button>
        );
      })}
    </div>
  );
}

function Agents({ s, set }: StageProps): JSX.Element {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(4,minmax(0,1fr))", gap: 12 }}>
      {AGENTS.map((a) => {
        const on = s.agent === a.id;
        return (
          <button key={a.id} type="button" data-agent-card="1" onClick={() => set({ agent: a.id })} onMouseEnter={() => set({ hover: a.id })} onMouseLeave={() => set({ hover: null })} style={{ position: "relative", display: "flex", flexDirection: "column", alignItems: "center", gap: 12, padding: "24px 14px 20px", borderRadius: 8, cursor: "pointer", textAlign: "center", fontFamily: FONT, color: "#010D1D", background: "#FFFFFF", border: `1px solid ${on ? "#2272AD" : "rgba(1,13,29,.12)"}`, boxShadow: on ? "0 0 0 1px #2272AD" : "none", transition: "border-color .2s,box-shadow .2s" }}>
            <div style={{ position: "relative", width: 128, height: 128, borderRadius: "50%", background: "#EEF4FA" }}><AgentFaceView src={a.img} /></div>
            <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
              <span style={{ fontSize: 17 }}>{a.name}</span>
              <span style={{ fontSize: 12, letterSpacing: ".015em", color: "#2272AD" }}>{a.role}</span>
            </div>
            <span className="pretty" style={{ fontSize: 13, lineHeight: 1.45, color: "#3D4A5C" }}>{a.blurb}</span>
            {(s.hover === a.id || on) && <span style={{ position: "absolute", left: "50%", top: -14, transform: "translateX(-50%)", whiteSpace: "nowrap", background: "#010D1D", color: "#F1F5F9", borderRadius: 6, padding: "6px 10px", fontSize: 12.5, animation: "fadeUp .2s cubic-bezier(0,0,.2,1)", zIndex: 2 }}>{a.hello}</span>}
          </button>
        );
      })}
    </div>
  );
}

function NameForm({ s, set }: StageProps): JSX.Element {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16, maxWidth: 480 }}>
      <label style={LABEL}>Company name<input value={s.biz} onChange={(e) => set({ biz: e.target.value })} placeholder="Golden State Haulers" style={INPUT} /></label>
      <label style={LABEL}>Home base<input value={s.base} onChange={(e) => set({ base: e.target.value })} placeholder="Oakland, CA" style={INPUT} /></label>
      <span style={{ fontSize: 13, color: "#64748A" }}>Your agent introduces itself as calling from <span style={{ color: "#010D1D" }}>{bizShown(s.biz)}</span>.</span>
    </div>
  );
}

/**
 * Five setup questions with a progress bar, Back/Next footer and Skip.
 *
 * Args:
 *   s: Onboarding state.
 *   set: State updater.
 *   build: Start the "building" stage after the last question.
 */
export function Questions({ s, set, build }: StageProps & { build: () => void }): JSX.Element {
  const q = QS[s.qi] ?? QS[0] as Question, last = s.qi === QS.length - 1, answered = isAnswered(q, s);
  const advance = (): void => { if (last) build(); else set({ qi: s.qi + 1 }); };
  const btn = { height: 40, borderRadius: 6, font: `14px ${FONT}`, cursor: "pointer" };
  return (
    <div data-screen-label="Questions" style={{ minHeight: "100vh", display: "flex", flexDirection: "column" }}>
      <header style={{ height: 64, display: "flex", alignItems: "center", gap: 16, padding: "0 24px" }}>
        <img src="/assets/manceps-logo-cut.png" alt="Manceps" style={{ height: 36, width: "auto", display: "block" }} />
        <div style={{ flex: 1, display: "flex", justifyContent: "center", gap: 6 }}>
          {QS.map((_, i) => <span key={i} style={{ width: 56, height: 4, borderRadius: 2, background: i < s.qi ? "#010D1D" : i === s.qi ? "#2272AD" : "#D3DDE8", transition: "background .25s cubic-bezier(.4,0,.2,1)" }} />)}
        </div>
        <button type="button" className="o-soft" onClick={advance} style={{ height: 32, padding: "0 12px", border: 0, borderRadius: 6, background: "transparent", color: "#3D4A5C", font: `14px ${FONT}`, cursor: "pointer" }}>Skip</button>
      </header>
      <main style={{ flex: 1, display: "flex", justifyContent: "center", padding: "40px 24px 120px" }}>
        <div key={s.qi} style={{ width: "100%", maxWidth: q.type === "agents" ? 960 : 760, display: "flex", flexDirection: "column", gap: 28, animation: "fadeUp .3s cubic-bezier(0,0,.2,1)" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <span style={{ fontSize: 12, letterSpacing: ".015em", color: "#64748A" }}>{s.qi + 1} of {QS.length}</span>
            <h1 style={{ margin: 0, fontWeight: 400, fontSize: 32, lineHeight: 1.15, letterSpacing: "-0.015em" }}>{q.title}</h1>
            <p style={{ margin: 0, fontSize: 15, lineHeight: 1.5, color: "#3D4A5C" }}>{q.sub}</p>
          </div>
          {q.type === "cards" && <Cards q={q} s={s} set={set} />}
          {q.type === "agents" && <Agents s={s} set={set} />}
          {q.type === "name" && <NameForm s={s} set={set} />}
        </div>
      </main>
      <footer style={{ position: "fixed", left: 0, right: 0, bottom: 0, height: 72, display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 24px", background: "rgba(241,244,248,.92)", backdropFilter: "blur(10px)", WebkitBackdropFilter: "blur(10px)", borderTop: "1px solid rgba(1,13,29,.08)" }}>
        <button type="button" className="o-outline" onClick={() => set(s.qi > 0 ? { qi: s.qi - 1 } : { stage: "signup" })} style={{ ...btn, padding: "0 16px", border: "1px solid rgba(1,13,29,.18)", background: "#FFFFFF", color: "#010D1D" }}>Back</button>
        <button type="button" className="o-dark" onClick={() => { if (answered) advance(); }} style={{ ...btn, padding: "0 20px", border: 0, background: "#010D1D", color: "#FFFFFF", opacity: answered ? 1 : 0.4, transition: "background .2s cubic-bezier(.4,0,.2,1)" }}>{last ? "Create my dispatch" : "Next"}</button>
      </footer>
    </div>
  );
}
