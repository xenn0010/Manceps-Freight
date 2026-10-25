// Ground, roads, warehouse dock, city blocks, traffic and dock workers.
import * as THREE from "three";
import { bx, mesh, rng } from "./kit";
import { BOX_GEO, type Materials } from "./materials";

export interface Car {
  g: THREE.Group;
  axis: "x" | "z";
  lane: number;
  x: number;
  dir: 1 | -1;
  speed: number;
  off: number;
}

export interface Person {
  g: THREE.Group;
  legs: THREE.Group[];
  arms: THREE.Group[];
  carry: boolean;
  still: boolean;
  path: [[number, number], [number, number]];
  at: [number, number];
  face: number;
  speed: number;
  phase: number;
}

const MAX_DASHES = 120;
const MAX_BLOCKS = 200;
const CROSS_EVERY = 46;
const CAR_COLORS = [0xffffff, 0x0d1424, 0x2f7cff, 0xf2f5f9, 0x1a2436, 0x6aa8ff];
const SKINS = [0xc89b7b, 0x8d5a3b, 0xe0b896, 0x5e3b27, 0xd4a483];

const flat = (geo: THREE.BufferGeometry, mat: THREE.Material, x: number, y: number, z: number, scene: THREE.Object3D): THREE.Mesh => {
  const m = mesh(geo, mat, x, y, z, scene);
  m.rotation.x = -Math.PI / 2;
  return m;
};

function fadeTexture(): THREE.CanvasTexture {
  const c = document.createElement("canvas");
  c.width = c.height = 256;
  const x = c.getContext("2d");
  if (!x) throw new Error("2D canvas context unavailable");
  const g = x.createRadialGradient(128, 128, 0, 128, 128, 128);
  g.addColorStop(0, "#fff"); g.addColorStop(0.55, "#fff"); g.addColorStop(1, "#000");
  x.fillStyle = g; x.fillRect(0, 0, 256, 256);
  return new THREE.CanvasTexture(c);
}

/**
 * Ground plane, main road with lane markings, and the AI route ribbon.
 *
 * Returns:
 *   The ground mesh (it follows the truck) and the route ribbon.
 */
export function buildGround(scene: THREE.Scene, M: Materials): { ground: THREE.Mesh; route: THREE.Mesh } {
  M.ground.alphaMap = fadeTexture();
  const ground = flat(new THREE.PlaneGeometry(420, 420), M.ground, 0, 0, 0, scene);
  ground.receiveShadow = true;
  flat(new THREE.PlaneGeometry(520, 13), M.road, -250, 0.01, 0, scene).receiveShadow = true;
  flat(new THREE.PlaneGeometry(36, 30), M.road, 0, 0.008, 0, scene).receiveShadow = true;
  const dash = new THREE.InstancedMesh(new THREE.PlaneGeometry(2.4, 0.16), M.lane, MAX_DASHES), d = new THREE.Object3D();
  let n = 0;
  for (let x = -14; x > -500 && n < MAX_DASHES; x -= 6) { d.position.set(x, 0.02, 0); d.rotation.set(-Math.PI / 2, 0, 0); d.updateMatrix(); dash.setMatrixAt(n++, d.matrix); }
  dash.count = n; scene.add(dash);
  for (const z of [-6.2, 6.2, -2.2, 2.2]) flat(new THREE.PlaneGeometry(500, 0.12), M.lane, -262, 0.02, z, scene);
  const routeGeo = new THREE.PlaneGeometry(1, 0.5); routeGeo.translate(-0.5, 0, 0);
  const route = flat(routeGeo, M.route, -2, 0.04, -1.6, scene);
  route.scale.x = 0.001;
  return { ground, route };
}

/**
 * Warehouse with dock doors behind the trailer, plus pallets on the apron.
 *
 * Args:
 *   scene: Scene to add to.
 *   M: Materials.
 *   WX: X of the dock face.
 */
