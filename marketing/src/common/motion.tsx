import type { CSSProperties, ReactNode } from "react";
import { Easing, interpolate, useCurrentFrame } from "remotion";
import { EASE_IN_OUT, EASE_OUT, FONT } from "./theme";

const easeOut = Easing.bezier(...EASE_OUT);
const easeInOut = Easing.bezier(...EASE_IN_OUT);
const WORD_IN_FRAMES = 16;
const WORD_RISE_PX = 28;
const WORD_BLUR_PX = 10;

/**
 * Eased 0..1 progress between two frames.
 *
 * Args:
 *   frame: Current frame.
 *   from: Start frame.
 *   to: End frame.
 *   smooth: Use ease-in-out instead of ease-out.
 *
 * Returns:
 *   Clamped eased progress.
 */
export function prog(frame: number, from: number, to: number, smooth = false): number {
  return interpolate(frame, [from, to], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: smooth ? easeInOut : easeOut });
}

/**
 * Linear map of frame through keyframes with ease-in-out per segment.
 *
 * Args:
 *   frame: Current frame.
 *   at: Keyframe frames (ascending).
 *   values: Values at each keyframe.
 *
 * Returns:
 *   Interpolated value, clamped at the ends.
 */
export function keys(frame: number, at: number[], values: number[]): number {
  return interpolate(frame, at, values, { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: easeInOut });
}

export interface WordsProps {
  text: string;
  /** Frame the first word starts appearing (relative to the parent Sequence). */
  at: number;
  /** Frames between words. */
  step?: number;
  /** Frame the whole line starts fading out; omit to keep it. */
  out?: number;
  size: number;
  color: string;
  style?: CSSProperties;
  /** Words that should be painted in the accent color. */
  accent?: { words: string[]; color: string };
}

/** A headline whose words rise out of a blur one after another. */
export function Words({ text, at, step = 6, out, size, color, style, accent }: WordsProps): JSX.Element {
  const frame = useCurrentFrame();
  const fade = out === undefined ? 1 : 1 - prog(frame, out, out + 12);
  const drift = out === undefined ? 0 : -18 * prog(frame, out, out + 12);
  return (
    <div style={{ fontFamily: FONT, fontSize: size, color, letterSpacing: "-0.035em", lineHeight: 1.04, whiteSpace: "pre", opacity: fade, transform: `translateY(${drift}px)`, ...style }}>
      {text.split(" ").map((w, i) => {
        const p = prog(frame, at + i * step, at + i * step + WORD_IN_FRAMES);
        const tint = accent && accent.words.includes(w) ? accent.color : undefined;
        return (
          <span key={i} style={{ display: "inline-block", opacity: p, transform: `translateY(${(1 - p) * WORD_RISE_PX}px)`, filter: `blur(${(1 - p) * WORD_BLUR_PX}px)`, color: tint }}>
            {w}
            {i < text.split(" ").length - 1 ? " " : ""}
          </span>
        );
      })}
    </div>
  );
}

/** Full-frame absolutely positioned layer. */
export function Layer({ children, style }: { children?: ReactNode; style?: CSSProperties }): JSX.Element {
  return <div style={{ position: "absolute", inset: 0, ...style }}>{children}</div>;
}

/** Centers its children in the frame. */
export function Center({ children, style }: { children?: ReactNode; style?: CSSProperties }): JSX.Element {
  return <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", ...style }}>{children}</div>;
}

export { easeInOut, easeOut };
