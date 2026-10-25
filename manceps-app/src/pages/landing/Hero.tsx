import { useEffect, useState, type CSSProperties } from "react";
import { HeroFilm } from "../../components/ThreeViews";
import { BROKERS, CAPTIONS, SCREEN, STATUS_LINES, TASKS } from "./content";

/** Hero scene phase in which the scene shrinks onto the dark "screen". */
const AGENT_PHASE = 3;
const SCREEN_LINE_MS = 1100;
const WAVE_MS = 140;
/** Wave ticks per status-line change. */
const STATUS_EVERY = 25;
const UPPER: CSSProperties = { letterSpacing: ".015em", textTransform: "uppercase" };
const SCREEN_INSET: CSSProperties = { position: "absolute", left: 24, right: 24, top: 84, bottom: 24 };

function Marquee(): JSX.Element {
  const twice = [...BROKERS, ...BROKERS];
  return (
    <div style={{ borderTop: "1px solid rgba(1,13,29,.08)", padding: "18px 0 22px", display: "flex", flexDirection: "column", gap: 14, overflow: "hidden" }}>
      <span style={{ textAlign: "center", fontSize: 11, ...UPPER, color: "#64748A" }}>Booking loads with brokers across the West</span>
      <div style={{ overflow: "hidden", WebkitMaskImage: "linear-gradient(90deg,transparent,#000 12%,#000 88%,transparent)", maskImage: "linear-gradient(90deg,transparent,#000 12%,#000 88%,transparent)" }}>
        <div style={{ display: "flex", width: "max-content", animation: "marquee 38s linear infinite" }}>
          {twice.map(([name, ls, tt], i) => <span key={i} style={{ padding: "0 26px", whiteSpace: "nowrap", color: "#8C9AAD", fontSize: 17, letterSpacing: ls, textTransform: tt }}>{name}</span>)}
        </div>
      </div>
    </div>
  );
}

