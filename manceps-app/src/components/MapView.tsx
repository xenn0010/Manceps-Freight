import { useEffect, useRef } from "react";
import { pick } from "../actions";
import { MancepsMap } from "../map/engine";
import { getMap, setMap } from "../map/registry";
import { useAppState } from "../store";

/** Full-screen 3D dispatch map; registers itself so actions can drive it, and draws the live fleet. */
export function MapView(): JSX.Element {
  const host = useRef<HTMLDivElement>(null);
  const trucks = useAppState().trucks;
  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const m = new MancepsMap(el, (id) => pick(id));
    setMap(m);
    return () => { setMap(null); m.destroy(); };
  }, []);
  useEffect(() => {
    getMap()?.setFleet(trucks.map((t) => ({ id: t.id, unit: t.unit })));
  }, [trucks]);
  return <div ref={host} style={{ position: "absolute", inset: 0, zIndex: 0, isolation: "isolate" }} />;
}
