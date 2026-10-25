// A photo mapped onto a dome that turns to follow the cursor and nods on hover.
import * as THREE from "three";
import { clamp } from "./kit";

const VERT = `varying vec2 vUv; varying vec3 vN; uniform vec2 uLook; uniform float uHover;
  void main(){ vUv=uv; vec3 p=position; float r=length(p.xy); float b=sqrt(max(0.,1.-r*r));
    p.z = b*(.55+.15*uHover);
    vN = normalize(vec3(p.xy, b+.001));
    gl_Position=projectionMatrix*modelViewMatrix*vec4(p,1.); }`;

const FRAG = `varying vec2 vUv; varying vec3 vN; uniform sampler2D map; uniform float uAspect; uniform vec2 uLook; uniform float uHover;
  void main(){ vec2 c=vUv-.5; float r=length(c)*2.; if(r>1.) discard;
    vec2 uv=c; if(uAspect<1.) { uv.y*=uAspect; uv.y+=.5*(1.-uAspect)*.55; } else uv.x/=uAspect;
    uv = uv*.92 + .5 - uLook*.025;
    vec3 col=texture2D(map,uv).rgb;
    vec3 L=normalize(vec3(-.4+uLook.x*.6,.5+uLook.y*.4,1.)); float d=max(dot(vN,L),0.);
    col*= .9 + .16*d; col += pow(1.-vN.z,3.)*.12;
    float a=smoothstep(1.,.985,r);
    gl_FragColor=vec4(col,a); }`;

const NOD_S = 0.9;
const MAX_DT = 0.05;
/** How far the cursor can be (in face widths) and still get full attention. */
const NEAR_FACTOR = 1.6;
const FAR_ATTENTION = 0.25;

/** Imperative controller for one agent face. */
export class AgentFace {
  private r: THREE.WebGLRenderer;
  private scene = new THREE.Scene();
  private cam = new THREE.PerspectiveCamera(28, 1, 0.1, 20);
  private pivot = new THREE.Group();
  private uni = { map: { value: null as THREE.Texture | null }, uAspect: { value: 1 }, uLook: { value: new THREE.Vector2() }, uHover: { value: 0 }, uTime: { value: 0 } };
  private target = new THREE.Vector2();
  private look = new THREE.Vector2();
  private hover = 0;
  private hoverT = 0;
  private nodT = -9;
  private last = performance.now();
  private raf = 0;
  private dead = false;
  private ro: ResizeObserver;
  private hoverHost: HTMLElement;

  /**
   * Render a face into a container.
   *
   * Args:
   *   el: Element the canvas fills.
   *   src: Photo URL.
   */
  constructor(private el: HTMLElement, src: string) {
    this.r = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    this.r.setPixelRatio(Math.min(devicePixelRatio, 2));
    this.r.domElement.style.cssText = "position:absolute;inset:0;width:100%;height:100%;display:block";
    el.appendChild(this.r.domElement);
    this.cam.position.set(0, 0, 4.1);
    this.scene.add(this.pivot);
    this.hoverHost = el.closest<HTMLElement>("[data-agent-card]") ?? el;
    window.addEventListener("pointermove", this.onMove);
    this.hoverHost.addEventListener("pointerenter", this.onEnter);
    this.hoverHost.addEventListener("pointerleave", this.onLeave);
    this.ro = new ResizeObserver(() => this.resize()); this.ro.observe(el); this.resize();
    new THREE.TextureLoader().loadAsync(src).then((tex) => this.build(tex)).catch((err: unknown) => console.error("[agent-face] failed to load", src, err));
  }

  /** Remove listeners and free GPU resources. */
  destroy(): void {
    this.dead = true;
    cancelAnimationFrame(this.raf);
    this.ro.disconnect();
    window.removeEventListener("pointermove", this.onMove);
    this.hoverHost.removeEventListener("pointerenter", this.onEnter);
    this.hoverHost.removeEventListener("pointerleave", this.onLeave);
    this.r.dispose();
    this.r.domElement.remove();
  }

  private build(tex: THREE.Texture): void {
    if (this.dead) return;
    tex.colorSpace = THREE.SRGBColorSpace; tex.anisotropy = 8;
    const img = tex.image as { width: number; height: number };
    this.uni.map.value = tex; this.uni.uAspect.value = img.width / img.height;
    const mat = new THREE.ShaderMaterial({ uniforms: this.uni, transparent: true, vertexShader: VERT, fragmentShader: FRAG });
    this.pivot.add(new THREE.Mesh(new THREE.CircleGeometry(1, 96, 0, Math.PI * 2), mat));
    this.raf = requestAnimationFrame((n) => this.frame(n));
  }

  private resize(): void {
    const w = this.el.clientWidth || 1, h = this.el.clientHeight || 1;
    this.r.setSize(w, h, false);
    this.cam.aspect = w / h;
    this.cam.updateProjectionMatrix();
  }

  private onMove = (e: PointerEvent): void => {
    const b = this.el.getBoundingClientRect(), cx = b.left + b.width / 2, cy = b.top + b.height / 2;
    const dx = (e.clientX - cx) / (b.width * 1.4), dy = (e.clientY - cy) / (b.height * 1.4);
    const near = Math.hypot(e.clientX - cx, e.clientY - cy) < b.width * NEAR_FACTOR;
    this.target.set(clamp(dx, -1, 1), clamp(-dy, -1, 1)).multiplyScalar(near ? 1 : FAR_ATTENTION);
  };

  private onEnter = (): void => { this.hoverT = 1; this.nodT = performance.now() / 1000; };
  private onLeave = (): void => { this.hoverT = 0; };

  private frame(now: number): void {
    if (this.dead) return;
    const dt = Math.min(MAX_DT, (now - this.last) / 1000), t = now / 1000, p = this.pivot;
    this.last = now;
    this.hover += (this.hoverT - this.hover) * Math.min(1, dt * 7);
    this.look.lerp(this.target, Math.min(1, dt * 6));
    const since = t - this.nodT;
    const nod = since < NOD_S ? Math.sin((since / NOD_S) * Math.PI * 2) * 0.14 * (1 - since / NOD_S) : 0;
    p.rotation.y = this.look.x * (0.28 + 0.22 * this.hover);
    p.rotation.x = -this.look.y * (0.2 + 0.15 * this.hover) + nod;
    p.rotation.z = -this.look.x * 0.05 * this.hover + Math.sin(t * 1.3) * 0.01;
    p.position.y = Math.sin(t * 1.6) * 0.015 + this.hover * 0.03;
    p.scale.setScalar(1 + this.hover * 0.05);
    this.uni.uLook.value.copy(this.look); this.uni.uHover.value = this.hover;
    this.r.render(this.scene, this.cam);
    this.raf = requestAnimationFrame((n) => this.frame(n));
  }
}
