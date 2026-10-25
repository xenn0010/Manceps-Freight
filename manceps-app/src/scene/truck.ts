// Detailed tractor-trailer with a see-through trailer for the loading shot.
import * as THREE from "three";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import { Cargo } from "./cargo";
import { bx, extrudeProfile, gArchTrim, gBox, gPanel, gSide, makeWarp, mesh, part, type Warp } from "./kit";
import type { Materials } from "./materials";

/** Cab width in meters. */
const W = 2.36;
const HW = W / 2;
/** Front axle arch: center x/y, radius, and the body line it cuts. */
const AX = 0.95, AY = 0.52, AR = 0.67, BY = 0.6;
const DA = Math.asin((BY - AY) / AR);
const WHEEL_R = 0.52;
/** Trailer: width, front x, rear x, floor y, roof y. */
const TW = 2.5, X0 = 2.6, X1 = 16.3, FY = 1.38, TOP = 4.06;

export interface TruckBuild {
  root: THREE.Group;
  cargo: Cargo;
  wheels: THREE.Mesh[];
  rearX: number;
}

const bothSides = (fn: (sg: 1 | -1) => void): void => { fn(1); fn(-1); };

function wheelGeometry(r: number, w: number, dual: boolean): THREE.BufferGeometry {
  const geos: THREE.BufferGeometry[] = [], mats: number[] = [];
  const push = (src: THREE.BufferGeometry, m: number): void => {
    const g = src.index ? src.toNonIndexed() : src;
    if (!g.attributes.uv) g.setAttribute("uv", new THREE.BufferAttribute(new Float32Array(g.attributes.position!.count * 2), 2));
    geos.push(g); mats.push(m);
  };
  const ri = r * 0.6;
  const prof = [[ri, -w / 2], [r * 0.88, -w / 2], [r * 0.96, -w / 2 + w * 0.06], [r, -w / 2 + w * 0.2], [r, w / 2 - w * 0.2], [r * 0.96, w / 2 - w * 0.06], [r * 0.88, w / 2], [ri, w / 2]].map((p) => new THREE.Vector2(p[0], p[1]));
  const one = (zc: number, face: boolean): void => {
    const t = new THREE.LatheGeometry(prof, 40); t.rotateX(Math.PI / 2); t.translate(0, 0, zc); push(t, 0);
    const barrel = new THREE.CylinderGeometry(ri, ri, w * 0.9, 32, 1, true); barrel.rotateX(Math.PI / 2); barrel.translate(0, 0, zc); push(barrel, 2);
    if (!face) return;
    const fz = zc + w * 0.36;
    const dish = new THREE.LatheGeometry([[0, 0.03], [ri * 0.3, 0.03], [ri * 0.42, 0], [ri * 0.9, -0.02], [ri * 1.02, 0.01], [ri * 1.04, -0.01]].map((p) => new THREE.Vector2(p[0], p[1])), 40);
    dish.rotateX(Math.PI / 2); dish.translate(0, 0, fz); push(dish, 1);
    for (let i = 0; i < 8; i++) { const a = (i / 8) * Math.PI * 2, h = new THREE.CircleGeometry(ri * 0.1, 12); h.translate(Math.cos(a) * ri * 0.66, Math.sin(a) * ri * 0.66, fz - 0.014); push(h, 2); }
    const hub = new THREE.CylinderGeometry(ri * 0.26, ri * 0.3, 0.09, 24); hub.rotateX(Math.PI / 2); hub.translate(0, 0, fz + 0.05); push(hub, 3);
  };
  if (dual) { one(-w / 2 - 0.012, false); one(w / 2 + 0.012, true); } else one(0, true);
  const merged = mergeGeometries(geos, true);
  merged.groups.forEach((gr, i) => { gr.materialIndex = mats[i] ?? 0; });
  return merged;
}

function cabShape(): THREE.Shape {
  const dxA = Math.cos(DA) * AR, s = new THREE.Shape();
  s.moveTo(0.07, BY); s.lineTo(AX - dxA, BY); s.absarc(AX, AY, AR, Math.PI - DA, DA, true);
  s.lineTo(2.32, BY); s.lineTo(2.32, 3.3); s.quadraticCurveTo(2.33, 3.97, 2.1, 3.98); s.lineTo(1.55, 3.98);
  s.bezierCurveTo(1.05, 3.96, 0.66, 3.5, 0.5, 3.27); s.quadraticCurveTo(0.42, 3.13, 0.24, 3.1);
  s.lineTo(0.19, 3.0); s.lineTo(0.075, 2.03); s.quadraticCurveTo(0.035, 1.6, 0.025, 1.15); s.quadraticCurveTo(0.01, 0.72, 0.07, BY);
  return s;
}

