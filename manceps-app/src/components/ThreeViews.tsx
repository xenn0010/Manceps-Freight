import { useEffect, useRef, type CSSProperties } from "react";
import { AgentFace } from "../scene/agentFace";
import { HeroScene } from "../scene/heroScene";

const FILL: CSSProperties = { position: "absolute", inset: 0 };

/**
 * The landing hero film.
 *
 * Args:
 *   onPhase: Called with the film phase (0 loading, 1 dispatched, 2 in transit, 3 agent).
 */
export function HeroFilm({ onPhase }: { onPhase: (phase: number) => void }): JSX.Element {
  const host = useRef<HTMLDivElement>(null);
  const cb = useRef(onPhase);
  cb.current = onPhase;
  useEffect(() => {
    if (!host.current) return;
    const s = new HeroScene(host.current, (p) => cb.current(p));
    return () => s.destroy();
  }, []);
  return <div ref={host} style={FILL} />;
}

/**
 * A 3D agent face that follows the cursor.
 *
 * Args:
 *   src: Photo URL.
 */
export function AgentFaceView({ src }: { src: string }): JSX.Element {
  const host = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!host.current) return;
    const f = new AgentFace(host.current, src);
    return () => f.destroy();
  }, [src]);
  return <div ref={host} style={FILL} />;
}
