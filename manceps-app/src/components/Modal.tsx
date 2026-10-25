import type { ReactNode } from "react";
import { ENTER, GLASS, ICON_CLOSE, Icon } from "./ui";

/**
 * Centered glass dialog over a dimmed screen.
 *
 * Args:
 *   title: Heading.
 *   onClose: Called by the close button and a click on the backdrop.
 *   width: Dialog width in px.
 *   children: Body.
 */
export function Modal({ title, onClose, width = 520, children }: { title: string; onClose: () => void; width?: number; children: ReactNode }): JSX.Element {
  return (
    <div role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }} style={{ position: "absolute", inset: 0, zIndex: 20, display: "grid", placeItems: "center", padding: 20, background: "rgba(1,13,29,.18)" }}>
      <div role="dialog" aria-modal="true" aria-label={title} style={{ width: "min(" + width + "px,100%)", maxHeight: "calc(100vh - 40px)", display: "flex", flexDirection: "column", borderRadius: 14, ...GLASS, background: "rgba(255,255,255,.86)", overflow: "hidden", animation: ENTER }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "14px 14px 10px 18px" }}>
          <span style={{ flex: 1, fontSize: 17, letterSpacing: "-0.01em" }}>{title}</span>
          <button type="button" className="hv-soft" onClick={onClose} aria-label="Close" style={{ width: 32, height: 32, border: 0, borderRadius: 6, background: "rgba(1,13,29,.05)", color: "#3D4A5C", cursor: "pointer", display: "grid", placeItems: "center" }}><Icon d={ICON_CLOSE} /></button>
        </div>
        <div style={{ flex: 1, minHeight: 0, overflow: "auto", padding: "4px 18px 18px" }}>{children}</div>
      </div>
    </div>
  );
}