function cabFront(g: THREE.Group, M: Materials, warp: Warp): void {
  part(g, extrudeProfile(cabShape(), W, 0.11, 0.085, 5), M.paint, warp, 0.13, true);
  const liner = new THREE.CylinderGeometry(AR - 0.015, AR - 0.015, W - 0.1, 40, 1, true, Math.PI / 2 + DA, Math.PI - 2 * DA);
  liner.rotateX(Math.PI / 2);
  mesh(liner, M.liner, AX, AY, 0, g);
  bothSides((sg) => part(g, gArchTrim(AX, AY, AR - 0.005, AR + 0.055, DA, sg * (HW + 0.006)), M.black, warp, 0.06));
  part(g, gPanel([0.075, 2.03], [0.19, 3.0], W - 0.2, 0.12, 0.088, 0, 0.035), M.black, warp, 0.08);
  part(g, gPanel([0.075, 2.03], [0.19, 3.0], W - 0.3, 0.09, 0.094, 0, -0.01), M.glass, warp, 0.08);
  for (const z of [-0.6, -0.2, 0.2, 0.6]) part(g, gBox(0.28, 0.34, 3.13, 3.18, z - 0.07, z + 0.07, 0.02), M.amberLamp, warp, 0.05);
  part(g, gPanel([0.027, 1.28], [0.06, 1.96], 1.78, 0.06, 0.088), M.black, warp, 0.07);
  for (let i = 0; i < 5; i++) {
    const y = 1.36 + i * 0.12, x = 0.027 + ((y - 1.28) / 0.68) * 0.033;
    part(g, gPanel([x, y], [x + 0.002, y + 0.038], 1.66, 0.015, 0.098), M.aluDark, warp, 0.07);
  }
  part(g, gPanel([0.045, 1.6], [0.048, 1.68], 0.34, 0.03, 0.108), M.chrome, warp, 0.05);
  bothSides((sg) => {
    part(g, gPanel([0.02, 0.84], [0.025, 1.08], 0.64, 0.07, 0.09, sg * 0.72), M.black, warp, 0.05);
    part(g, gPanel([0.02, 0.855], [0.025, 1.065], 0.6, 0.06, 0.096, sg * 0.72), M.headlamp, warp, 0.05);
  });
  part(g, gBox(-0.07, 0.32, 0.48, 0.78, -HW + 0.03, HW - 0.03, 0.05), M.black, warp, 0.08);
}

function cabSide(g: THREE.Group, M: Materials, warp: Warp, sg: 1 | -1): void {
  const z = sg * (HW + 0.004);
  const seam = (x0: number, x1: number, y0: number, y1: number): void => { part(g, gBox(x0, x1, y0, y1, z - 0.003, z + 0.003), M.black, warp, 0.08); };
  seam(0.33, 0.345, 1.27, 2.98); seam(1.4, 1.415, 1.0, 2.98); seam(0.33, 1.415, 1.27, 1.285);
  part(g, gSide([[0.4, 2.06], [1.34, 2.06], [1.34, 2.92], [0.46, 2.98]], z), M.black, warp, 0.08);
  part(g, gSide([[0.44, 2.1], [1.3, 2.1], [1.3, 2.88], [0.49, 2.93]], z + sg * 0.002), M.glass, warp, 0.08);
  part(g, gBox(1.16, 1.3, 1.82, 1.86, z - 0.012, z + 0.012, 0.008), M.chrome, warp, 0.05);
  part(g, gSide([[1.62, 2.45], [2.12, 2.45], [2.12, 2.82], [1.62, 2.82]], z), M.glass, warp, 0.08);
  bx(g, M.paint, 2.32, 2.56, 1.75, 3.96, sg > 0 ? HW - 0.03 : -HW - 0.01, sg > 0 ? HW + 0.01 : -HW + 0.03, 0.01);
  bx(g, M.black, 1.66, 2.3, 0.38, 0.98, sg * HW - 0.07, sg * HW + 0.03 * sg, 0.02);
  for (const y of [0.5, 0.8]) bx(g, M.alu, 1.7, 2.26, y, y + 0.03, sg * (HW + 0.03) - 0.02, sg * (HW + 0.03) + 0.02);
  const mz = sg * (HW + 0.36);
  bx(g, M.black, 0.3, 0.36, 2.86, 2.9, sg > 0 ? HW - 0.05 : mz, sg > 0 ? mz : -HW + 0.05);
  bx(g, M.black, 0.14, 0.3, 2.3, 2.92, mz - 0.09, mz + 0.09, 0.05);
}

