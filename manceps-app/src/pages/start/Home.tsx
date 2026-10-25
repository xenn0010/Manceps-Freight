import { completeTask, nextUploadProgress, setupSummary } from "../../logic/onboarding";
import { AGENTS, AGENT_ACTIVE_AFTER, IMPORTS, SIDE_NAV, TASKS, type Agent, type Task } from "./content";
import { FONT, Glyph, TruckLoad, bizShown, type StageProps } from "./shared";

const UPLOAD_TICK_MS = 160;
/** Pause before moving to the dashboard once every task is done. */
const FINISH_REDIRECT_MS = 900;
const CARD_SHADOW = "0 0 0 1px rgba(1,13,29,.06)";

function upload(set: StageProps["set"], id: string, file: File | undefined): void {
  if (!file) return;
  set((s) => ({ imp: { ...s.imp, [id]: { name: file.name, p: 0 } } }));
  const t = window.setInterval(() => set((s) => {
    const c = s.imp[id];
    if (!c) { window.clearInterval(t); return {}; }
    const p = nextUploadProgress(c.p, Math.random());
    if (p >= 100) window.clearInterval(t);
    return { imp: { ...s.imp, [id]: { ...c, p } } };
  }), UPLOAD_TICK_MS);
}

function Imports({ s, set }: StageProps): JSX.Element {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {IMPORTS.map((im) => {
        const st = s.imp[im.id], done = Boolean(st && st.p >= 100), busy = Boolean(st && !done);
        return (
          <label key={im.id} style={{ display: "grid", gridTemplateColumns: "36px minmax(0,1fr) auto", gap: 12, alignItems: "center", padding: "10px 12px", borderRadius: 6, cursor: "pointer", background: "#FFFFFF", border: `1px solid ${done ? "#1F9A5A" : "rgba(1,13,29,.12)"}` }}>
            <span style={{ width: 36, height: 36, borderRadius: 6, background: "#EEF4FA", color: "#1B5E94", display: "grid", placeItems: "center", fontSize: 11, letterSpacing: ".015em" }}>{im.badge}</span>
            <span style={{ display: "flex", flexDirection: "column", gap: 3, minWidth: 0 }}>
              <span style={{ fontSize: 14 }}>{im.title}</span>
              <span style={{ fontSize: 12, color: "#64748A", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{im.sub}</span>
              {busy && <span style={{ height: 3, borderRadius: 2, background: "#E2E8F0", overflow: "hidden" }}><span style={{ display: "block", height: "100%", background: "#2272AD", width: (st?.p ?? 0) + "%" }} /></span>}
            </span>
            <span style={{ fontSize: 13, whiteSpace: "nowrap", color: done ? "#1F9A5A" : "#2272AD" }}>{done ? "✓ " + (st?.name ?? "") : busy ? "Reading…" : "Upload"}</span>
            <input type="file" accept={im.accept} onChange={(e) => upload(set, im.id, e.target.files?.[0])} style={{ display: "none" }} />
          </label>
        );
      })}
    </div>
  );
}

function TaskArt({ t, agent }: { t: Task; agent: Agent }): JSX.Element {
  const round = t.artR === "50%", src = t.art === "AGENT" ? agent.img : t.art;
  return (
    <div style={{ borderRadius: 6, background: "linear-gradient(180deg,#F3F7FB,#E6EFF7)", display: "flex", alignItems: "center", justifyContent: "center", minHeight: 112, overflow: "hidden" }}>
      <span style={{ width: t.artW, height: round ? t.artW : "72px", borderRadius: t.artR, background: `url(${src}) center 22% / ${round ? "cover" : "contain"} no-repeat` }} />
    </div>
  );
}

function TaskRow({ t, s, set, agent }: StageProps & { t: Task; agent: Agent }): JSX.Element {
  const done = Boolean(s.done[t.id]), open = s.open === t.id;
  const nImp = Object.values(s.imp).filter((x) => x.p >= 100).length;
  const complete = (): void => {
    const next = completeTask(s.done, t.id);
    set(next);
    if (!next.open) window.setTimeout(() => { window.location.href = "/app"; }, FINISH_REDIRECT_MS);
  };
  return (
    <div style={{ borderRadius: 6, background: open ? "#F6F9FC" : "transparent", transition: "background .2s" }}>
      <button type="button" onClick={() => set({ open: open ? null : t.id })} style={{ width: "100%", display: "flex", alignItems: "center", gap: 12, padding: "10px 12px", border: 0, background: "transparent", cursor: "pointer", textAlign: "left", font: `14px ${FONT}`, color: "#010D1D" }}>
        <span style={{ width: 20, height: 20, flexShrink: 0, borderRadius: "50%", border: `1.5px ${done ? "solid" : "dashed"} ${done ? "#010D1D" : "#8C9AAD"}`, background: done ? "#010D1D" : "transparent", display: "grid", placeItems: "center", marginTop: 1 }}>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" style={{ opacity: done ? 1 : 0 }}><path d="M5 12l5 5 9-10" /></svg>
        </span>
        <span style={{ flex: 1, color: done && !open ? "#64748A" : "#010D1D" }}>{t.title}</span>
        {t.optional && <span style={{ fontSize: 11.5, color: "#64748A" }}>Optional</span>}
      </button>
      {open && (
        <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) 180px", gap: 20, padding: "0 12px 16px 44px", animation: "fadeUp .2s cubic-bezier(0,0,.2,1)" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <p style={{ margin: 0, fontSize: 13.5, lineHeight: 1.55, color: "#3D4A5C", maxWidth: "56ch" }}>{t.body}</p>
            {t.isImport && <Imports s={s} set={set} />}
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button type="button" className="o-dark" onClick={complete} style={{ height: 36, padding: "0 14px", border: 0, borderRadius: 6, background: "#010D1D", color: "#FFFFFF", font: `13.5px ${FONT}`, cursor: "pointer" }}>{t.isImport && nImp ? `Done · ${nImp} imported` : t.cta}</button>
              <button type="button" className="o-tint" onClick={() => set((x) => ({ done: { ...x.done, [t.id]: !done } }))} style={{ height: 36, padding: "0 12px", border: 0, borderRadius: 6, background: "transparent", color: "#2272AD", font: `13.5px ${FONT}`, cursor: "pointer" }}>{done ? "Mark as not done" : "Mark as done"}</button>
            </div>
          </div>
          <TaskArt t={t} agent={agent} />
        </div>
      )}
    </div>
  );
}

