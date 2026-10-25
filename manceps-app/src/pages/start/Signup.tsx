import type { FormEvent } from "react";
import { signupValid } from "../../logic/onboarding";
import { BUILD } from "./content";
import { FONT, INPUT, LABEL, TruckLoad, bizShown, type StageProps } from "./shared";

/** Demo email used by "Continue with Google". */
const DEMO_EMAIL = "jordan@goldenstate.co";

/** Sign-up form beside the "what you'll have" panel. */
export function Signup({ s, set }: StageProps): JSX.Element {
  const ok = signupValid(s.email, s.pw);
  const submit = (e: FormEvent): void => { e.preventDefault(); if (ok) set({ stage: "q" }); };
  return (
    <div data-screen-label="Sign up" style={{ minHeight: "100vh", display: "grid", gridTemplateColumns: "minmax(0,1fr) minmax(0,1fr)" }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 32, padding: "28px 40px" }}>
        <a href="/"><img src="/assets/manceps-logo-cut.png" alt="Manceps" style={{ height: 40, width: "auto", display: "block" }} /></a>
        <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <form onSubmit={submit} style={{ width: "100%", maxWidth: 400, display: "flex", flexDirection: "column", gap: 20, animation: "fadeUp .3s cubic-bezier(0,0,.2,1)" }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <h1 style={{ margin: 0, fontWeight: 400, fontSize: 36, lineHeight: 1.1, letterSpacing: "-0.015em" }}>Start dispatching free</h1>
              <p style={{ margin: 0, fontSize: 15, lineHeight: 1.5, color: "#3D4A5C" }}>No card. $0 until Manceps books your first load.</p>
            </div>
            <label style={LABEL}>Email<input type="email" value={s.email} onChange={(e) => set({ email: e.target.value })} placeholder="you@yourfleet.com" style={INPUT} /></label>
            <label style={LABEL}>Password<input type="password" value={s.pw} onChange={(e) => set({ pw: e.target.value })} placeholder="8+ characters" style={INPUT} /></label>
            <button type="submit" className="o-dark" style={{ height: 44, border: 0, borderRadius: 6, background: "#010D1D", color: "#FFFFFF", font: `15px ${FONT}`, cursor: "pointer", opacity: ok ? 1 : 0.4, transition: "background .2s cubic-bezier(.4,0,.2,1)" }}>Create Manceps account</button>
            <div style={{ display: "flex", alignItems: "center", gap: 12, fontSize: 12, color: "#8C9AAD" }}><span style={{ flex: 1, height: 1, background: "rgba(1,13,29,.1)" }} />or<span style={{ flex: 1, height: 1, background: "rgba(1,13,29,.1)" }} /></div>
            <button type="button" className="o-outline" onClick={() => set({ stage: "q", email: DEMO_EMAIL })} style={{ height: 44, border: "1px solid rgba(1,13,29,.18)", borderRadius: 6, background: "#FFFFFF", color: "#010D1D", font: `15px ${FONT}`, cursor: "pointer" }}>Continue with Google</button>
            <span style={{ fontSize: 13, color: "#64748A" }}>Already have an account? <a href="/app">Log in</a></span>
          </form>
        </div>
      </div>
      <div style={{ position: "relative", margin: 12, borderRadius: 8, overflow: "hidden", background: "linear-gradient(180deg,#FFFFFF 0%,#E6EFF7 100%)", display: "flex", flexDirection: "column", justifyContent: "flex-end", padding: 40, gap: 24 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 12, maxWidth: 440 }}>
          <span style={{ fontSize: 12, letterSpacing: ".015em", color: "#2272AD" }}>What you'll have in 3 minutes</span>
          <span style={{ fontSize: 32, lineHeight: 1.15, letterSpacing: "-0.015em" }}>An AI dispatcher that knows your trucks, drivers and lanes.</span>
        </div>
        <img src="/assets/truck-blue.png" alt="" style={{ width: "100%", maxWidth: 620, display: "block" }} />
      </div>
    </div>
  );
}

/** "Setting up your company" screen while the truck fills. */
export function Building({ s }: StageProps): JSX.Element {
  return (
    <div data-screen-label="Building" style={{ minHeight: "100vh", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 28, padding: 24, animation: "fadeUp .3s cubic-bezier(0,0,.2,1)" }}>
      <TruckLoad pct={(s.bi + 1) / BUILD.length} width="min(560px,90vw)" />
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8, textAlign: "center" }}>
        <span style={{ fontSize: 28, letterSpacing: "-0.015em" }}>Setting up {bizShown(s.biz)}</span>
        <span style={{ fontSize: 15, color: "#3D4A5C", display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ width: 14, height: 14, borderRadius: "50%", border: "2px solid #C3D4E3", borderTopColor: "#2272AD", animation: "spin .8s linear infinite" }} />{BUILD[s.bi]}
        </span>
      </div>
    </div>
  );
}
