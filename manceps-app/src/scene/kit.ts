// Geometry and math helpers for the hero scene.
import * as THREE from "three";
import { RoundedBoxGeometry } from "three/examples/jsm/geometries/RoundedBoxGeometry.js";
import { TessellateModifier } from "three/examples/jsm/modifiers/TessellateModifier.js";
import { mergeVertices } from "three/examples/jsm/utils/BufferGeometryUtils.js";

export type P2 = [number, number];
export type Warp = (p: THREE.Vector3) => void;

/** Corner radii below this are built as plain boxes. */
const MIN_RADIUS = 0.002;
const TESSELLATE_ITERATIONS = 10;

export const clamp = (v: number, a: number, b: number): number => Math.max(a, Math.min(b, v));

export const ease = {
  outCubic: (t: number): number => 1 - Math.pow(1 - t, 3),
  inOut: (t: number): number => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2),
  outBack: (t: number, s = 1.4): number => 1 + (s + 1) * Math.pow(t - 1, 3) + s * Math.pow(t - 1, 2),
};

/**
 * Seeded pseudo-random generator (mulberry32).
 *
 * Args:
 *   seed: Integer seed.
 *
 * Returns:
 *   A function yielding floats in [0, 1).
 */
export function rng(seed: number): () => number {
  let s = seed;
  return () => {
    s |= 0; s = (s + 0x6d2b79f5) | 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * Add a mesh to a parent at a position.
 *
 * Args:
 *   geo: Geometry.
 *   mat: Material or material list.
 *   x: X position.
 *   y: Y position.
 *   z: Z position.
 *   parent: Object to attach to.
 *
 * Returns:
 *   The mesh.
 */
export function mesh(geo: THREE.BufferGeometry, mat: THREE.Material | THREE.Material[], x = 0, y = 0, z = 0, parent?: THREE.Object3D): THREE.Mesh {
  const m = new THREE.Mesh(geo, mat);
  m.position.set(x, y, z);
  parent?.add(m);
  return m;
}

/**
 * Axis-aligned box geometry between two corners, optionally rounded.
 *
 * Returns:
 *   Geometry already translated to the box center.
 */
export function gBox(x0: number, x1: number, y0: number, y1: number, z0: number, z1: number, r = 0): THREE.BufferGeometry {
  const w = x1 - x0, h = y1 - y0, d = z1 - z0, rr = Math.min(r, w / 2 - 1e-3, h / 2 - 1e-3, d / 2 - 1e-3);
  const g = rr > MIN_RADIUS ? new RoundedBoxGeometry(w, h, d, 2, rr) : new THREE.BoxGeometry(w, h, d);
  return g.translate((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2);
}

/**
 * Box mesh between two corners added to a parent.
 *
 * Returns:
 *   The mesh.
 */
export function bx(parent: THREE.Object3D, mat: THREE.Material, x0: number, x1: number, y0: number, y1: number, z0: number, z1: number, r = 0): THREE.Mesh {
  const w = x1 - x0, h = y1 - y0, d = z1 - z0, rr = Math.min(r, w / 2 - 1e-3, h / 2 - 1e-3, d / 2 - 1e-3);
  const g = rr > MIN_RADIUS ? new RoundedBoxGeometry(w, h, d, 2, rr) : new THREE.BoxGeometry(w, h, d);
  return mesh(g, mat, (x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2, parent);
}

export interface WarpOpts {
  halfW: number;
  frontR: number;
  frontK: number;
  bow: number;
  bowR: number;
  y0: number;
  y1: number;
  taper: number;
}

/**
 * Build the cab body warp: pinches the nose, tapers the roof and bows the front.
 *
 * Args:
 *   o: Warp parameters.
 *
 * Returns:
 *   A function that moves a vertex in place.
 */
export function makeWarp(o: WarpOpts): Warp {
  return (p) => {
    let x = p.x, z = p.z, f = 1;
    const y = p.y;
    if (x < o.frontR) { const u = (o.frontR - Math.max(x, -0.2)) / o.frontR; f *= 1 - o.frontK * u * u; }
    if (o.taper && y > o.y0) f *= 1 - o.taper * Math.min(1, (y - o.y0) / (o.y1 - o.y0));
    z *= f;
    if (o.bow && x < o.bowR) { const s = z / o.halfW; x += o.bow * s * s * (1 - Math.max(0, x) / o.bowR); }
    p.x = x; p.z = z;
  };
}

/**
 * Tessellate a geometry and apply a warp to every vertex.
 *
 * Args:
 *   source: Geometry to shape.
 *   warp: Vertex warp.
 *   tess: Max edge length after tessellation.
 *   smooth: Merge vertices for smooth shading.
 *
 * Returns:
 *   The warped geometry with fresh normals.
 */
export function shapeUp(source: THREE.BufferGeometry, warp: Warp, tess = 0.1, smooth = false): THREE.BufferGeometry {
  let geo = source.index ? source.toNonIndexed() : source;
  if (!geo.attributes.normal) geo.computeVertexNormals();
  geo = new TessellateModifier(tess, TESSELLATE_ITERATIONS).modify(geo);
  const p = geo.attributes.position as THREE.BufferAttribute, v = new THREE.Vector3();
  for (let i = 0; i < p.count; i++) { v.fromBufferAttribute(p, i); warp(v); p.setXYZ(i, v.x, v.y, v.z); }
  if (smooth) { geo.deleteAttribute("normal"); geo.deleteAttribute("uv"); geo = mergeVertices(geo, 1e-4); }
  geo.computeVertexNormals();
  return geo;
}

/** Warped mesh added to a parent. */
export function part(parent: THREE.Object3D, geo: THREE.BufferGeometry, mat: THREE.Material, warp: Warp, tess = 0.1, smooth = false): THREE.Mesh {
  return mesh(shapeUp(geo, warp, tess, smooth), mat, 0, 0, 0, parent);
}

/** Rounded-rectangle 2D shape centered on the origin. */
export function rrShape(w: number, h: number, radius: number): THREE.Shape {
  const s = new THREE.Shape(), x = -w / 2, y = -h / 2, r = Math.min(radius, w / 2, h / 2);
  s.moveTo(x + r, y); s.lineTo(x + w - r, y); s.quadraticCurveTo(x + w, y, x + w, y + r); s.lineTo(x + w, y + h - r);
  s.quadraticCurveTo(x + w, y + h, x + w - r, y + h); s.lineTo(x + r, y + h); s.quadraticCurveTo(x, y + h, x, y + h - r);
  s.lineTo(x, y + r); s.quadraticCurveTo(x, y, x + r, y);
  return s;
}

/**
 * Flat rounded panel spanning the segment p1→p2 in the side profile, facing outward.
 *
 * Args:
 *   p1: Start point (x, y).
 *   p2: End point (x, y).
 *   width: Panel width across the cab.
 *   rad: Corner radius.
 *   off: Offset along the profile normal.
 *   zc: Lateral center.
 *   pad: Extra length at both ends.
 *
 * Returns:
 *   Positioned panel geometry.
 */
export function gPanel(p1: P2, p2: P2, width: number, rad: number, off: number, zc = 0, pad = 0): THREE.BufferGeometry {
  const dx = p2[0] - p1[0], dy = p2[1] - p1[1], Ln = Math.hypot(dx, dy), ux = dx / Ln, uy = dy / Ln, nx = -uy, ny = ux;
  const geo = new THREE.ShapeGeometry(rrShape(Ln + 2 * pad, width, rad), 6);
  const m = new THREE.Matrix4().makeBasis(new THREE.Vector3(ux, uy, 0), new THREE.Vector3(0, 0, -1), new THREE.Vector3(nx, ny, 0));
  m.setPosition((p1[0] + p2[0]) / 2 + nx * off, (p1[1] + p2[1]) / 2 + ny * off, zc);
  return geo.applyMatrix4(m);
}

/** Flat polygon in the side plane at depth z. */
export const gSide = (pts: P2[], z: number): THREE.BufferGeometry =>
  new THREE.ShapeGeometry(new THREE.Shape(pts.map((p) => new THREE.Vector2(p[0], p[1])))).translate(0, 0, z);

/** Ring segment trimming a wheel arch. */
export const gArchTrim = (ax: number, ay: number, r0: number, r1: number, da: number, z: number): THREE.BufferGeometry =>
  new THREE.RingGeometry(r0, r1, 40, 1, da, Math.PI - 2 * da).translate(ax, ay, z);

/**
 * Extrude a side profile across the cab width with a beveled edge.
 *
 * Returns:
 *   Geometry centered on z = 0.
 */
export function extrudeProfile(shape: THREE.Shape, width: number, bevel: number, bevelSize: number, segs = 4): THREE.BufferGeometry {
  const depth = width - 2 * bevel;
  const g = new THREE.ExtrudeGeometry(shape, { depth, bevelEnabled: true, bevelThickness: bevel, bevelSize, bevelSegments: segs, curveSegments: 28 });
  g.translate(0, 0, -depth / 2);
  return g;
}

/**
 * Texture drawn on a 2D canvas.
 *
 * Args:
 *   w: Width in px.
 *   h: Height in px.
 *   draw: Painter.
 *
 * Returns:
 *   An sRGB canvas texture.
 */
export function canvasTex(w: number, h: number, draw: (ctx: CanvasRenderingContext2D, w: number, h: number) => void): THREE.CanvasTexture {
  const c = document.createElement("canvas");
  c.width = w; c.height = h;
  const ctx = c.getContext("2d");
  if (!ctx) throw new Error("2D canvas context unavailable");
  draw(ctx, w, h);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 8;
  return t;
}

/** Sprinkle random specks for a paper texture. */
export function noise(ctx: CanvasRenderingContext2D, w: number, h: number, n: number, a: number, A: string, B: string): void {
  for (let i = 0; i < n; i++) {
    ctx.fillStyle = Math.random() < 0.5 ? A : B;
    ctx.globalAlpha = Math.random() * a;
    ctx.fillRect(Math.random() * w, Math.random() * h, 1 + Math.random() * 2, 1 + Math.random() * 2);
  }
  ctx.globalAlpha = 1;
}

export { RoundedBoxGeometry };
