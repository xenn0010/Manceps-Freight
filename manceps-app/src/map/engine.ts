// Pitched MapLibre map with three.js trucks, checkpoints, voice bubbles and dispatch pulses.
import maplibregl, { type CustomLayerInterface, type Map as MLMap, type Marker } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import * as THREE from "three";
import type { LngLat } from "../data";
import { BLUE, CHECK_EPS, CHECKPOINTS, CITIES, HOME, INK, ROUTES, along, type RouteId, type TruckSpec } from "./geo";
import { bubbleHtml, checkEl, cityEl, ensureMapCss, pulseEl, styleCheckEl, styleTruckEl, truckEl, type Bubble, type CheckState } from "./markers";
import { TRUCK_LENGTH_M, buildTruck, type TruckMaterials } from "./truck3d";

const STYLE_URL = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json";
/** Meters per pixel at zoom 0 on the equator for 512px tiles. */
const MPP_Z0 = 78271.517;
/** Heading easing per frame toward the travel direction. */
const HEAD_EASE = 0.08;
/** Look-ahead fraction for heading. */
const HEAD_LOOKAHEAD = 0.004;
const PULSE_MS = 3400;
/** Demo backhaul lines, revealed only when the demo "Needs your yes" booking is approved. */
const BOOKED_ROUTES: RouteId[] = ["R-O1-EMPTY-PU", "R-O1-LOADED"];

interface LiveTruck extends TruckSpec {
  el: HTMLDivElement;
  mk: Marker;
  pos: LngLat;
  head: number;
  prog: number;
  g?: THREE.Group;
}

interface LiveCheck {
  f: number;
  e: HTMLDivElement;
  mk: Marker;
  st: CheckState | "";
}

export interface Progress {
  f: number;
  moving: boolean;
}

/** Imperative controller for the dispatch map. */
export class MancepsMap {
  private map: MLMap;
  private trucks: LiveTruck[] = [];
  private checks: LiveCheck[] = [];
  private checkKey = "";
  private sel: string | null = null;
  private fleet: TruckSpec[] = [];
  private loaded = false;
  private scene: THREE.Scene | null = null;
  private t0 = 0;
  private dead = false;
  private raf = 0;
  private resize: ResizeObserver;

  /**
   * Create the map inside a container.
   *
   * Args:
   *   container: Element the map fills.
   *   onTruck: Called with a truck id when its marker is clicked.
   */
  constructor(container: HTMLElement, private onTruck: (id: string) => void) {
    ensureMapCss();
    this.map = new maplibregl.Map({ container, style: STYLE_URL, ...HOME, attributionControl: { compact: true }, maxPitch: 70, antialias: true });
    this.map.on("load", () => this.onLoad());
    this.resize = new ResizeObserver(() => this.map.resize());
    this.resize.observe(container);
  }

  /** Tear down the map, markers and animation loop. */
  destroy(): void {
    this.dead = true;
    cancelAnimationFrame(this.raf);
    this.resize.disconnect();
    this.map.remove();
  }

  private onLoad(): void {
    const map = this.map;
    map.getStyle().layers.forEach((l) => { if (l.type === "symbol") map.setLayoutProperty(l.id, "visibility", "none"); });
    if (map.getLayer("water")) map.setPaintProperty("water", "fill-color", "#CFE0EE");
    if (map.getLayer("background")) map.setPaintProperty("background", "background-color", "#F4F6F9");
    (Object.keys(ROUTES) as RouteId[]).forEach((id) => this.addRoute(id));
    CITIES.forEach(([n, c]) => new maplibregl.Marker({ element: cityEl(n), anchor: "left", offset: [6, 0] }).setLngLat(c).addTo(map));
    this.loaded = true;
    this.trucks = this.fleet.filter(placeable).map((t) => this.addTruck(t));
    map.addLayer(this.truckLayer());
    this.t0 = performance.now();
    this.tick();
    this.select(this.sel, true);
  }

