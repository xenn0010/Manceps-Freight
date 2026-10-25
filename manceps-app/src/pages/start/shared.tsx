import { useEffect, useRef, type CSSProperties } from "react";
import { truckBoxes, type OnboardState } from "../../logic/onboarding";

export type SetOnboard = (patch: Partial<OnboardState> | ((s: OnboardState) => Partial<OnboardState>)) => void;

export interface StageProps {
  s: OnboardState;
  set: SetOnboard;
}

export const FONT = "'Alliance No.2',system-ui";

export const INPUT: CSSProperties = { height: 44, border: "1px solid rgba(1,13,29,.18)", borderRadius: 6, padding: "0 14px", font: `15px ${FONT}`, color: "#010D1D", background: "#FFFFFF" };
export const LABEL: CSSProperties = { display: "flex", flexDirection: "column", gap: 6, fontSize: 13 };

/**
 * White truck whose trailer fills with blue boxes as progress grows.
 *
 * Args:
 *   pct: Progress 0 to 1.
 *   width: CSS width of the graphic.
 *   small: Tighter gaps and corners for the compact version.
 *   alt: Image alt text.
 */
export function TruckLoad({ pct, width, small = false, alt = "" }: { pct: number; width: string; small?: boolean; alt?: string }): JSX.Element {
  const prev = useRef(0);
  const { boxes, filled } = truckBoxes(pct, prev.current);
  useEffect(() => { prev.current = filled; }, [filled]);
  return (
    <div style={{ position: "relative", width, aspectRatio: "720/164" }}>
      <img src="/assets/truck-white.png" alt={alt} style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }} />
      <div style={{ position: "absolute", left: "33%", right: "2.6%", top: "3.5%", height: "58%", display: "grid", gridTemplateColumns: "repeat(12,1fr)", gridTemplateRows: "repeat(3,1fr)", gridAutoFlow: "column", gap: small ? 1 : 2, padding: small ? 2 : 3, boxSizing: "border-box" }}>
        {boxes.map((b, i) => <span key={i} style={{ borderRadius: small ? 1 : 2, background: b.bg, opacity: b.op, animation: b.anim, boxShadow: small ? undefined : "inset 0 0 0 1px rgba(1,13,29,.12)" }} />)}
      </div>
    </div>
  );
}

/** Line icon on a 24px grid with round caps and joins. */
export function Glyph({ d, size = 16 }: { d: string; size?: number }): JSX.Element {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d={d} /></svg>;
}

/** The business name, or "your company" until one is entered. */
export const bizShown = (biz: string): string => biz.trim() || "your company";
