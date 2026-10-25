import { useState, type CSSProperties, type ReactNode } from "react";
import { agentOf } from "../agents";
import { useAppState } from "../store";

export const FONT = "'Alliance No.2',system-ui";

/** Frosted glass surface shared by the header, cards and panels. */
export const GLASS: CSSProperties = {
  background: "rgba(255,255,255,.58)",
  backdropFilter: "blur(22px) saturate(170%)",
  WebkitBackdropFilter: "blur(22px) saturate(170%)",
  border: "1px solid rgba(255,255,255,.75)",
  boxShadow: "inset 0 1px 0 rgba(255,255,255,.9),0 1px 2px rgba(1,13,29,.06),0 24px 48px -24px rgba(1,13,29,.35)",
};

/** Blue gradient shell for the chat and permissions panels. */
export const BLUE_SHELL: CSSProperties = {
  position: "absolute", left: "50%", bottom: 24, width: "min(680px,calc(100vw - 40px))", transform: "translateX(-50%)",
  padding: "0 6px 6px", boxSizing: "border-box", borderRadius: 14,
  background: "linear-gradient(115deg,rgba(27,94,148,.82) 0%,rgba(34,114,173,.72) 45%,rgba(76,155,255,.6) 100%)",
  backdropFilter: "blur(24px) saturate(160%)", WebkitBackdropFilter: "blur(24px) saturate(160%)",
  border: "1px solid rgba(255,255,255,.4)", boxShadow: "0 30px 60px -24px rgba(1,13,29,.45)", animation: "rise .25s cubic-bezier(0,0,.2,1)",
};

export const ENTER = "up .25s cubic-bezier(0,0,.2,1)";

/** Colors for a segmented-control button. */
export function segStyle(on: boolean): { background: string; color: string; boxShadow: string } {
  return { background: on ? "#FFFFFF" : "transparent", color: on ? "#010D1D" : "#64748A", boxShadow: on ? "0 1px 2px rgba(1,13,29,.12)" : "none" };
}

interface IconProps {
  d: string | string[];
  size?: number;
  stroke?: string;
  width?: number;
  join?: boolean;
}

/**
 * Line icon on a 24px grid.
 *
 * Args:
 *   d: Path data, or several paths.
 *   size: Rendered size in px.
 *   stroke: Stroke color.
 *   width: Stroke width.
 *   join: Use round line joins.
 */
export function Icon({ d, size = 16, stroke = "currentColor", width = 1.5, join = false }: IconProps): JSX.Element {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={stroke} strokeWidth={width} strokeLinecap="round" strokeLinejoin={join ? "round" : undefined}>
      {(Array.isArray(d) ? d : [d]).map((p) => <path key={p} d={p} />)}
    </svg>
  );
}

export const ICON_CLOSE = "M6 6l12 12M18 6L6 18";
export const ICON_SEND = "M12 19V5M6 11l6-6 6 6";

/**
 * Round photo of the firm's chosen agent persona; draws initials if the photo fails to load.
 *
 * Args:
 *   size: Diameter in px.
 *   style: Extra styles.
 *   children: Overlays such as a status dot.
 */
export function AgentAvatar({ size, style, children }: { size: number; style?: CSSProperties; children?: ReactNode }): JSX.Element {
  const a = agentOf(useAppState().agent);
  return <PersonaPhoto src={a.avatar} initials={a.initials} size={size} style={style}>{children}</PersonaPhoto>;
}

/**
 * Round persona photo with an initials fallback for load errors.
 *
 * Args:
 *   src: Image path.
 *   initials: Letters shown if the image fails.
 *   size: Diameter in px.
 *   style: Extra styles.
 *   children: Overlays such as a status dot.
 */
export function PersonaPhoto({ src, initials, size, style, children }: { src: string; initials: string; size: number; style?: CSSProperties; children?: ReactNode }): JSX.Element {
  const [failed, setFailed] = useState<string | null>(null);
  const broken = failed === src;
  return (
    <span style={{ position: "relative", width: size, height: size, borderRadius: "50%", flexShrink: 0, display: "grid", placeItems: "center", background: "#E6EFF7", color: "#1B5E94", fontSize: Math.max(9, Math.round(size * 0.38)), lineHeight: 1, ...style }}>
      {broken ? initials : <img src={src} alt="" onError={() => setFailed(src)} style={{ position: "absolute", inset: 0, width: "100%", height: "100%", borderRadius: "50%", objectFit: "cover", objectPosition: "center 22%" }} />}
      {children}
    </span>
  );
}