export function buildWarehouse(scene: THREE.Scene, M: Materials, WX: number): void {
  const wh = new THREE.Group(); scene.add(wh);
  bx(wh, M.bldg, WX, WX + 26, 0, 9.5, -16, 16);
  bx(wh, M.bldgDark, WX - 0.02, WX + 26, 9.5, 10, -16.2, 16.2);
  bx(wh, M.dockLip, WX - 1.2, WX, 0, 1.3, -16, 16);
  for (const z of [-9, -4.5, 0, 4.5, 9]) {
    bx(wh, M.door, WX - 0.03, WX, 1.3, 5.2, z - 1.6, z + 1.6);
    bx(wh, M.bumper, WX - 1.35, WX - 1.2, 0.5, 1.2, z - 1.5, z - 1.2); bx(wh, M.bumper, WX - 1.35, WX - 1.2, 0.5, 1.2, z + 1.2, z + 1.5);
    bx(wh, M.bldgDark, WX - 1.2, WX, 5.4, 5.6, z - 1.9, z + 1.9);
  }
  for (const z of [-12.5, 12.5]) bx(wh, M.stripe, WX - 1.22, WX - 1.18, 0, 1.3, z - 0.1, z + 0.1);
  bx(wh, M.bldg, WX + 4, WX + 22, 0, 13, 22, 40);
  bx(wh, M.bldgDark, WX - 30, WX - 12, 0, 6, -40, -24);
  const R = rng(3), palletGeo = new THREE.BoxGeometry(1.2, 0.14, 1);
  for (const [px, pz] of [[WX - 3, 10.5], [WX - 3, 12], [WX - 4.6, 10.8], [WX - 3, -6.5], [WX - 4.4, -6.8], [WX - 2.6, -10.8]] as [number, number][]) {
    const p = mesh(palletGeo, M.wood, px, 0.07, pz, wh); p.castShadow = true; p.receiveShadow = true;
    const h = 2 + Math.floor(R() * 3);
    for (let y = 0; y < h; y++) for (const ox of [-0.3, 0.3]) for (const oz of [-0.25, 0.25]) {
      if (R() < 0.15 && y === h - 1) continue;
      const b = mesh(BOX_GEO, M.box, px + ox, 0.14 + 0.26 + y * 0.5, pz + oz, wh);
      b.scale.set(0.58, 0.5, 0.48); b.castShadow = true; b.rotation.y = (R() - 0.5) * 0.08;
    }
  }
}

/**
 * City blocks along the route and cross streets for the bird's-eye shot.
 *
 * Returns:
 *   X positions of the cross streets.
 */
export function buildCity(scene: THREE.Scene, M: Materials): number[] {
  const blocks = new THREE.InstancedMesh(new THREE.BoxGeometry(1, 1, 1), M.bldg, MAX_BLOCKS), d = new THREE.Object3D(), RB = rng(21);
  let n = 0;
  for (let x = -24; x > -420 && n < MAX_BLOCKS; x -= 7 + RB() * 9) for (const side of [-1, 1]) {
    if (RB() < 0.3 || n >= MAX_BLOCKS) continue;
    const w = 5 + RB() * 12, dd = 5 + RB() * 14, h = 2 + RB() * 9, z = side * (10 + dd / 2 + RB() * 18);
    d.position.set(x, h / 2, z); d.rotation.set(0, 0, 0); d.scale.set(w, h, dd); d.updateMatrix(); blocks.setMatrixAt(n++, d.matrix);
  }
  blocks.count = n; blocks.castShadow = true; blocks.receiveShadow = true; scene.add(blocks);
  const crossXs: number[] = [];
  for (let x = -40; x > -480; x -= CROSS_EVERY) crossXs.push(x);
  crossXs.forEach((x) => {
    flat(new THREE.PlaneGeometry(6, 260), M.road, x, 0.012, 0, scene).receiveShadow = true;
    for (let z = -120; z < 120; z += 6) if (Math.abs(z) >= 5) flat(new THREE.PlaneGeometry(0.14, 2.2), M.lane, x, 0.022, z, scene);
  });
  return crossXs;
}

/**
 * Cars and vans on the main road and the cross streets.
 *
 * Returns:
 *   Every car with its lane, direction, speed and phase offset.
 */
