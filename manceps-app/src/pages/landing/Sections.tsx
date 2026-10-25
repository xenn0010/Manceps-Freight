import { useEffect, useState, type CSSProperties } from "react";
import { AgentFaceView } from "../../components/ThreeViews";
import { AGENTS, CAPS, LOG, STEPS, type Step } from "./content";

const LINE = "1px solid rgba(1,13,29,.12)";
const LOG_MIN = 4;
const LOG_EVERY_MS = 2600;
const UPPER: CSSProperties = { letterSpacing: ".015em", textTransform: "uppercase" };
const H2: CSSProperties = { margin: 0, fontWeight: 400, fontSize: "clamp(36px,4.2vw,64px)", lineHeight: 1, letterSpacing: "-0.035em" };
const LEAD: CSSProperties = { margin: 0, maxWidth: 420, fontSize: 17, lineHeight: 1.55, color: "#3D4A5C", justifySelf: "end" };
const HEAD_GRID: CSSProperties = { display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(min(100%,380px),1fr))", gap: 32, alignItems: "end" };
const WHO_GREY: CSSProperties = { color: "#8C9AAD" };
const WHO_BLUE: CSSProperties = { color: "#2272AD" };

function Total({ label, value }: { label: string; value: string }): JSX.Element {
  return <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", paddingTop: 12, marginTop: 8, borderTop: "1px solid rgba(1,13,29,.1)", color: "#010D1D" }}>{label}<span style={{ fontSize: 26, letterSpacing: "-0.03em" }}>{value}</span></div>;
}

/** The right-hand proof for each step: a call, a chat, a tracking line. */
function StepProof({ n }: { n: string }): JSX.Element {
  if (n === "01") return (<>
    <div><span style={WHO_GREY}>Broker </span>Best I can do is $2,050.</div>
    <div><span style={WHO_BLUE}>Manceps </span>We're 12 miles out and empty. $2,300 and we take it now.</div>
    <div><span style={WHO_GREY}>Broker </span>$2,240 and it's yours.</div>
    <Total label="Booked · OAK → LAX" value="$2,240" />
  </>);
  if (n === "02") return (<>
    <div><span style={WHO_BLUE}>Manceps </span>Ava, it's Arjun, your AI dispatcher. You're on load 4471. Pickup Dock 3, Oakland, Tue 08:00. 26 pallets, 38,400 lb.</div>
    <div><span style={WHO_GREY}>Ava </span>Got it. Rolling at 07:15.</div>
    <Total label="Confirmed" value="06:52" />
  </>);
  return (<>
    <div style={{ display: "flex", justifyContent: "space-between" }}>Oakland<span>Los Angeles</span></div>
    <div style={{ position: "relative", height: 2, background: "rgba(1,13,29,.1)", margin: "8px 0 10px" }}>
      <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: "64%", background: "#010D1D" }} />
      <span style={{ position: "absolute", left: "64%", top: "50%", width: 10, height: 10, margin: "-5px 0 0 -5px", borderRadius: "50%", background: "#2272AD" }} />
    </div>
    <div>Roadwork on I-5 near Coalinga → rerouted via CA-33</div>
    <Total label="ETA · on time" value="16:40" />
  </>);
}

function StepRow({ s }: { s: Step }): JSX.Element {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "64px minmax(0,1.1fr) minmax(0,1fr)", gap: "clamp(20px,4vw,64px)", padding: "clamp(32px,5vh,52px) 0", borderBottom: LINE, alignItems: "start" }}>
      <span style={{ fontSize: 13, color: "#64748A", paddingTop: 8 }}>{s.n}</span>
      <div style={{ display: "flex", flexDirection: "column", gap: 14, maxWidth: 460 }}>
        <h3 style={{ margin: 0, fontWeight: 400, fontSize: "clamp(24px,2.4vw,32px)", letterSpacing: "-0.025em", lineHeight: 1.1 }}>{s.title}</h3>
        <p className="pretty" style={{ margin: 0, fontSize: 16, lineHeight: 1.55, color: "#3D4A5C" }}>{s.body}</p>
      </div>
      <div style={{ fontSize: 14, lineHeight: 1.65, color: "#3D4A5C", display: "flex", flexDirection: "column", gap: 2 }}>
        <div style={{ display: "flex", justifyContent: "space-between", color: "#64748A", fontSize: 11, ...UPPER, paddingBottom: 10 }}>{s.head}<span>{s.time}</span></div>
        <StepProof n={s.n} />
      </div>
    </div>
  );
}