/**
 * Small tag marking a surface that shows demo data, not the firm's live data.
 *
 * Args:
 *   dark: Use the light-on-dark variant for blue or ink backgrounds.
 *   style: Extra styles.
 */
export function DemoTag({ dark = false, style }: { dark?: boolean; style?: CSSProperties }): JSX.Element {
  return <span title="Sample data. Not your firm's live data yet." style={{ flexShrink: 0, display: "inline-flex", alignItems: "center", height: 18, padding: "0 7px", borderRadius: 9, fontSize: 10.5, letterSpacing: ".04em", lineHeight: 1, background: dark ? "rgba(255,255,255,.2)" : "rgba(227,154,45,.16)", color: dark ? "#FFFFFF" : "#8A5A12", border: dark ? "1px solid rgba(255,255,255,.35)" : "1px solid rgba(227,154,45,.3)", ...style }}>Demo</span>;
}

/** Shared input look for forms on glass panels. */
export const FIELD: CSSProperties = { height: 40, boxSizing: "border-box", padding: "0 12px", border: "1px solid rgba(1,13,29,.14)", borderRadius: 6, background: "#FFFFFF", color: "#010D1D", font: "14px 'Alliance No.2',system-ui", outline: "none", minWidth: 0 };

/** Primary dark button. */
export const BTN_PRIMARY: CSSProperties = { height: 40, padding: "0 16px", border: 0, borderRadius: 6, background: "#010D1D", color: "#FFFFFF", font: "14px 'Alliance No.2',system-ui", cursor: "pointer", transition: "background .2s cubic-bezier(.4,0,.2,1)" };

/** Secondary outlined button. */
export const BTN_OUTLINE: CSSProperties = { height: 40, padding: "0 14px", border: "1px solid rgba(1,13,29,.14)", borderRadius: 6, background: "#FFFFFF", color: "#010D1D", font: "14px 'Alliance No.2',system-ui", cursor: "pointer" };

/**
 * iOS-style toggle.
 *
 * Args:
 *   on: Current value.
 *   label: Accessible name.
 *   onClick: Toggle handler.
 */
export function Switch({ on, label, onClick }: { on: boolean; label: string; onClick: () => void }): JSX.Element {
  return (
    <button type="button" onClick={onClick} role="switch" aria-checked={on} aria-label={label} style={{ width: 44, height: 26, flexShrink: 0, border: 0, borderRadius: 13, cursor: "pointer", position: "relative", background: on ? "#2272AD" : "#C3CEDA", transition: "background .2s" }}>
      <span style={{ position: "absolute", top: 3, left: on ? 21 : 3, width: 20, height: 20, borderRadius: "50%", background: "#FFFFFF", boxShadow: "0 1px 3px rgba(1,13,29,.3)", transition: "left .2s cubic-bezier(.4,0,.2,1)" }} />
    </button>
  );
}

/**
 * Label over value, used in the truck and account fact grids.
 *
 * Args:
 *   k: Label.
 *   v: Value.
 *   ink: Value color.
 *   tabular: Use tabular numerals.
 */
export function Fact({ k, v, ink, tabular = false }: { k: string; v: string; ink?: string; tabular?: boolean }): JSX.Element {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
      <span style={{ fontSize: 11.5, letterSpacing: ".015em", color: "#64748A" }}>{k}</span>
      <span style={{ fontSize: 13.5, fontVariantNumeric: tabular ? "tabular-nums" : undefined, color: ink }}>{v}</span>
    </div>
  );
}

/** Two-column grid of facts. */
export const FACT_GRID: CSSProperties = { display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px 16px" };

/**
 * Segmented tabs used in the account and truck panels.
 *
 * Args:
 *   items: [key, label] pairs.
 *   value: Selected key.
 *   onChange: Called with the clicked key.
 *   style: Extra container styles.
 */
export function Segmented<K extends string>({ items, value, onChange, style }: { items: [K, string][]; value: K; onChange: (k: K) => void; style?: CSSProperties }): JSX.Element {
  return (
    <div style={{ display: "flex", gap: 2, padding: 3, borderRadius: 7, background: "rgba(1,13,29,.05)", ...style }}>
      {items.map(([k, label]) => (
        <button key={k} type="button" onClick={() => onChange(k)} style={{ flex: 1, height: 30, border: 0, borderRadius: 5, cursor: "pointer", font: `12.5px ${FONT}`, ...segStyle(value === k) }}>{label}</button>
      ))}
    </div>
  );
}