function HeroCopy({ wv }: { wv: number }): JSX.Element {
  return (
    <div style={{ background: "#FFFFFF", borderRadius: 6, display: "grid", gridTemplateRows: "auto minmax(0,1fr) auto", overflow: "hidden" }}>
      <div style={{ height: 64, display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 20px 0 24px", borderBottom: "1px solid rgba(1,13,29,.08)" }}>
        <img src="/assets/manceps-logo-cut.png" alt="Manceps" style={{ height: 44, width: "auto", display: "block" }} />
        <span style={{ display: "flex", alignItems: "center", gap: 10, height: 36, padding: "0 12px 0 4px", background: "#F3F7FB", borderRadius: 6 }}>
          <span style={{ position: "relative", width: 28, height: 28, flexShrink: 0 }}>
            <img src="/assets/agent-d.jpg" alt="" style={{ width: 28, height: 28, borderRadius: "50%", objectFit: "cover", objectPosition: "center 22%", display: "block", background: "#E6EFF7" }} />
            <span style={{ position: "absolute", right: -1, bottom: -1, width: 9, height: 9, borderRadius: "50%", background: "#1F9A5A", boxShadow: "0 0 0 2px #F3F7FB" }} />
          </span>
          <span style={{ display: "flex", flexDirection: "column", lineHeight: 1.15 }}>
            <span style={{ fontSize: 13, color: "#010D1D" }}>Arjun is dispatching</span>
            <span style={{ fontSize: 11, letterSpacing: ".015em", color: "#64748A" }}>{STATUS_LINES[Math.floor(wv / STATUS_EVERY) % STATUS_LINES.length]}</span>
          </span>
        </span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", padding: "32px clamp(28px,3.4vw,56px)", gap: 28 }}>
        <span style={{ fontSize: 12, ...UPPER, color: "#2272AD" }}>AI dispatch for owner-operators</span>
        <h1 className="balance" style={{ margin: 0, fontWeight: 400, fontSize: "clamp(46px,min(5.2vw,9vh),88px)", lineHeight: 0.98, letterSpacing: "-0.035em" }}>Dispatch that <span style={{ color: "#2272AD" }}>drives itself.</span></h1>
        <p className="pretty" style={{ margin: 0, maxWidth: 400, fontSize: 17, lineHeight: 1.5, color: "#3D4A5C" }}>Manceps finds loads, calls brokers, briefs drivers and keeps every truck moving. You only hear about it when it needs a yes.</p>
        <div style={{ display: "flex", alignItems: "center", gap: 24, flexWrap: "wrap" }}>
          <a href="/start" className="l-dark" style={{ height: 50, display: "flex", alignItems: "center", gap: 8, padding: "0 22px", background: "#010D1D", color: "#FFFFFF", borderRadius: 5, fontSize: 15 }}>Dispatch yourself <span>→</span></a>
          <a href="#how" style={{ fontSize: 15, borderBottom: "1px solid currentColor", paddingBottom: 2 }}>See how it works</a>
        </div>
      </div>
      <Marquee />
    </div>
  );
}

function AgentScreen({ on, sN, wv }: { on: boolean; sN: number; wv: number }): JSX.Element {
  const lines = Math.min(SCREEN.length, sN);
  return (
    <div style={{ ...SCREEN_INSET, padding: 20, boxSizing: "border-box", zIndex: 2, display: "grid", gridTemplateColumns: "36% minmax(0,1fr)", gap: 18, color: "#E8F0F8", pointerEvents: "none", opacity: on ? 1 : 0, transition: "opacity .3s cubic-bezier(0,0,.2,1) .25s" }}>
      <div style={{ display: "flex", flexDirection: "column", justifyContent: "flex-end", gap: 8 }}>
        <span style={{ fontSize: 11, ...UPPER, color: "#7FA6CC" }}>Truck 101 · live</span>
        <span style={{ fontSize: 13.5, color: "#C9D6E6" }}>OAK → LAX · 64% · ETA 16:40</span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 14, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <img src="/assets/agent-d.jpg" alt="" style={{ width: 44, height: 44, borderRadius: "50%", objectFit: "cover", objectPosition: "center 22%", background: "#E8F0F8" }} />
          <div style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
            <span style={{ fontSize: 15, color: "#FFFFFF" }}>Arjun · on a call</span>
            <span style={{ fontSize: 12.5, color: "#7FA6CC" }}>Lining up tomorrow's backhaul</span>
          </div>
          <span style={{ marginLeft: "auto", display: "flex", gap: 2, alignItems: "center", height: 18 }}>
            {[0, 1, 2, 3, 4].map((i) => <span key={i} style={{ width: 3, borderRadius: 2, background: "#4C9BFF", height: on && lines % 2 === 1 ? 4 + Math.abs(Math.sin(wv * 0.9 + i * 1.7)) * 14 : 3, transition: "height .15s" }} />)}
          </span>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8, fontSize: 13, lineHeight: 1.45 }}>
          {SCREEN.slice(0, lines).map(([who, color, text]) => (
            <div key={text} style={{ display: "flex", flexDirection: "column", gap: 2, animation: "fadeUp .4s ease both" }}>
              <span style={{ fontSize: 10.5, ...UPPER, color }}>{who}</span>
              <span className="pretty" style={{ color: "#E2E8F0" }}>{text}</span>
            </div>
          ))}
        </div>
        <div style={{ marginTop: "auto", display: "flex", flexDirection: "column", gap: 6, borderTop: "1px solid rgba(232,240,248,.12)", paddingTop: 12 }}>
          {TASKS.map((label, i) => {
            const done = sN > SCREEN.length + i;
            return <div key={label} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12.5, color: done ? "#E8F0F8" : "#64748A" }}><span style={{ width: 14, height: 14, borderRadius: "50%", display: "grid", placeItems: "center", fontSize: 9, background: done ? "#4C9BFF" : "rgba(232,240,248,.15)", color: "#010D1D" }}>{done ? "✓" : ""}</span>{label}</div>;
          })}
        </div>
      </div>
    </div>
  );
}