function chassis(g: THREE.Group, M: Materials, wheels: THREE.Mesh[]): void {
  bx(g, M.black, 0.5, 6.6, 0.72, 1.02, -0.5, 0.5);
  bx(g, M.alu, 2.45, 3.6, 0.46, 1.06, 0.52, 1.12, 0.2);
  bx(g, M.black, 2.45, 3.6, 0.46, 1.06, -1.12, -0.52, 0.1);
  for (const z of [-1, 1]) bx(g, M.black, 3.72, 6.22, 1.08, 1.14, z * 0.84 - 0.34, z * 0.84 + 0.34, 0.03);
  const mats = [M.tire, M.rim, M.rimDark, M.chrome];
  const fw = wheelGeometry(WHEEL_R, 0.32, false), dw = wheelGeometry(WHEEL_R, 0.27, true);
  const place = (geo: THREE.BufferGeometry, x: number, z: number, flip: boolean): void => {
    const w = new THREE.Mesh(geo, mats);
    w.position.set(x, WHEEL_R, z);
    if (flip) w.rotation.y = Math.PI;
    w.userData.sign = flip ? -1 : 1;
    g.add(w); wheels.push(w);
  };
  place(fw, AX, HW - 0.19, false); place(fw, AX, -(HW - 0.19), true);
  for (const x of [4.3, 5.62]) { place(dw, x, 0.86, false); place(dw, x, -0.86, true); }
  for (const x of [13.75, 15.05]) { place(dw, x, 0.88, false); place(dw, x, -0.88, true); }
}

function trailer(g: THREE.Group, M: Materials): void {
  bx(g, M.black, 3.0, X1 - 0.1, 1.02, 1.26, -0.55, 0.55);
  for (const z of [-1, 1]) { bx(g, M.black, 7.0, 12.6, 0.58, 1.16, z * 1.18 - 0.02, z * 1.18 + 0.02, 0.01); bx(g, M.black, 12.9, 15.95, 1.1, 1.18, z * 0.86 - 0.42, z * 0.86 + 0.42, 0.02); }
  for (const z of [-0.95, 0.95]) bx(g, M.redLamp, X1 - 0.07, X1 - 0.03, 0.82, 0.92, z - 0.18, z + 0.18);
  for (const z of [-0.74, 0.74]) bx(g, M.aluDark, 4.4, 4.5, 0.2, 1.05, z - 0.04, z + 0.04);
  bx(g, M.floorIn, X0, X1, 1.25, FY, -TW / 2, TW / 2);
  bx(g, M.wallIn, X0, X1, FY, TOP - 0.04, -TW / 2, -TW / 2 + 0.05);
  bx(g, M.frostFront, X0, X0 + 0.06, FY, TOP, -TW / 2, TW / 2);
  const roof = bx(g, M.frost, X0, X1, TOP - 0.05, TOP, -TW / 2, TW / 2);
  roof.renderOrder = 3; roof.userData.noShadow = true;
  bx(g, M.alu, X0, X1, 1.2, 1.44, TW / 2 - 0.07, TW / 2 + 0.02, 0.02);
  bx(g, M.alu, X0, X1, TOP - 0.13, TOP + 0.02, TW / 2 - 0.07, TW / 2 + 0.02, 0.02);
  bx(g, M.alu, X0, X1, TOP - 0.13, TOP + 0.02, -TW / 2 - 0.02, -TW / 2 + 0.06, 0.02);
  bx(g, M.alu, X0, X0 + 0.1, FY, TOP, -TW / 2 - 0.02, -TW / 2 + 0.06);
  bx(g, M.glow, X1 - 0.1, X1, 1.22, TOP + 0.02, TW / 2 - 0.1, TW / 2 + 0.02, 0.02);
  bx(g, M.glow, X1 - 0.1, X1, 1.22, TOP + 0.02, -TW / 2 - 0.02, -TW / 2 + 0.1, 0.02);
  bx(g, M.glow, X1 - 0.1, X1, TOP - 0.1, TOP + 0.02, -TW / 2, TW / 2);
}

/**
 * Build the truck, its wheels and the cargo that loads into it.
 *
 * Args:
 *   M: Scene materials.
 *
 * Returns:
 *   Root group, cargo, wheel meshes and the trailer's rear x.
 */
export function buildTruck(M: Materials): TruckBuild {
  const root = new THREE.Group(), g = new THREE.Group(), wheels: THREE.Mesh[] = [];
  root.add(g);
  const warp = makeWarp({ halfW: HW, frontR: 0.7, frontK: 0.1, bow: 0.07, bowR: 0.6, y0: 2.1, y1: 4.0, taper: 0.035 });
  cabFront(g, M, warp);
  bothSides((sg) => cabSide(g, M, warp, sg));
  chassis(g, M, wheels);
  trailer(g, M);
  g.position.x = -(X1 + 0.1) / 2;
  root.traverse((o) => { if (o instanceof THREE.Mesh && !o.userData.noShadow && o.material !== M.frost) o.castShadow = true; });
  const vol = { min: new THREE.Vector3(X0 + 0.1, FY + 0.005, -TW / 2 + 0.07), max: new THREE.Vector3(X1 - 0.14, TOP - 0.07, TW / 2 - 0.05) };
  const cargo = new Cargo(g, vol, M.box, { seed: 11, minS: [0.55, 0.45, 0.5], maxS: [1.5, 1.3, 1.25], dur: 4.2, flight: [0.7, 0.4] });
  return { root, cargo, wheels, rearX: X1 - (X1 + 0.1) / 2 };
}
