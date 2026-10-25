// Boxes that fly into the trailer and pack themselves.
import * as THREE from "three";
import { clamp, ease, rng } from "./kit";
import { BOX_GEO } from "./materials";

type V3 = [number, number, number];

interface Volume {
  min: THREE.Vector3;
  max: THREE.Vector3;
}

export interface CargoOpts {
  seed: number;
  minS: V3;
  maxS: V3;
  /** Seconds over which boxes start flying. */
  dur: number;
  /** [min, extra] flight time per box. */
  flight: [number, number];
}

interface Item {
  size: THREE.Vector3;
  target: THREE.Vector3;
  start: THREE.Vector3;
  q0: THREE.Quaternion;
  r: number;
  key: number;
  flight: number;
  delay: number;
  tone: number;
}

const CUT_RATIOS = [0.5, 0.5, 0.5, 1 / 3, 2 / 3, 0.4, 0.6, 0.25, 0.75];
const FORCE_RANDOM_AXIS = 0.25;
const OPTIONAL_SPLIT = 0.42;
const AXES = [0, 1, 2] as const;

/** Recursively split a volume into box-sized cells. */
function pack(min: THREE.Vector3, max: THREE.Vector3, minS: V3, maxS: V3, R: () => number, out: Volume[]): void {
  const s: V3 = [max.x - min.x, max.y - min.y, max.z - min.z];
  let axis = -1;
  const must = AXES.filter((a) => s[a] > maxS[a] && s[a] >= 2 * minS[a]);
  if (must.length) {
    axis = must.reduce((a, b) => (s[a] / maxS[a] > s[b] / maxS[b] ? a : b));
    if (R() < FORCE_RANDOM_AXIS) axis = must[Math.floor(R() * must.length)] ?? axis;
  } else {
    const can = AXES.filter((a) => s[a] >= 2 * minS[a]);
    if (can.length && R() < OPTIONAL_SPLIT) axis = can[Math.floor(R() * can.length)] ?? -1;
  }
  if (axis < 0) { out.push({ min: min.clone(), max: max.clone() }); return; }
  const ax = axis as 0 | 1 | 2;
  const cut = clamp(s[ax] * (CUT_RATIOS[Math.floor(R() * CUT_RATIOS.length)] ?? 0.5), minS[ax], s[ax] - minS[ax]);
  const m1 = max.clone(); m1.setComponent(ax, min.getComponent(ax) + cut);
  const m2 = min.clone(); m2.setComponent(ax, min.getComponent(ax) + cut);
  pack(min, m1, minS, maxS, R, out);
  pack(m2, max, minS, maxS, R, out);
}

function makeItem(b: Volume, vol: Volume, o: CargoOpts, R: () => number): Item {
  const size = b.max.clone().sub(b.min), target = b.min.clone().add(b.max).multiplyScalar(0.5);
  const e = new THREE.Euler((R() - 0.5) * 2.6, (R() - 0.5) * 2.6, (R() - 0.5) * 2.6);
  const r = R();
  const start = new THREE.Vector3(
    Math.min(vol.max.x + 1.6, target.x + 2.2 * (0.5 + R() * 1.1)),
    clamp(target.y + (R() - 0.3) * 1.1, vol.min.y + size.y / 2, vol.max.y - size.y / 2),
    target.z + (R() - 0.3) * 0.9,
  );
  const key = -(target.x - vol.min.x) / (vol.max.x - vol.min.x) + (R() - 0.5) * 0.06 + (target.y - vol.min.y) * 0.006;
  return { size, target, start, q0: new THREE.Quaternion().setFromEuler(e), r, key, flight: o.flight[0] + R() * o.flight[1], tone: 0.74 + R() * 0.16, delay: 0 };
}

/** Instanced cargo that animates from scattered to packed. */
export class Cargo {
  readonly mesh: THREE.InstancedMesh;
  private items: Item[];
  private d = new THREE.Object3D();
  private I = new THREE.Quaternion();

  /**
   * Build the cargo inside a trailer volume.
   *
   * Args:
   *   parent: Object the cargo is attached to.
   *   vol: Trailer interior volume.
   *   mat: Box material.
   *   o: Packing and timing options.
   */
  constructor(parent: THREE.Object3D, vol: Volume, mat: THREE.Material, o: CargoOpts) {
    const R = rng(o.seed), raw: Volume[] = [];
    pack(vol.min, vol.max, o.minS, o.maxS, R, raw);
    this.items = raw.map((b) => makeItem(b, vol, o, R)).sort((a, b) => a.key - b.key);
    const n = this.items.length;
    this.items.forEach((it, i) => { it.delay = (i / n) * o.dur + it.r * 0.06; });
    this.mesh = new THREE.InstancedMesh(BOX_GEO, mat, n);
    this.mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    const col = new THREE.Color();
    this.items.forEach((it, i) => { col.setRGB(it.tone, it.tone * 0.985, it.tone * 0.96); this.mesh.setColorAt(i, col); });
    this.mesh.frustumCulled = false;
    this.mesh.castShadow = true;
    parent.add(this.mesh);
  }

  /**
   * Pose every box for a time.
   *
   * Args:
   *   t: Seconds since loading started.
   *
   * Returns:
   *   Fraction of boxes in place.
   */
  update(t: number): number {
    const d = this.d;
    let done = 0;
    this.items.forEach((it, i) => {
      const u = clamp((t - it.delay) / it.flight, 0, 1);
      if (u <= 0) { d.scale.setScalar(0); d.position.copy(it.target); }
      else {
        d.position.lerpVectors(it.start, it.target, ease.outCubic(u));
        d.position.y += Math.sin(Math.PI * Math.min(1, u * 1.1)) * 0.25 * it.size.y;
        d.quaternion.copy(it.q0).slerp(this.I, clamp(ease.outBack(Math.min(1, u * 1.05), 1.2), 0, 1.08));
        const sc = Math.min(1, u * 5);
        d.scale.set(Math.max(0.001, it.size.x - 0.012) * sc, Math.max(0.001, it.size.y - 0.012) * sc, Math.max(0.001, it.size.z - 0.012) * sc);
      }
      if (u >= 1) { d.quaternion.identity(); done++; }
      d.updateMatrix();
      this.mesh.setMatrixAt(i, d.matrix);
    });
    this.mesh.instanceMatrix.needsUpdate = true;
    return done / this.items.length;
  }
}