function SceneNav(): JSX.Element {
  const link = (href: string, label: string): JSX.Element => <a href={href} className="l-nav" style={{ fontSize: 14, whiteSpace: "nowrap", color: "#3D4A5C" }}>{label}</a>;
  return (
    <nav style={{ position: "absolute", left: 0, right: 0, top: 0, zIndex: 3, height: 64, display: "flex", alignItems: "center", gap: "clamp(14px,2.2vw,36px)", padding: "0 14px 0 20px", overflow: "hidden", background: "rgba(255,255,255,.7)", backdropFilter: "blur(12px)", WebkitBackdropFilter: "blur(12px)", borderBottom: "1px solid rgba(1,13,29,.08)" }}>
      {link("#how", "How it works")}{link("#agent", "The agent")}{link("#agents", "Dispatchers")}
      <span style={{ flex: 1 }} />
      <a href="/start" className="l-dark" style={{ height: 36, display: "flex", alignItems: "center", padding: "0 16px", background: "#010D1D", color: "#FFFFFF", borderRadius: 5, fontSize: 13.5, whiteSpace: "nowrap", flexShrink: 0 }}>Sign up</a>
    </nav>
  );
}

function Caption({ phase, on }: { phase: number; on: boolean }): JSX.Element {
  const cap = CAPTIONS[phase] ?? CAPTIONS[0];
  return (
    <div style={{ position: "absolute", left: 20, bottom: 20, zIndex: 3, width: 300, opacity: on ? 1 : 0, transition: "opacity .4s", background: "rgba(255,255,255,.78)", backdropFilter: "blur(14px)", WebkitBackdropFilter: "blur(14px)", border: "1px solid rgba(1,13,29,.06)", borderRadius: 6, padding: "16px 18px", display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "flex", gap: 4 }}>{CAPTIONS.map((_, i) => <span key={i} style={{ height: 2, flex: 1, background: i <= phase ? "#010D1D" : "rgba(1,13,29,.15)", transition: "background .4s" }} />)}</div>
      <span style={{ fontSize: 11, ...UPPER, color: "#2272AD" }}>{cap?.tag}</span>
      <span style={{ fontSize: 18, letterSpacing: "-0.01em" }}>{cap?.title}</span>
      <span className="pretty" style={{ fontSize: 13.5, lineHeight: 1.45, color: "#3D4A5C" }}>{cap?.body}</span>
    </div>
  );
}

/** Split hero: copy and broker marquee on the left, the 3D film on the right. */
export function Hero(): JSX.Element {
  const [phase, setPhase] = useState(0), [sN, setSN] = useState(0), [wv, setWv] = useState(0);
  const scr = phase === AGENT_PHASE;
  useEffect(() => { const t = window.setInterval(() => setWv((x) => x + 1), WAVE_MS); return () => window.clearInterval(t); }, []);
  useEffect(() => {
    setSN(0);
    if (!scr) return;
    const t = window.setInterval(() => setSN((x) => x + 1), SCREEN_LINE_MS);
    return () => window.clearInterval(t);
  }, [scr]);
  return (
    <section data-screen-label="Hero" style={{ height: "100vh", minHeight: 680, boxSizing: "border-box", padding: 12, display: "flex", flexDirection: "column" }}>
      <div style={{ flex: 1, minHeight: 0, background: "#2272AD", borderRadius: 10, padding: 8, display: "grid", gridTemplateColumns: "minmax(400px,40%) minmax(0,1fr)", gap: 8 }}>
        <HeroCopy wv={wv} />
        <div style={{ position: "relative", borderRadius: 6, overflow: "hidden", background: "linear-gradient(180deg,#FFFFFF 0%,#F3F6FA 55%,#E3ECF4 100%)" }}>
          <div style={{ ...SCREEN_INSET, pointerEvents: "none", borderRadius: 8, background: "rgba(1,13,29,.92)", boxShadow: "0 30px 60px -20px rgba(1,13,29,.6)", opacity: scr ? 1 : 0, transition: "opacity .3s cubic-bezier(0,0,.2,1)" }} />
          <div style={{ position: "absolute", inset: 0, zIndex: 1, transformOrigin: "0 0", transition: "transform .45s cubic-bezier(.4,0,.2,1), border-radius .45s", overflow: "hidden", transform: scr ? "translate(44px,104px) scale(.36)" : "none", borderRadius: scr ? 14 : 0 }}>
            <HeroFilm onPhase={setPhase} />
          </div>
          <AgentScreen on={scr} sN={sN} wv={wv} />
          <SceneNav />
          <Caption phase={phase} on={!scr} />
        </div>
      </div>
    </section>
  );
}