/** "One load, start to finish": the three steps of a load. */
export function HowItWorks(): JSX.Element {
  return (
    <section id="how" data-screen-label="How it works" style={{ padding: "clamp(80px,12vh,130px) clamp(20px,4vw,48px) clamp(48px,8vh,96px)" }}>
      <div style={{ maxWidth: 1200, margin: "0 auto", display: "flex", flexDirection: "column", gap: 64 }}>
        <div style={HEAD_GRID}>
          <h2 style={H2}>One load,<br /><span style={{ color: "#2272AD" }}>start to finish.</span></h2>
          <p className="pretty" style={LEAD}>The film above is one real day for a Manceps truck. The agent did the work. The owner tapped once to approve the booking.</p>
        </div>
        <div style={{ display: "flex", flexDirection: "column", borderTop: LINE }}>{STEPS.map((s) => <StepRow key={s.n} s={s} />)}</div>
      </div>
    </section>
  );
}

function AgentLog(): JSX.Element {
  const [logN, setLogN] = useState(LOG_MIN);
  useEffect(() => { const t = window.setInterval(() => setLogN((n) => (n >= LOG.length ? LOG_MIN : n + 1)), LOG_EVERY_MS); return () => window.clearInterval(t); }, []);
  return (
    <div style={{ background: "#010D1D", color: "#E8F0F8", borderRadius: 8, padding: 24, display: "flex", flexDirection: "column", gap: 14, minHeight: 540 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontSize: 11, ...UPPER, color: "#8FA3BD" }}>Agent log · today</span>
        <span style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 11, ...UPPER, color: "#8FA3BD" }}><span style={{ width: 6, height: 6, borderRadius: "50%", background: "#2FB36B", animation: "pulse 1.8s ease infinite" }} />Working</span>
      </div>
      <div style={{ display: "flex", flexDirection: "column" }}>
        {LOG.slice(0, logN).map(([time, kind, color, text], i) => (
          <div key={time} style={{ display: "grid", gridTemplateColumns: "48px 76px minmax(0,1fr)", gap: 14, padding: "12px 0", borderBottom: "1px solid rgba(232,240,248,.08)", fontSize: 14, lineHeight: 1.45, animation: i === logN - 1 ? "fadeUp .5s ease" : "none" }}>
            <span style={{ fontSize: 12.5, color: "#64748A" }}>{time}</span>
            <span style={{ fontSize: 11, ...UPPER, color }}>{kind}</span>
            <span className="pretty">{text}</span>
          </div>
        ))}
      </div>
      <div style={{ marginTop: "auto", display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap", background: "rgba(232,240,248,.06)", borderRadius: 6, padding: "14px 16px" }}>
        <span style={{ fontSize: 14 }}>Approve $2,240 load for Truck 101?</span>
        <span style={{ display: "flex", gap: 8 }}>
          <span style={{ background: "#FFFFFF", color: "#010D1D", borderRadius: 4, padding: "7px 14px", fontSize: 13 }}>Approve</span>
          <span style={{ border: "1px solid rgba(232,240,248,.25)", borderRadius: 4, padding: "7px 14px", fontSize: 13 }}>Review</span>
        </span>
      </div>
    </div>
  );
}