  private addRoute(id: RouteId): void {
    this.map.addSource(id, { type: "geojson", data: { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: ROUTES[id] } } });
    const layout = { "line-cap": "round", "line-join": "round", visibility: "none" } as const;
    this.map.addLayer({ id: id + "-c", type: "line", source: id, layout, paint: { "line-color": "#FFFFFF", "line-width": 6, "line-opacity": 0.8 } });
    this.map.addLayer({ id, type: "line", source: id, layout, paint: { "line-color": INK, "line-width": 2.5, "line-opacity": 0.35 } });
  }

  private addTruck(t: TruckSpec): LiveTruck {
    const pos = t.park ?? along(ROUTES[t.route as RouteId], t.from ?? 0);
    const el = truckEl(t.unit, () => this.onTruck(t.id));
    const mk = new maplibregl.Marker({ element: el }).setLngLat(pos).addTo(this.map);
    return { ...t, el, mk, pos, head: t.parkHead ?? 0, prog: t.from ?? 0 };
  }

  private truckLayer(): CustomLayerInterface {
    const self = this;
    const camera = new THREE.Camera(), scene = new THREE.Scene();
    const M = new THREE.Matrix4(), S = new THREE.Matrix4(), R = new THREE.Matrix4();
    let renderer: THREE.WebGLRenderer | null = null;
    return {
      id: "trucks3d", type: "custom", renderingMode: "3d",
      onAdd(m: MLMap, gl: WebGLRenderingContext | WebGL2RenderingContext) {
        scene.add(new THREE.HemisphereLight(0xffffff, 0x9fb6cc, 1.6));
        const d = new THREE.DirectionalLight(0xffffff, 1.6); d.position.set(0.4, -0.6, 1); scene.add(d);
        const d2 = new THREE.DirectionalLight(0x8db8ff, 0.6); d2.position.set(-0.6, 0.5, 0.4); scene.add(d2);
        self.scene = scene;
        self.trucks.forEach((t) => self.addModel(t));
        renderer = new THREE.WebGLRenderer({ canvas: m.getCanvas(), context: gl, antialias: true });
        renderer.autoClear = false;
      },
      render(_gl: WebGLRenderingContext | WebGL2RenderingContext, matrix: unknown) {
        if (!renderer) return;
        const mx = (matrix as { defaultProjectionData?: { mainMatrix: ArrayLike<number> } }).defaultProjectionData?.mainMatrix ?? (matrix as ArrayLike<number>);
        const z = self.map.getZoom(), lat = self.map.getCenter().lat;
        const mpp = (MPP_Z0 * Math.cos((lat * Math.PI) / 180)) / Math.pow(2, z);
        self.trucks.forEach((t) => self.placeTruck(t, z, mpp, M, S, R));
        camera.projectionMatrix = new THREE.Matrix4().fromArray(Array.from(mx));
        renderer.resetState();
        renderer.render(scene, camera);
        self.map.triggerRepaint();
      },
    };
  }

  private placeTruck(t: LiveTruck, z: number, mpp: number, M: THREE.Matrix4, S: THREE.Matrix4, R: THREE.Matrix4): void {
    if (!t.g) return;
    const mc = maplibregl.MercatorCoordinate.fromLngLat(t.pos, 0);
    const u = mc.meterInMercatorCoordinateUnits();
    const on = t.id === this.sel;
    const px = on ? (z > 11 ? 120 : 70) : 46;
    const k = Math.max(1.5, (px * mpp) / TRUCK_LENGTH_M) * u;
    const head = (-t.head * Math.PI) / 180 + Math.PI / 2;
    M.makeTranslation(mc.x, mc.y, mc.z);
    S.makeScale(k, -k, k);
    R.makeRotationZ(head);
    t.g.matrix.copy(M).multiply(S).multiply(R);
    t.g.matrixWorldNeedsUpdate = true;
    const ud = t.g.userData as TruckMaterials;
    ud.trailerM.color.setHex(on ? 0xe6f0fa : 0xf7f9fc);
    ud.stripeM.emissiveIntensity = on ? 0.9 : 0.25;
  }

  private tick(): void {
    if (this.dead) return;
    const s = (performance.now() - this.t0) / 1000;
    this.trucks.forEach((t) => this.moveTruck(t, s));
    this.drawChecks();
    this.raf = requestAnimationFrame(() => this.tick());
  }

  private moveTruck(t: LiveTruck, s: number): void {
    let r: LngLat[] | null = null, f = 0;
    if (t.dur && t.route) { r = ROUTES[t.route]; f = (t.from ?? 0) + ((t.to ?? 1) - (t.from ?? 0)) * Math.min(1, s / t.dur); }
    if (!r) return;
    const p = along(r, f), q = along(r, Math.min(1, f + HEAD_LOOKAHEAD));
    if (q[0] !== p[0] || q[1] !== p[1]) {
      const lat = (p[1] * Math.PI) / 180;
      const want = (Math.atan2((q[0] - p[0]) * Math.cos(lat), q[1] - p[1]) * 180) / Math.PI;
      const dh = ((want - t.head + 540) % 360) - 180;
      t.head += dh * HEAD_EASE;
    }
    t.pos = p; t.prog = f; t.mk.setLngLat(p);
  }

  private addModel(t: LiveTruck): void {
    if (!this.scene) return;
    t.g = buildTruck();
    t.g.matrixAutoUpdate = false;
    this.scene.add(t.g);
  }

  private removeTruck(t: LiveTruck): void {
    t.mk.remove();
    if (t.g) this.scene?.remove(t.g);
  }

  /**
   * Replace the trucks on the map. Trucks without a position (no park point and no route) are not drawn.
   *
   * Args:
   *   list: The fleet, as map specs.
   */
  setFleet(list: TruckSpec[]): void {
    this.fleet = list;
    if (!this.loaded) return;
    this.trucks.forEach((t) => this.removeTruck(t));
    this.trucks = list.filter(placeable).map((t) => this.addTruck(t));
    this.trucks.forEach((t) => this.addModel(t));
    this.select(this.sel && this.trucks.some((t) => t.id === this.sel) ? this.sel : null, true);
  }

  private drawChecks(): void {
    const id = this.sel, t = id ? this.trucks.find((x) => x.id === id) : undefined;
    const list = t && id && t.dur ? CHECKPOINTS[id] ?? null : null;
    const key = list && t ? t.id : "";
    if (key !== this.checkKey) {
      this.checks.forEach((c) => c.mk.remove());
      this.checks = [];
      this.checkKey = key;
      if (list && t) {
        const r = ROUTES[t.route as RouteId];
        this.checks = list.map(([name, f]) => { const e = checkEl(name); return { f, e, mk: new maplibregl.Marker({ element: e }).setLngLat(along(r, f)).addTo(this.map), st: "" }; });
      }
    }
    if (!list || !t) return;
    const nextI = this.checks.findIndex((c) => c.f > t.prog + CHECK_EPS);
    this.checks.forEach((c, i) => {
      const st: CheckState = c.f <= t.prog + CHECK_EPS ? "done" : i === nextI ? "next" : "upcoming";
      if (st === c.st) return;
      c.st = st;
      styleCheckEl(c.e, st);
    });
  }

  /**
   * Select a truck (or none) and fly the camera to it.
   *
   * Args:
   *   id: Truck to select, or null for the fleet view.
   *   quiet: Restyle without moving the camera.
   */
  select(id: string | null, quiet = false): void {
    this.sel = id;
    if (!this.loaded) return;
    this.trucks.forEach((t) => { const on = t.id === id; styleTruckEl(t.el, on); t.mk.getElement().style.zIndex = on ? "3" : "1"; });
    if (quiet) return;
    const t = this.trucks.find((x) => x.id === id);
    if (t) this.map.flyTo({ center: t.pos, zoom: 12.4, pitch: 66, bearing: t.head - 70, duration: 1800, essential: true, offset: [-190, 80], curve: 1.6 });
    else this.map.flyTo({ ...HOME, duration: 1200 });
  }

  /**
   * Show or hide a voice bubble above a truck.
   *
   * Args:
   *   id: Truck.
   *   b: Bubble content, or null to hide it.
   */
  say(id: string, b: Bubble | null): void {
    const t = this.trucks.find((x) => x.id === id);
    const el = t?.el.querySelector<HTMLElement & { _k?: string }>("[data-bub]");
    if (!t || !el) return;
    t.mk.getElement().style.zIndex = b ? "6" : t.id === this.sel ? "3" : "1";
    if (!b) { el.style.display = "none"; el._k = ""; return; }
    const k = b.mode + "|" + b.who + "|" + b.text;
    if (el._k === k) return;
    el._k = k;
    el.style.display = "block";
    el.innerHTML = bubbleHtml(b);
  }

  /**
   * Flash an expanding ring at a point.
   *
   * Args:
   *   c: Where to pulse.
   */
  pulse(c: LngLat): void {
    if (!this.loaded) return;
    const mk = new maplibregl.Marker({ element: pulseEl() }).setLngLat(c).addTo(this.map);
    window.setTimeout(() => mk.remove(), PULSE_MS);
  }

  /** Reveal the demo backhaul route once the owner approves it. */
  book(): void {
    if (!this.loaded) return;
    BOOKED_ROUTES.forEach((id) => {
      if (!this.map.getLayer(id)) return;
      [id, id + "-c"].forEach((l) => this.map.setLayoutProperty(l, "visibility", "visible"));
      this.map.setPaintProperty(id, "line-color", BLUE);
      this.map.setPaintProperty(id, "line-opacity", 0.9);
      this.map.setPaintProperty(id, "line-width", 3.5);
    });
    const start = ROUTES["R-O1-LOADED"][0];
    if (start) this.pulse(start);
  }
}

/** Whether a spec has somewhere to be drawn. */
function placeable(t: TruckSpec): boolean {
  return Boolean(t.park || t.route);
}
