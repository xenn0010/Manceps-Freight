import { agentOf } from "../agents";
import { presetName, weekBars, weekStats, weekTotal } from "../demo";
import { signOut } from "../live/session";
import { setState, useAppState, type MeTab, type NotifKey } from "../store";
import { AgentSettings } from "./AgentSettings";
import { AgentAvatar, DemoTag, FONT, GLASS, ICON_CLOSE, Icon, Segmented, Switch } from "./ui";

const ME_TABS: [MeTab, string][] = [["dash", "Dashboard"], ["profile", "Profile"], ["settings", "Settings"]];
const ROW_LINE = "1px solid rgba(1,13,29,.06)";

function notifs(agent: string): [NotifKey, string, string][] {
  return [["push", "Push notifications", "Only for things that need your yes"], ["wa", "WhatsApp updates", agent + " texts you a short summary"], ["digest", "Daily email digest", "18:00 every weekday"]];
}

/** Weekly numbers; demo until /v1/dashboard/summary exists. */
function Dashboard(): JSX.Element {
  const s = useAppState(), wk = weekTotal(s.booked);
  return (
    <>
      <div style={{ display: "flex", flexDirection: "column", gap: 2, paddingTop: 10 }}>
        <span style={{ fontSize: 11.5, letterSpacing: ".015em", color: "#64748A", display: "flex", alignItems: "center", gap: 8 }}>This week<DemoTag /></span>
        <span style={{ fontSize: 30, letterSpacing: "-0.015em", fontVariantNumeric: "tabular-nums" }}>{wk.total}</span>
        <span style={{ fontSize: 12.5, color: wk.up ? "#17673E" : "#64748A" }}>{wk.delta}</span>
      </div>
      <div style={{ display: "flex", alignItems: "flex-end", gap: 6, height: 64 }}>
        {weekBars(s.booked).map((w, i) => (
          <div key={i} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 4, height: "100%", justifyContent: "flex-end" }}>
            <span style={{ width: "100%", borderRadius: 3, height: w.h, background: w.c }} />
            <span style={{ fontSize: 10.5, color: "#8C9AAD" }}>{w.d}</span>
          </div>
        ))}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
        {weekStats(s, agentOf(s.agent).name).map((f) => (
          <div key={f.k} style={{ borderRadius: 8, background: "rgba(255,255,255,.55)", padding: "10px 12px", display: "flex", flexDirection: "column", gap: 2 }}>
            <span style={{ fontSize: 18, letterSpacing: "-0.01em", fontVariantNumeric: "tabular-nums" }}>{f.v}</span>
            <span style={{ fontSize: 11.5, color: "#64748A" }}>{f.k}</span>
          </div>
        ))}
      </div>
    </>
  );
}

/** Live profile from /v1/me and /v1/firm. */
function Profile(): JSX.Element {
  const p = useAppState().profile;
  if (!p) return <span style={{ fontSize: 13.5, color: "#64748A", paddingTop: 10 }}>Loading your profile…</span>;
  return (
    <div style={{ display: "flex", flexDirection: "column", paddingTop: 4 }}>
      {p.rows.map(([k, v]) => (
        <div key={k} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, padding: "11px 0", borderBottom: ROW_LINE }}>
          <span style={{ fontSize: 12.5, color: "#64748A" }}>{k}</span>
          <span style={{ fontSize: 13.5, textAlign: "right", overflowWrap: "anywhere" }}>{v}</span>
        </div>
      ))}
    </div>
  );
}

function Settings(): JSX.Element {
  const s = useAppState(), name = agentOf(s.agent).name;
  return (
    <>
      <div style={{ display: "flex", flexDirection: "column", paddingTop: 4 }}>
        <AgentSettings />
        <button type="button" onClick={() => setState({ me: false, chat: true, permOpen: true })} style={{ display: "flex", alignItems: "center", gap: 12, padding: "11px 0", border: 0, borderBottom: ROW_LINE, background: "transparent", cursor: "pointer", textAlign: "left", fontFamily: FONT, color: "#010D1D" }}>
          <AgentAvatar size={28} />
          <span style={{ flex: 1, display: "flex", flexDirection: "column", gap: 1 }}>
            <span style={{ fontSize: 14 }}>{name}'s permissions</span>
            <span style={{ fontSize: 12, color: "#64748A" }}>{presetName(s.perm)}</span>
          </span>
          <DemoTag />
          <Icon d="M9 6l6 6-6 6" stroke="#8C9AAD" />
        </button>
        {notifs(name).map(([k, label, desc]) => (
          <div key={k} style={{ display: "flex", alignItems: "center", gap: 12, padding: "11px 0", borderBottom: ROW_LINE }}>
            <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 1 }}>
              <span style={{ fontSize: 14, display: "flex", alignItems: "center", gap: 8 }}>{label}<DemoTag /></span>
              <span style={{ fontSize: 12, color: "#64748A" }}>{desc}</span>
            </div>
            <Switch on={s.notif[k]} label={label} onClick={() => setState((x) => ({ notif: { ...x.notif, [k]: !x.notif[k] } }))} />
          </div>
        ))}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "11px 0", borderBottom: ROW_LINE }}>
          <span style={{ fontSize: 14 }}>Units</span>
          <span style={{ fontSize: 13.5, color: "#3D4A5C" }}>Miles · USD</span>
        </div>
      </div>
      <button type="button" className="hv-signout" onClick={() => void signOut()} style={{ height: 40, border: 0, borderRadius: 6, background: "rgba(1,13,29,.05)", color: "#B23A31", font: `14px ${FONT}`, cursor: "pointer" }}>Sign out</button>
    </>
  );
}

/** Account panel with weekly dashboard, profile and settings tabs. */
export function MePanel(): JSX.Element {
  const s = useAppState(), p = s.profile;
  return (
    <div style={{ position: "absolute", right: 20, top: 68, width: 360, maxHeight: "calc(100vh - 92px)", display: "flex", flexDirection: "column", borderRadius: 14, ...GLASS, overflow: "hidden", zIndex: 5, animation: "up .22s cubic-bezier(0,0,.2,1)" }}>
      <div style={{ padding: "16px 16px 12px", display: "flex", alignItems: "center", gap: 12 }}>
        <span style={{ width: 44, height: 44, borderRadius: "50%", background: "#010D1D", color: "#F1F5F9", display: "grid", placeItems: "center", fontSize: 14, flexShrink: 0 }}>{p?.initials ?? ""}</span>
        <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 1 }}>
          <span style={{ fontSize: 16, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{p?.name ?? "Loading…"}</span>
          <span style={{ fontSize: 12.5, color: "#64748A", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{p?.subtitle ?? ""}</span>
        </div>
        <button type="button" className="hv-soft" onClick={() => setState({ me: false })} aria-label="Close" style={{ width: 32, height: 32, border: 0, borderRadius: 6, background: "rgba(1,13,29,.05)", color: "#3D4A5C", cursor: "pointer", display: "grid", placeItems: "center" }}><Icon d={ICON_CLOSE} /></button>
      </div>
      <div style={{ padding: "0 16px 12px" }}>
        <Segmented items={ME_TABS} value={s.meTab} onChange={(k) => setState({ meTab: k })} />
      </div>
      <div style={{ flex: 1, minHeight: 0, overflow: "auto", padding: "4px 16px 16px", display: "flex", flexDirection: "column", gap: 14, borderTop: "1px solid rgba(1,13,29,.06)" }}>
        {s.meTab === "dash" && <Dashboard />}
        {s.meTab === "profile" && <Profile />}
        {s.meTab === "settings" && <Settings />}
      </div>
    </div>
  );
}
