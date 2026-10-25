// The landing hero film: the trailer loads at the dock, the truck pulls out, then a bird's-eye view as the agent plans the next load.
import * as THREE from "three";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import { clamp, ease } from "./kit";
import { createMaterials } from "./materials";
import { buildTruck, type TruckBuild } from "./truck";
import { buildCity, buildGround, buildPeople, buildTraffic, buildWarehouse, type Car, type Person } from "./world";

/** Film length in seconds; it loops. */
const LOOP = 29;
/** When the truck starts driving. */
const DRIVE_AT = 9.2;
const ACCEL = 1.0, VMAX = 15;
const BLEND = 1.3;
const FADE_OUT = 0.8, FADE_IN = 0.6;
const LOAD_DELAY = 1.2;
const ROUTE_AT = 15.8, ROUTE_DUR = 3.5, ROUTE_LEN = 180;
const PHASE3_AT = 21.5;
const MAX_DT = 0.05;
const WHEEL_R = 0.52;
const STEP_HZ = 7.5;

interface Shot { until: number; cam: (t: number, tx: number) => { p: THREE.Vector3; l: THREE.Vector3 } }

/** Truck x position for a time: parked, then accelerating out along -x. */
function truckX(t: number): number {
  const tb = t - DRIVE_AT;
  if (tb <= 0) return 0;
  const tA = VMAX / ACCEL;
  return tb < tA ? -0.5 * ACCEL * tb * tb : -(0.5 * ACCEL * tA * tA + VMAX * (tb - tA));
}

/** Imperative controller for the hero film. */
export class HeroScene {
  private renderer: THREE.WebGLRenderer;
  private scene = new THREE.Scene();
  private camera = new THREE.PerspectiveCamera(30, 1, 0.1, 600);
  private sun = new THREE.DirectionalLight(0xfff6ea, 2.4);
  private tr: TruckBuild;
  private ground: THREE.Mesh;
  private route: THREE.Mesh;
  private cars: Car[];
  private people: Person[];
  private WX: number;
  private shots: Shot[];
  private clock = 0;
  private last = performance.now();
  private phase = -1;
  private raf = 0;
  private dead = false;
  private ro: ResizeObserver;
  private tmp = new THREE.Vector3();

  /**
   * Build the scene in a container and start the loop.
   *
   * Args:
   *   host: Element the canvas fills.
   *   onPhase: Called with 0–3 as the film moves between loading, dispatch, in transit and agent.
   */
  constructor(private host: HTMLElement, private onPhase: (phase: number) => void) {
    const r = this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" });
    r.setPixelRatio(Math.min(devicePixelRatio, 2));
    r.toneMapping = THREE.ACESFilmicToneMapping; r.toneMappingExposure = 1.12;
    r.shadowMap.enabled = true; r.shadowMap.type = THREE.PCFSoftShadowMap;
    r.setClearColor(0x000000, 0);
    r.domElement.style.cssText = "position:absolute;inset:0;width:100%;height:100%;display:block;opacity:0;transition:opacity .8s ease";
    host.appendChild(r.domElement);
    const M = createMaterials();
    this.scene.fog = new THREE.Fog(0xf3f6fa, 90, 260);
    ({ ground: this.ground, route: this.route } = buildGround(this.scene, M));
    this.tr = buildTruck(M); this.scene.add(this.tr.root);
    this.WX = this.tr.rearX + 1.4;
    buildWarehouse(this.scene, M, this.WX);
    this.cars = buildTraffic(this.scene, M, buildCity(this.scene, M));
    this.people = buildPeople(this.scene, M, this.WX);
    this.light();
    this.shots = this.makeShots();
    this.ro = new ResizeObserver(() => this.resize()); this.ro.observe(host); this.resize();
    r.compile(this.scene, this.camera);
    this.raf = requestAnimationFrame((n) => this.frame(n));
  }

  /** Stop the loop and free GPU resources. */
  destroy(): void {
    this.dead = true;
    cancelAnimationFrame(this.raf);
    this.ro.disconnect();
    this.renderer.dispose();
    this.renderer.domElement.remove();
  }

  private light(): void {
    const s = this.scene, pmrem = new THREE.PMREMGenerator(this.renderer);
    s.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
    s.environmentIntensity = 0.7;
    s.add(new THREE.HemisphereLight(0xffffff, 0xbcd3ea, 1.1));
    const fillB = new THREE.DirectionalLight(0x8da6ff, 0.7); fillB.position.set(14, 5, 12); s.add(fillB);
    const backB = new THREE.DirectionalLight(0x3a6dff, 1.1); backB.position.set(10, 8, -14); s.add(backB);
    const sun = this.sun; sun.castShadow = true; sun.shadow.mapSize.set(4096, 4096);
    const sc = sun.shadow.camera; sc.left = -30; sc.right = 30; sc.top = 30; sc.bottom = -30; sc.near = 1; sc.far = 120;
    sun.shadow.bias = -0.0004; sun.shadow.radius = 6;
    s.add(sun, sun.target);
  }

  private resize(): void {
    const w = this.host.clientWidth || 1, h = this.host.clientHeight || 1;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }

