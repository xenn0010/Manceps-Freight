import type { LngLat } from "../data";
import routesJson from "./routes.json";

export type RouteId = "R-L101-RET" | "R-O1-EMPTY-PU" | "R-O1-LOADED" | "R-O1-EMPTY-SF" | "R-L103" | "R-L201" | "R-L301";
export type Routes = Record<RouteId, LngLat[]>;

export const ROUTES = routesJson as unknown as Routes;

export const BLUE = "#2272AD";
export const INK = "#010D1D";

/** Default camera: all of California, pitched. */
export const HOME = { center: [-120.3, 36.4] as LngLat, zoom: 5.7, pitch: 52, bearing: -18 };

/** A truck the map can draw; trucks without a position are not placed. */
export interface TruckSpec {
  id: string;
  unit: string;
  park?: LngLat;
  parkHead?: number;
  route?: RouteId;
  from?: number;
  to?: number;
  /** Seconds to drive from `from` to `to`. */
  dur?: number;
}

/** Named checkpoints along each truck's route, as [label, fraction of route]. */
export const CHECKPOINTS: Partial<Record<string, [string, number][]>> = {
  "T-101": [["Pickup · Commerce", 0], ["Grapevine", 0.18], ["Fuel · Kettleman City", 0.45], ["Weigh station · Los Banos", 0.72], ["Delivery · San Francisco", 1]],
  "T-102": [["Pickup · Fresno", 0], ["Fuel · Merced", 0.38], ["Weigh station · Turlock", 0.62], ["Delivery · Stockton", 1]],
  "T-103": [["Pickup · Sacramento", 0], ["Davis", 0.25], ["Toll · Carquinez Bridge", 0.7], ["Delivery · Oakland", 1]],
};

export const CITIES: [string, LngLat][] = [
  ["San Francisco", [-122.4194, 37.7749]],
  ["Sacramento", [-121.4944, 38.5816]],
  ["Fresno", [-119.7871, 36.7378]],
  ["Los Angeles", [-118.2437, 34.0522]],
  ["San Jose", [-121.8863, 37.3382]],
  ["Stockton", [-121.2908, 37.9577]],
];

/** Fraction tolerance when deciding a checkpoint is passed. */
export const CHECK_EPS = 0.002;

const cumDist = new WeakMap<LngLat[], number[]>();

/**
 * Point at a fraction of a polyline's planar length.
 *
 * Args:
 *   coords: Polyline vertices.
 *   f: Fraction along the line, clamped to [0, 1].
 *
 * Returns:
 *   The interpolated [lng, lat].
 */
export function along(coords: LngLat[], f: number): LngLat {
  const first = coords[0];
  if (!first) return [0, 0];
  if (coords.length < 2) return first;
  let D = cumDist.get(coords);
  if (!D) {
    D = [0];
    for (let i = 1; i < coords.length; i++) {
      const a = coords[i - 1] as LngLat, b = coords[i] as LngLat;
      D.push((D[i - 1] as number) + Math.hypot(b[0] - a[0], b[1] - a[1]));
    }
    cumDist.set(coords, D);
  }
  const L = (D[D.length - 1] as number) * Math.max(0, Math.min(1, f));
  let i = 1;
  while (i < D.length - 1 && (D[i] as number) < L) i++;
  const d0 = D[i - 1] as number, d1 = D[i] as number;
  const t = (L - d0) / (d1 - d0 || 1), a = coords[i - 1] as LngLat, b = coords[i] as LngLat;
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
}

/** Minutes per full route used for checkpoint ETAs. */
const ROUTE_MINUTES: Partial<Record<string, number>> = { "T-102": 190, "T-103": 120 };
const DEFAULT_ROUTE_MINUTES = 420;

/**
 * Minutes until a checkpoint, never less than one.
 *
 * Args:
 *   id: Truck.
 *   f: Checkpoint fraction.
 *   at: Truck's current fraction.
 *
 * Returns:
 *   Whole minutes until the truck reaches f.
 */
export function minutesTo(id: string, f: number, at: number): number {
  return Math.max(1, Math.round((f - at) * (ROUTE_MINUTES[id] ?? DEFAULT_ROUTE_MINUTES)));
}
