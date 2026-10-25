// DOM for map markers: truck labels, checkpoints, voice bubbles and dispatch pulses.
import { BLUE, INK } from "./geo";

export interface Bubble {
  mode: "agent" | "you";
  who: string;
  text: string;
}

export type CheckState = "done" | "next" | "upcoming";

const WAVE_BARS = 5;
const WAVE_STAGGER_MS = 110;

/**
 * Escape text for safe insertion into marker HTML.
 *
 * Args:
 *   s: Raw text.
 *
 * Returns:
 *   HTML-escaped text.
 */
export function esc(s: string): string {
  const map: Record<string, string> = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" };
  return s.replace(/[&<>"]/g, (c) => map[c] ?? c);
}

/**
 * Inject the map's keyframes and attribution styling once.
 */
export function ensureMapCss(): void {
  if (document.getElementById("m3-css")) return;
  const st = document.createElement("style");
  st.id = "m3-css";
  st.textContent = "@keyframes m3ring{0%{transform:scale(.3);opacity:.9}100%{transform:scale(3.2);opacity:0}}@keyframes m3ping{0%{transform:scale(.7);opacity:.8}100%{transform:scale(2.1);opacity:0}}@keyframes m3bub{from{opacity:0;transform:translate(-50%,6px) scale(.96)}to{opacity:1;transform:translate(-50%,0) scale(1)}}@keyframes m3wave{0%,100%{transform:scaleY(.35)}50%{transform:scaleY(1)}}.maplibregl-ctrl-attrib{font-size:10px;background:rgba(255,255,255,.7)!important}";
  document.head.appendChild(st);
}

/**
 * City label marker element.
 *
 * Args:
 *   name: City name.
 *
 * Returns:
 *   A non-interactive label element.
 */
export function cityEl(name: string): HTMLDivElement {
  const m = document.createElement("div");
  m.style.cssText = "pointer-events:none";
  m.innerHTML = `<span style="font:12px 'Alliance No.2',system-ui;color:#64748A;white-space:nowrap;text-shadow:0 0 3px #F4F6F9,0 0 3px #F4F6F9">${esc(name)}</span>`;
  return m;
}

/**
 * Truck marker: unit label, selection ping, hit target and bubble slot.
 *
 * Args:
 *   unit: Truck unit number.
 *   onClick: Called when the label or hit area is clicked.
 *
 * Returns:
 *   The zero-size anchor element.
 */
export function truckEl(unit: string, onClick: () => void): HTMLDivElement {
  const m = document.createElement("div");
  m.style.cssText = "position:relative;width:0;height:0;pointer-events:none";
  m.innerHTML = `<div data-bub style="position:absolute;left:0;bottom:52px;transform:translateX(-50%);display:none;pointer-events:none"></div><button type="button" data-lbl style="position:absolute;left:50%;bottom:22px;transform:translateX(-50%);pointer-events:auto;cursor:pointer;border:0;padding:2px 8px;border-radius:5px;background:#fff;color:${INK};font:12px/18px 'Alliance No.2',system-ui;white-space:nowrap;box-shadow:0 4px 12px -6px rgba(1,13,29,.45);transition:background .2s,color .2s">${esc(unit)}</button><span data-ping style="position:absolute;left:-22px;top:-22px;width:44px;height:44px;border-radius:50%;background:rgba(34,114,173,.28);opacity:0"></span><button type="button" data-hit aria-label="Truck ${esc(unit)}" style="position:absolute;left:-18px;top:-18px;width:36px;height:36px;border:0;border-radius:50%;background:transparent;cursor:pointer;pointer-events:auto"></button>`;
  const go = (e: Event): void => { e.stopPropagation(); onClick(); };
  m.querySelector("[data-lbl]")?.addEventListener("click", go);
  m.querySelector("[data-hit]")?.addEventListener("click", go);
  return m;
}

/**
 * Style a truck marker as selected or not.
 *
 * Args:
 *   m: Truck marker element.
 *   on: Whether this truck is selected.
 */
export function styleTruckEl(m: HTMLElement, on: boolean): void {
  const l = m.querySelector<HTMLElement>("[data-lbl]"), p = m.querySelector<HTMLElement>("[data-ping]");
  if (l) { l.style.background = on ? BLUE : "#fff"; l.style.color = on ? "#fff" : INK; }
  if (p) p.style.animation = on ? "m3ping 1.8s cubic-bezier(0,0,.2,1) infinite" : "none";
}

/**
 * Checkpoint marker with a status dot and a label.
 *
 * Args:
 *   name: Checkpoint label.
 *
 * Returns:
 *   The zero-size anchor element.
 */
export function checkEl(name: string): HTMLDivElement {
  const e = document.createElement("div");
  e.style.cssText = "position:relative;width:0;height:0;pointer-events:none";
  e.innerHTML = `<span data-dot style="position:absolute;left:-7px;top:-7px;width:14px;height:14px;border-radius:50%;box-sizing:border-box;display:grid;place-items:center"></span><span style="position:absolute;left:12px;top:-9px;font:11.5px/18px 'Alliance No.2',system-ui;color:#3D4A5C;white-space:nowrap;padding:0 6px;border-radius:4px;background:rgba(255,255,255,.88)">${esc(name)}</span>`;
  return e;
}

/**
 * Restyle a checkpoint dot for its state.
 *
 * Args:
 *   e: Checkpoint marker element.
 *   st: Passed, next or upcoming.
 */
export function styleCheckEl(e: HTMLElement, st: CheckState): void {
  const d = e.querySelector<HTMLElement>("[data-dot]");
  if (!d) return;
  d.style.cssText += st === "done" ? `;background:${INK};border:0;box-shadow:0 0 0 2px #fff` : st === "next" ? `;background:#fff;border:3px solid ${BLUE};box-shadow:0 0 0 2px #fff` : ";background:#fff;border:2px solid #8C9AAD;box-shadow:none";
  d.innerHTML = st === "done" ? '<svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12l5 5 9-10"/></svg>' : "";
}

/**
 * HTML for a voice bubble above a truck.
 *
 * Args:
 *   b: Who is speaking, the call mode and the line.
 *
 * Returns:
 *   Bubble markup.
 */
export function bubbleHtml(b: Bubble): string {
  const dark = b.mode === "you";
  const wave = Array.from({ length: WAVE_BARS }, (_, i) => `<span style="width:3px;height:12px;border-radius:2px;background:${dark ? "#fff" : BLUE};animation:m3wave .8s ${i * WAVE_STAGGER_MS}ms cubic-bezier(.4,0,.2,1) infinite"></span>`).join("");
  return `<div style="position:relative;width:max-content;max-width:240px;padding:10px 12px;border-radius:12px;background:${dark ? INK : "#fff"};color:${dark ? "#F1F5F9" : INK};box-shadow:0 14px 30px -12px rgba(1,13,29,.45);font:13px/1.45 'Alliance No.2',system-ui;animation:m3bub .22s cubic-bezier(0,0,.2,1)">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:${b.text ? 4 : 0}px"><span style="display:flex;align-items:center;gap:2px;height:12px">${wave}</span><span style="font-size:11px;letter-spacing:.015em;color:${dark ? "#B8C7D9" : "#64748A"}">${esc(b.who)}</span></div>
      ${b.text ? `<div style="text-wrap:pretty">${esc(b.text)}</div>` : ""}
      <span style="position:absolute;left:50%;bottom:-6px;width:12px;height:12px;margin-left:-6px;transform:rotate(45deg);background:${dark ? INK : "#fff"}"></span></div>`;
}

/**
 * Expanding ring marker used for dispatch pulses.
 *
 * Returns:
 *   The zero-size anchor element.
 */
export function pulseEl(): HTMLDivElement {
  const m = document.createElement("div");
  m.style.cssText = "position:relative;width:0;height:0;pointer-events:none";
  m.innerHTML = `<span style="position:absolute;left:-16px;top:-16px;width:32px;height:32px;border-radius:50%;border:2px solid ${BLUE};animation:m3ring 1.6s cubic-bezier(0,0,.2,1) 2"></span><span style="position:absolute;left:-4px;top:-4px;width:8px;height:8px;border-radius:50%;background:${BLUE}"></span>`;
  return m;
}