function TopBar({ s, agent }: { s: StageProps["s"]; agent: Agent }): JSX.Element {
  return (
    <div style={{ gridColumn: "1 / -1", display: "flex", alignItems: "center", gap: 16, padding: "0 16px", background: "#010D1D" }}>
      <img src="/assets/manceps-logo-cut.png" alt="Manceps" style={{ height: 32, width: "auto", filter: "invert(1)" }} />
      <div style={{ flex: 1, display: "flex", justifyContent: "center" }}>
        <div style={{ width: "min(480px,100%)", height: 34, borderRadius: 6, background: "rgba(241,245,249,.1)", display: "flex", alignItems: "center", gap: 8, padding: "0 12px", fontSize: 13.5, color: "#8FA3BD" }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"><circle cx="11" cy="11" r="7" /><path d="M20 20l-4-4" /></svg>Search trucks, drivers, loads
        </div>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, color: "#E2E8F0", fontSize: 13 }}>
        <span style={{ width: 28, height: 28, borderRadius: "50%", background: `#E6EFF7 url(${agent.img}) center 22% / cover no-repeat` }} />{bizShown(s.biz)}
      </div>
    </div>
  );
}

function GuideHeader({ doneN, agentFirst }: { doneN: number; agentFirst: string }): JSX.Element {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) 240px", gap: 20, alignItems: "center", padding: "20px 20px 16px", borderBottom: "1px solid rgba(1,13,29,.06)" }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <span style={{ fontSize: 16 }}>Setup guide</span>
        <span style={{ fontSize: 13.5, color: "#3D4A5C" }}>Use this guide to get {agentFirst} dispatching on its own.</span>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 6 }}>
          <span style={{ fontSize: 12.5, color: "#3D4A5C", whiteSpace: "nowrap" }}>{doneN} of {TASKS.length} tasks complete</span>
          <span style={{ flex: 1, maxWidth: 160, height: 4, borderRadius: 2, background: "#E2E8F0", overflow: "hidden" }}><span style={{ display: "block", height: "100%", background: "#2272AD", width: Math.round((doneN / TASKS.length) * 100) + "%", transition: "width .3s cubic-bezier(.4,0,.2,1)" }} /></span>
        </div>
      </div>
      <TruckLoad pct={doneN / TASKS.length} width="240px" small alt="Truck load shows setup progress" />
    </div>
  );
}

