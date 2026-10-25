import { useEffect, useState, useSyncExternalStore, type FormEvent, type ReactNode } from "react";
import { auth, client } from "../api";
import { SignInFlow, type SignInState } from "../auth/flow";
import { formatUsPhone, typingUsPhone } from "../auth/phone";
import { enterWith } from "../live/session";
import { useAppState } from "../store";
import { BTN_PRIMARY, FIELD, FONT, GLASS } from "./ui";

const LINK = { border: 0, background: "transparent", padding: 0, color: "#2272AD", font: `13px ${FONT}`, cursor: "pointer" } as const;
const MUTED = { fontSize: 13.5, lineHeight: 1.5, color: "#3D4A5C" } as const;

function useFlow(resume: boolean): [SignInFlow, SignInState] {
  const [flow] = useState(() => new SignInFlow({
    api: auth,
    onTokens: (t) => { client.setTokens(t); if (t.state === "active") enterWith(t); },
  }));
  const st = useSyncExternalStore((l) => flow.subscribe(l), () => flow.state);
  useEffect(() => {
    if (resume) void flow.resumeProvisioning();
    return () => flow.stop();
  }, [flow, resume]);
  return [flow, st];
}

function Card({ title, sub, children }: { title: string; sub?: ReactNode; children: ReactNode }): JSX.Element {
  return (
    <div style={{ width: "min(400px,100%)", boxSizing: "border-box", borderRadius: 16, ...GLASS, padding: "28px 24px 24px", display: "flex", flexDirection: "column", gap: 14, animation: "up .25s cubic-bezier(0,0,.2,1)" }}>
      <img src="/assets/manceps-logo-cut.png" alt="Manceps" style={{ height: 36, width: "auto", alignSelf: "flex-start" }} />
      <span style={{ fontSize: 22, letterSpacing: "-0.015em", marginTop: 6 }}>{title}</span>
      {sub && <span className="pretty" style={MUTED}>{sub}</span>}
      {children}
    </div>
  );
}

function Submit({ busy, label }: { busy: boolean; label: string }): JSX.Element {
  return <button type="submit" className="hv-primary" disabled={busy} style={{ ...BTN_PRIMARY, opacity: busy ? 0.6 : 1 }}>{busy ? "One moment…" : label}</button>;
}

function Problem({ text }: { text: string | null }): JSX.Element | null {
  return text ? <span role="alert" style={{ fontSize: 13, color: "#B23A31", lineHeight: 1.45 }}>{text}</span> : null;
}

function PhoneStep({ flow, st, note }: { flow: SignInFlow; st: SignInState; note: string | null }): JSX.Element {
  const [phone, setPhone] = useState("");
  const go = (e: FormEvent): void => { e.preventDefault(); void flow.submitPhone(phone); };
  return (
    <Card title="Sign in to Manceps" sub="Enter your mobile number. We'll text you a code.">
      {note && <span style={{ fontSize: 13, color: "#8A5A12" }}>{note}</span>}
      <form onSubmit={go} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <input autoFocus value={phone} onChange={(e) => setPhone(typingUsPhone(e.target.value))} inputMode="tel" autoComplete="tel-national" placeholder="(214) 555-0199" aria-label="Mobile number" style={FIELD} />
        <Problem text={st.error} />
        <Submit busy={st.busy} label="Text me a code" />
      </form>
      <span style={{ fontSize: 12, color: "#8C9AAD" }}>US numbers only. Message and data rates may apply.</span>
    </Card>
  );
}

