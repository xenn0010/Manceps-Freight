import type { CSSProperties, ReactNode } from "react";
import { Img, OffthreadVideo, staticFile } from "remotion";

/** Region of the source screen to show, in CSS pixels of the captured viewport. */
export interface Crop {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface Pose {
  x?: number;
  y?: number;
  z?: number;
  rx?: number;
  ry?: number;
  rz?: number;
  scale?: number;
  opacity?: number;
}

export interface Panel3DProps {
  /** Path under public/, e.g. "screens/map-overview-1920.png" or "recordings/rec-sheet-agent.mp4". */
  src: string;
  /** CSS width of the captured viewport the source represents. */
  sourceWidth?: number;
  sourceHeight?: number;
  crop?: Crop;
  /** Rendered width of the panel in film pixels. */
  width: number;
  pose: Pose;
  radius?: number;
  dark?: boolean;
  reflection?: boolean;
  /** Video start offset in frames, for recordings. */
  startFrom?: number;
  filter?: string;
  style?: CSSProperties;
}

const isVideo = (src: string): boolean => /\.(mp4|webm|mov)$/i.test(src);

function Media({ src, startFrom, w, h }: { src: string; startFrom?: number; w: number; h: number }): JSX.Element {
  const style: CSSProperties = { width: w, height: h, display: "block" };
  return isVideo(src) ? <OffthreadVideo src={staticFile(src)} startFrom={startFrom ?? 0} muted style={style} /> : <Img src={staticFile(src)} style={style} />;
}

/** A crop of a real app capture floating as a glass card in 3D space, with soft shadow and optional reflection. */
export function Panel3D({ src, sourceWidth = 1920, sourceHeight = 1080, crop, width, pose, radius = 18, dark = false, reflection = false, startFrom, filter, style }: Panel3DProps): JSX.Element {
  const c = crop ?? { x: 0, y: 0, w: sourceWidth, h: sourceHeight };
  const k = width / c.w;
  const height = c.h * k;
  const { x = 0, y = 0, z = 0, rx = 0, ry = 0, rz = 0, scale = 1, opacity = 1 } = pose;
  const shadow = dark
    ? "0 0 0 1px rgba(255,255,255,.10), 0 50px 140px -30px rgba(76,155,255,.28), 0 30px 60px -30px rgba(0,0,0,.9)"
    : "0 0 0 1px rgba(1,13,29,.06), 0 70px 140px -40px rgba(1,13,29,.38), 0 24px 48px -24px rgba(1,13,29,.22)";
  const face = (flip: boolean): JSX.Element => (
    <div style={{ width, height, borderRadius: radius, overflow: "hidden", position: "relative", boxShadow: flip ? "none" : shadow, filter, ...(flip ? { transform: "scaleY(-1)", marginTop: 10, opacity: dark ? 0.1 : 0.16, WebkitMaskImage: "linear-gradient(to top, rgba(0,0,0,.9), transparent 38%)", maskImage: "linear-gradient(to top, rgba(0,0,0,.9), transparent 38%)" } : {}) }}>
      <div style={{ position: "absolute", left: -c.x * k, top: -c.y * k }}>
        <Media src={src} startFrom={startFrom} w={sourceWidth * k} h={sourceHeight * k} />
      </div>
      {!flip && <div style={{ position: "absolute", inset: 0, borderRadius: radius, background: "linear-gradient(155deg, rgba(255,255,255,.16), rgba(255,255,255,0) 40%)", pointerEvents: "none" }} />}
    </div>
  );
  return (
    <div style={{ position: "absolute", left: "50%", top: "50%", width, marginLeft: -width / 2, marginTop: -height / 2, transformStyle: "preserve-3d", transform: `translate3d(${x}px, ${y}px, ${z}px) rotateX(${rx}deg) rotateY(${ry}deg) rotateZ(${rz}deg) scale(${scale})`, opacity, ...style }}>
      {face(false)}
      {reflection && face(true)}
    </div>
  );
}

/** Perspective stage that Panel3D children live in. */
export function Stage({ children, perspective = 2200, originY = "50%" }: { children: ReactNode; perspective?: number; originY?: string }): JSX.Element {
  return <div style={{ position: "absolute", inset: 0, perspective, perspectiveOrigin: `50% ${originY}`, transformStyle: "preserve-3d" }}>{children}</div>;
}