/** Workspace home with the setup guide, the chosen agent and a summary of answers. */
export function Home({ s, set }: StageProps): JSX.Element {
  const agent = AGENTS.find((a) => a.id === s.agent) ?? (AGENTS[0] as Agent), first = agent.name.split(" ")[0] ?? agent.name;
  const doneN = TASKS.filter((t) => s.done[t.id]).length;
  return (
    <div data-screen-label="Setup guide" style={{ minHeight: "100vh", display: "grid", gridTemplateColumns: "232px minmax(0,1fr)", gridTemplateRows: "56px minmax(0,1fr)", background: "#F1F4F8" }}>
      <TopBar s={s} agent={agent} />
      <aside style={{ padding: "12px 8px", display: "flex", flexDirection: "column", gap: 2, borderRight: "1px solid rgba(1,13,29,.08)", background: "#EAEFF5" }}>
        {SIDE_NAV.map(([label, icon, on]) => <span key={label} style={{ height: 32, display: "flex", alignItems: "center", gap: 10, padding: "0 10px", borderRadius: 6, fontSize: 13.5, background: on ? "#FFFFFF" : "transparent", color: on ? "#010D1D" : "#3D4A5C" }}><Glyph d={icon} />{label}</span>)}
      </aside>
      <main style={{ padding: "28px 24px 64px", display: "flex", justifyContent: "center", overflow: "auto" }}>
        <div style={{ width: "100%", maxWidth: 860, display: "flex", flexDirection: "column", gap: 20 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", gap: 16, flexWrap: "wrap" }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <h1 style={{ margin: 0, fontWeight: 400, fontSize: 28, letterSpacing: "-0.015em" }}>Welcome, {bizShown(s.biz)}</h1>
              <span style={{ fontSize: 14, color: "#3D4A5C" }}>{first} is ready. Finish these and your trucks are fully loaded.</span>
            </div>
            <a href="/app" className="o-skip" style={{ height: 36, display: "flex", alignItems: "center", padding: "0 14px", borderRadius: 6, border: "1px solid rgba(1,13,29,.18)", background: "#FFFFFF", color: "#010D1D", fontSize: 13.5 }}>Skip to dashboard</a>
          </div>
          <section style={{ background: "#FFFFFF", borderRadius: 8, boxShadow: "0 1px 2px rgba(1,13,29,.06),0 0 0 1px rgba(1,13,29,.06)", overflow: "hidden" }}>
            <GuideHeader doneN={doneN} agentFirst={first} />
            <div style={{ display: "flex", flexDirection: "column", padding: 8 }}>{TASKS.map((t) => <TaskRow key={t.id} t={t} s={s} set={set} agent={agent} />)}</div>
          </section>
          <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(240px,1fr))", gap: 12 }}>
            <div style={{ background: "#FFFFFF", borderRadius: 8, boxShadow: CARD_SHADOW, padding: "16px 18px", display: "flex", gap: 12, alignItems: "center" }}>
              <span style={{ width: 40, height: 40, flexShrink: 0, borderRadius: "50%", background: `#EEF4FA url(${agent.img}) center 22% / cover no-repeat` }} />
              <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}><span style={{ fontSize: 14 }}>{first} · {agent.role}</span><span style={{ fontSize: 12.5, color: "#64748A" }}>{doneN >= AGENT_ACTIVE_AFTER ? "Searching loads on your lanes" : "Waiting for your setup to finish"}</span></div>
            </div>
            <div style={{ background: "#FFFFFF", borderRadius: 8, boxShadow: CARD_SHADOW, padding: "16px 18px", display: "flex", flexDirection: "column", gap: 2 }}>
              <span style={{ fontSize: 12, letterSpacing: ".015em", color: "#64748A" }}>Your setup</span>
              <span style={{ fontSize: 14 }}>{setupSummary(s.ans)}</span>
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}