function CodeStep({ flow, st, phone }: { flow: SignInFlow; st: SignInState; phone: string }): JSX.Element {
  const [code, setCode] = useState("");
  const go = (e: FormEvent): void => { e.preventDefault(); void flow.submitCode(code); };
  return (
    <Card title="Enter your code" sub={"We texted a code to " + formatUsPhone(phone) + "."}>
      <form onSubmit={go} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <input autoFocus value={code} onChange={(e) => setCode(e.target.value.replace(/[^0-9]/g, "").slice(0, 10))} inputMode="numeric" autoComplete="one-time-code" placeholder="123456" aria-label="Code" style={{ ...FIELD, letterSpacing: ".2em", fontVariantNumeric: "tabular-nums" }} />
        <Problem text={st.error} />
        <Submit busy={st.busy} label="Continue" />
      </form>
      <div style={{ display: "flex", justifyContent: "space-between" }}>
        <button type="button" onClick={() => flow.back()} style={LINK}>Use another number</button>
        <button type="button" disabled={st.busy} onClick={() => void flow.resend()} style={LINK}>Send a new code</button>
      </div>
    </Card>
  );
}

function FirmStep({ flow, st }: { flow: SignInFlow; st: SignInState }): JSX.Element {
  const [name, setName] = useState("");
  const [terms, setTerms] = useState(false);
  const go = (e: FormEvent): void => { e.preventDefault(); void flow.submitFirm(name, terms); };
  return (
    <Card title="Set up your firm" sub="New here. What's your company called?">
      <form onSubmit={go} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <input autoFocus value={name} maxLength={200} onChange={(e) => setName(e.target.value)} autoComplete="organization" placeholder="Golden State Dispatch LLC" aria-label="Company name" style={FIELD} />
        <label style={{ display: "flex", alignItems: "flex-start", gap: 10, fontSize: 13, color: "#3D4A5C", lineHeight: 1.45, cursor: "pointer" }}>
          <input type="checkbox" checked={terms} onChange={(e) => setTerms(e.target.checked)} style={{ marginTop: 2 }} />
          I accept the Manceps terms of service and privacy policy.
        </label>
        <Problem text={st.error} />
        <Submit busy={st.busy} label="Create my firm" />
      </form>
      <button type="button" onClick={() => flow.back()} style={{ ...LINK, alignSelf: "flex-start" }}>Start over</button>
    </Card>
  );
}

function ProvisioningStep({ st }: { st: SignInState }): JSX.Element {
  const step = st.step.k === "provisioning" ? st.step : null;
  const failed = step?.status === "failed";
  const sub = failed ? step?.message ?? "Setting up your firm failed. Contact Manceps support." : step?.slow ? "This is taking longer than usual. You can leave this page open; it continues on its own." : "This takes about a minute. We're creating your workspace and your AI dispatcher.";
  return (
    <Card title={failed ? "We couldn't set up your firm" : "Setting up your firm"} sub={sub}>
      {!failed && <span style={{ height: 4, borderRadius: 2, background: "#E2E8F0", overflow: "hidden", position: "relative" }}><span style={{ position: "absolute", inset: 0, borderRadius: 2, background: "#2272AD", animation: "pulse 1.6s ease-in-out infinite" }} /></span>}
      <Problem text={st.error} />
    </Card>
  );
}

/** Phone sign-in gate for /app: phone -> code -> (new user) firm name -> setting up your firm -> the app. */
export function SignIn(): JSX.Element {
  const s = useAppState();
  const [flow, st] = useFlow(s.session === "provisioning");
  const k = st.step.k;
  return (
    <div style={{ position: "fixed", inset: 0, display: "grid", placeItems: "center", padding: 20, overflow: "auto", background: "radial-gradient(55% 45% at 12% 88%,rgba(34,114,173,.18),transparent 70%),radial-gradient(45% 40% at 92% 8%,rgba(76,155,255,.16),transparent 70%),#F4F6F9" }}>
      {k === "phone" && <PhoneStep flow={flow} st={st} note={s.sessionNote} />}
      {k === "code" && st.step.k === "code" && <CodeStep flow={flow} st={st} phone={st.step.phone} />}
      {k === "firm" && <FirmStep flow={flow} st={st} />}
      {(k === "provisioning" || k === "done") && <ProvisioningStep st={st} />}
    </div>
  );
}