export function buildTraffic(scene: THREE.Scene, M: Materials, crossXs: number[]): Car[] {
  const carMats = CAR_COLORS.map((c) => new THREE.MeshPhysicalMaterial({ color: c, metalness: 0.5, roughness: 0.25, clearcoat: 1 }));
  const glassDark = new THREE.MeshStandardMaterial({ color: 0x0a1220, roughness: 0.2, metalness: 0.6 });
  const tail = new THREE.MeshStandardMaterial({ color: 0x400000, emissive: 0xff3030, emissiveIntensity: 1.6 });
  const RC = rng(77), wheelGeo = new THREE.CylinderGeometry(0.34, 0.34, 0.24, 14);
  const car = (van: boolean): THREE.Group => {
    const g = new THREE.Group(), m = carMats[Math.floor(RC() * carMats.length)] as THREE.Material;
    const L = van ? 5.2 : 4.4, H = van ? 1.9 : 1.25;
    bx(g, m, -L / 2, L / 2, 0.32, 0.32 + H * 0.6, -0.9, 0.9, 0.18);
    bx(g, glassDark, -L * 0.28, L * 0.22, 0.32 + H * 0.58, 0.32 + H, -0.8, 0.8, 0.2);
    bx(g, tail, L / 2 - 0.04, L / 2 + 0.02, 0.55, 0.7, -0.8, -0.5); bx(g, tail, L / 2 - 0.04, L / 2 + 0.02, 0.55, 0.7, 0.5, 0.8);
    for (const xx of [-L * 0.32, L * 0.32]) for (const zz of [-0.86, 0.86]) mesh(wheelGeo, M.tire, xx, 0.34, zz, g).rotation.x = Math.PI / 2;
    g.traverse((o) => { if (o instanceof THREE.Mesh) o.castShadow = true; });
    scene.add(g);
    return g;
  };
  const cars: Car[] = [];
  for (let i = 0; i < 16; i++) cars.push({ g: car(RC() < 0.25), axis: "x", lane: 4.3, x: 0, dir: 1, speed: 11 + RC() * 6, off: -RC() * 470 });
  for (let i = 0; i < 9; i++) cars.push({ g: car(RC() < 0.25), axis: "x", lane: -4.3, x: 0, dir: -1, speed: 12 + RC() * 3, off: -60 - RC() * 400 });
  crossXs.forEach((x) => {
    for (let i = 0; i < 3; i++) { const dir = i % 2 ? 1 : -1; cars.push({ g: car(RC() < 0.2), axis: "z", lane: 0, x: x + dir * 1.5, dir, speed: 9 + RC() * 5, off: RC() * 240 - 120 }); }
  });
  return cars;
}

type PersonOpts = Partial<Pick<Person, "carry" | "still" | "path" | "at" | "face" | "speed" | "phase">> & { skin: number; vest: boolean };

function person(scene: THREE.Scene, M: Materials, o: PersonOpts): Person {
  const p = new THREE.Group(), skin = new THREE.MeshStandardMaterial({ color: o.skin, roughness: 0.7 });
  const capsule = (r: number, l: number): THREE.CapsuleGeometry => new THREE.CapsuleGeometry(r, l, 6, 12);
  mesh(capsule(0.2, 0.5), o.vest ? M.vest : M.shirt, 0, 1.22, 0, p).scale.z = 0.75;
  mesh(new THREE.SphereGeometry(0.15, 20, 14), skin, 0, 1.72, 0, p);
  const limb = (y: number, z: number, r: number, l: number, mat: THREE.Material, dy: number): THREE.Group => {
    const pivot = new THREE.Group(); pivot.position.set(0, y, z); p.add(pivot); mesh(capsule(r, l), mat, 0, dy, 0, pivot); return pivot;
  };
  const legs = [-1, 1].map((sx) => limb(0.86, sx * 0.1, 0.08, 0.62, M.pants, -0.4));
  const arms = [-1, 1].map((sx) => limb(1.42, sx * 0.27, 0.06, 0.5, o.vest ? M.vest : M.shirt, -0.32));
  if (o.carry) mesh(BOX_GEO, M.box, 0.32, 1.15, 0, p).scale.set(0.42, 0.34, 0.5);
  p.traverse((m) => { if (m instanceof THREE.Mesh) m.castShadow = true; });
  scene.add(p);
  return { g: p, legs, arms, carry: !!o.carry, still: !!o.still, path: o.path ?? [[0, 0], [0, 0]], at: o.at ?? [0, 0], face: o.face ?? 0, speed: o.speed ?? 1, phase: o.phase ?? 0 };
}

/**
 * Dock workers: four walking (two carrying boxes) and one who waves the truck off.
 *
 * Returns:
 *   All people; the last one is the watcher.
 */
export function buildPeople(scene: THREE.Scene, M: Materials, WX: number): Person[] {
  const s = (i: number): number => SKINS[i] ?? 0xc89b7b;
  return [
    person(scene, M, { skin: s(0), vest: true, path: [[WX - 2.2, -12], [WX - 2.2, 12]], speed: 1.2, phase: 0 }),
    person(scene, M, { skin: s(1), vest: false, carry: true, path: [[WX - 3.4, 9], [WX - 3.4, 2.4]], speed: 1.0, phase: 0.4 }),
    person(scene, M, { skin: s(2), vest: true, path: [[WX - 5, -9], [WX - 8, -3]], speed: 0.9, phase: 0.2 }),
    person(scene, M, { skin: s(3), vest: false, carry: true, path: [[WX - 3.6, -8], [WX - 3.6, -2.4]], speed: 1.1, phase: 0.7 }),
    person(scene, M, { skin: s(4), vest: true, still: true, at: [WX - 1.6, 8.6], face: Math.PI }),
  ];
}