/** "Every job a dispatcher does": capability list and the live agent log. */
export function AgentSection(): JSX.Element {
  return (
    <section id="agent" data-screen-label="The agent" style={{ padding: "clamp(48px,8vh,96px) clamp(20px,4vw,48px)" }}>
      <div style={{ maxWidth: 1200, margin: "0 auto", display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(min(100%,440px),1fr))", gap: "clamp(32px,5vw,72px)", alignItems: "start" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
          <h2 style={H2}>Every job<br /><span style={{ color: "#2272AD" }}>a dispatcher does.</span></h2>
          <p className="pretty" style={{ margin: 0, maxWidth: 440, fontSize: 17, lineHeight: 1.55, color: "#3D4A5C" }}>Works around the clock and knows your trucks, lanes and drivers. It always tells brokers and drivers it's an AI, and every call and message is logged, word for word.</p>
          <div style={{ display: "flex", flexDirection: "column", borderTop: LINE }}>
            {CAPS.map(([title, how], i) => (
              <div key={title} style={{ display: "grid", gridTemplateColumns: "36px minmax(0,1fr) minmax(0,1.2fr)", gap: 12, alignItems: "baseline", padding: "15px 0", borderBottom: LINE }}>
                <span style={{ fontSize: 12, color: "#64748A" }}>{String(i + 1).padStart(2, "0")}</span>
                <span style={{ fontSize: 16 }}>{title}</span>
                <span style={{ fontSize: 13.5, color: "#64748A", lineHeight: 1.4 }}>{how}</span>
              </div>
            ))}
          </div>
        </div>
        <AgentLog />
      </div>
    </section>
  );
}

/** "Pick who answers the phone": the four agent personas with live 3D faces. */
export function Dispatchers(): JSX.Element {
  return (
    <section id="agents" data-screen-label="Dispatchers" style={{ padding: "clamp(48px,8vh,96px) clamp(20px,4vw,48px) clamp(80px,12vh,130px)" }}>
      <div style={{ maxWidth: 1200, margin: "0 auto", display: "flex", flexDirection: "column", gap: 56 }}>
        <div style={HEAD_GRID}>
          <h2 style={H2}>Pick who<br /><span style={{ color: "#2272AD" }}>answers the phone.</span></h2>
          <p className="pretty" style={LEAD}>Same work, different voice with brokers and drivers. Choose one at sign-up, switch anytime.</p>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(min(100%,max(200px,calc(50% - 2px))),1fr))", borderTop: LINE, borderLeft: LINE }}>
          {AGENTS.map((a) => (
            <a key={a.name} href="/start" data-agent-card="1" className="l-card" style={{ padding: "36px 28px", display: "flex", flexDirection: "column", gap: 22, borderRight: LINE, borderBottom: LINE, transition: "background .25s" }}>
              <div style={{ width: 140, height: 140, borderRadius: "50%", background: "#E6EFF7", position: "relative" }}><AgentFaceView src={a.img} /></div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <span style={{ fontSize: 22, letterSpacing: "-0.02em" }}>{a.name}</span>
                <span style={{ fontSize: 11, ...UPPER, color: "#2272AD" }}>{a.role}</span>
              </div>
              <span className="pretty" style={{ fontSize: 14.5, lineHeight: 1.5, color: "#3D4A5C" }}>{a.blurb}</span>
            </a>
          ))}
        </div>
      </div>
    </section>
  );
}

/** Closing call to action and footer. */
export function Cta(): JSX.Element {
  return (
    <section id="start" data-screen-label="CTA" style={{ padding: "12px 12px 10px" }}>
      <div style={{ background: "#2272AD", color: "#FFFFFF", borderRadius: 10, padding: "clamp(72px,12vh,120px) 40px", display: "flex", flexDirection: "column", alignItems: "center", gap: 24, textAlign: "center" }}>
        <h2 className="balance" style={{ margin: 0, fontWeight: 400, fontSize: "clamp(44px,6vw,96px)", lineHeight: 0.95, letterSpacing: "-0.04em" }}>Let the truck dispatch itself.</h2>
        <p style={{ margin: 0, fontSize: 17, color: "#EAF2FA" }}>Set up in about three minutes. $0 until your first booked load.</p>
        <a href="/start" className="l-cta" style={{ height: 50, display: "flex", alignItems: "center", gap: 8, padding: "0 24px", background: "#010D1D", color: "#FFFFFF", borderRadius: 5, fontSize: 15 }}>Create your account <span>→</span></a>
      </div>
      <footer style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, flexWrap: "wrap", padding: "24px 10px 14px", fontSize: 13, color: "#8FA3BD" }}>
        <img src="/assets/manceps-logo-cut.png" alt="Manceps" style={{ height: 30, width: "auto", filter: "invert(1)" }} />
        <span>© 2026 Manceps. Demo content.</span>
      </footer>
    </section>
  );
}