  private makeShots(): Shot[] {
    const V = (x: number, y: number, z: number): THREE.Vector3 => new THREE.Vector3(x, y, z);
    const asp = (): number => Math.max(0.6, this.camera.aspect);
    const birdsEye = (_t: number, tx: number): { p: THREE.Vector3; l: THREE.Vector3 } => ({ p: V(tx + 14, 70 * Math.max(1, 1.2 / asp()), 26), l: V(tx - 6, 0, 0) });
    return [
      { until: 9.6, cam: (t) => { const a = -0.5 + t * 0.03, r = 33 * Math.max(1, 1.45 / asp()); return { p: V(2 + Math.sin(a) * r, 9 + t * 0.12, Math.cos(a) * r), l: V(2.5, 2.4, 0) }; } },
      { until: 15.5, cam: (_t, tx) => ({ p: V(this.WX - 0.6, 3.1, 11.5), l: V(Math.max(tx - 3, -80), 1.6, -0.5) }) },
      { until: PHASE3_AT, cam: birdsEye },
      { until: 99, cam: birdsEye },
    ];
  }

  private camFor(t: number, tx: number): { p: THREE.Vector3; l: THREE.Vector3; i: number } {
    const i = Math.max(0, this.shots.findIndex((s) => t < s.until));
    const shot = this.shots[i] as Shot, cur = shot.cam(t, tx);
    const prevShot = this.shots[i - 1];
    if (prevShot && i < 3 && t - prevShot.until < BLEND) {
      const k = ease.inOut((t - prevShot.until) / BLEND), prev = prevShot.cam(t, tx);
      return { p: prev.p.lerp(cur.p, k), l: prev.l.lerp(cur.l, k), i };
    }
    return { ...cur, i };
  }

  private animatePeople(t: number): void {
    this.people.forEach((P) => {
      if (P.still) {
        P.g.position.set(P.at[0], 0, P.at[1]);
        const look = Math.atan2(-(this.tr.root.position.z - P.at[1]), this.tr.root.position.x - P.at[0]);
        P.g.rotation.y = t > DRIVE_AT ? look : P.face;
        P.legs.forEach((l) => { l.rotation.z = 0; });
        const wave = P.arms[0];
        if (wave) wave.rotation.z = t > 10 && t < 13 ? 2.6 + Math.sin(t * 9) * 0.3 : 0;
        return;
      }
      const [a, b] = P.path, len = Math.hypot(b[0] - a[0], b[1] - a[1]);
      const s = ((t * P.speed) / len + P.phase) % 2, u = s < 1 ? s : 2 - s, dir = s < 1 ? 1 : -1;
      P.g.position.set(a[0] + (b[0] - a[0]) * u, Math.abs(Math.sin(t * STEP_HZ + P.phase * 9)) * 0.04, a[1] + (b[1] - a[1]) * u);
      P.g.rotation.y = Math.atan2(-(b[1] - a[1]) * dir, (b[0] - a[0]) * dir);
      const sw = Math.sin(t * STEP_HZ + P.phase * 9) * 0.55;
      const [l0, l1] = P.legs, [a0, a1] = P.arms;
      if (l0 && l1) { l0.rotation.z = sw; l1.rotation.z = -sw; }
      if (P.carry) P.arms.forEach((ar) => { ar.rotation.z = 1.1; });
      else if (a0 && a1) { a0.rotation.z = -sw * 0.7; a1.rotation.z = sw * 0.7; }
    });
  }

  private animateCars(t: number): void {
    this.cars.forEach((C) => {
      if (C.axis === "x") {
        const span = 440;
        let x = C.off + C.dir * C.speed * t;
        x = (((x + 482) % span) + span) % span - 482;
        C.g.position.set(x, 0, C.lane); C.g.rotation.y = C.dir > 0 ? Math.PI : 0;
      } else {
        const side = C.off < 0 ? -1 : 1, zr = Math.abs(C.off) + C.speed * t;
        C.g.position.set(C.x, 0, side * (9 + (((zr % 121) + 121) % 121)));
        C.g.rotation.y = side > 0 ? -Math.PI / 2 : Math.PI / 2;
      }
    });
  }

  private frame(now: number): void {
    if (this.dead) return;
    const dt = Math.min(MAX_DT, (now - this.last) / 1000);
    this.last = now;
    if (!document.hidden) this.clock += dt;
    const t = this.clock % LOOP, tx = truckX(t);
    this.renderer.domElement.style.opacity = String(t > LOOP - FADE_OUT ? (LOOP - t) / FADE_OUT : t < FADE_IN ? t / FADE_IN : 1);
    this.tr.root.position.x = tx;
    this.tr.wheels.forEach((w) => { w.rotation.z = ((w.userData.sign as number) || 1) * (-tx / WHEEL_R); });
    this.tr.cargo.update(t - LOAD_DELAY);
    this.animatePeople(t);
    this.ground.position.x = Math.min(0, tx);
    this.animateCars(t);
    const rk = clamp((t - ROUTE_AT) / ROUTE_DUR, 0, 1);
    this.route.position.x = tx - 9; this.route.scale.x = 0.001 + ease.outCubic(rk) * ROUTE_LEN;
    (this.route.material as THREE.MeshBasicMaterial).opacity = 0.85 * rk;
    const c = this.camFor(t, tx);
    this.camera.position.copy(c.p); this.camera.lookAt(c.l);
    this.tmp.set(tx, 0, 0); this.sun.target.position.copy(this.tmp); this.sun.position.set(tx - 18, 40, 22);
    const ph = t >= PHASE3_AT ? 3 : c.i >= 2 ? 2 : c.i;
    if (ph !== this.phase) { this.phase = ph; this.onPhase(ph); }
    this.renderer.render(this.scene, this.camera);
    this.raf = requestAnimationFrame((n) => this.frame(n));
  }
}
