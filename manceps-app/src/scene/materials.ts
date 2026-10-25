import * as THREE from "three";
import { RoundedBoxGeometry, canvasTex, noise } from "./kit";

const DS = THREE.DoubleSide;

/**
 * Create every material the hero scene uses.
 *
 * Returns:
 *   Materials keyed by role.
 */
export function createMaterials() {
  return {
    paint: new THREE.MeshPhysicalMaterial({ color: 0x1c1b1f, metalness: 0.55, roughness: 0.22, clearcoat: 1, clearcoatRoughness: 0.05, envMapIntensity: 1.6 }),
    black: new THREE.MeshStandardMaterial({ color: 0x15171c, metalness: 0.35, roughness: 0.5, side: DS }),
    liner: new THREE.MeshStandardMaterial({ color: 0x0e0f12, roughness: 0.9, side: DS }),
    chrome: new THREE.MeshStandardMaterial({ color: 0xe6e9ee, metalness: 1, roughness: 0.12, side: DS }),
    glass: new THREE.MeshPhysicalMaterial({ color: 0x0b1018, metalness: 0.3, roughness: 0.03, clearcoat: 1, envMapIntensity: 2.4, side: DS }),
    tire: new THREE.MeshStandardMaterial({ color: 0x101114, roughness: 0.82 }),
    rim: new THREE.MeshStandardMaterial({ color: 0x9da3ad, metalness: 0.9, roughness: 0.28 }),
    rimDark: new THREE.MeshStandardMaterial({ color: 0x2c3036, metalness: 0.8, roughness: 0.4 }),
    alu: new THREE.MeshStandardMaterial({ color: 0xc9cbd0, metalness: 0.85, roughness: 0.3 }),
    aluDark: new THREE.MeshStandardMaterial({ color: 0x5d636c, metalness: 0.8, roughness: 0.4, side: DS }),
    wallIn: new THREE.MeshStandardMaterial({ color: 0x5b6472, roughness: 0.85 }),
    floorIn: new THREE.MeshStandardMaterial({ color: 0x4a4744, roughness: 0.7 }),
    frost: new THREE.MeshPhysicalMaterial({ color: 0xdedbd5, roughness: 0.3, transparent: true, opacity: 0.22, depthWrite: false, side: DS }),
    frostFront: new THREE.MeshPhysicalMaterial({ color: 0xe8e5df, metalness: 0.2, roughness: 0.35, transparent: true, opacity: 0.8, side: DS }),
    redLamp: new THREE.MeshStandardMaterial({ color: 0x400000, emissive: 0xff2a2a, emissiveIntensity: 2.2 }),
    amberLamp: new THREE.MeshStandardMaterial({ color: 0x402000, emissive: 0xffa024, emissiveIntensity: 2.2, side: DS }),
    headlamp: new THREE.MeshPhysicalMaterial({ color: 0xf2f0ea, metalness: 0.6, roughness: 0.08, emissive: 0xfff4dc, emissiveIntensity: 0.5, clearcoat: 1, side: DS }),
    glow: new THREE.MeshStandardMaterial({ color: 0xd8e6ff, emissive: 0x3f86ff, emissiveIntensity: 1.4, roughness: 0.3 }),
    ground: new THREE.MeshStandardMaterial({ color: 0xe3eef7, roughness: 1, transparent: true }),
    road: new THREE.MeshStandardMaterial({ color: 0xc3d4e3, roughness: 0.95 }),
    lane: new THREE.MeshBasicMaterial({ color: 0xffffff }),
    bldg: new THREE.MeshStandardMaterial({ color: 0xf6f9fc, roughness: 0.85 }),
    bldgDark: new THREE.MeshStandardMaterial({ color: 0xb9cde0, roughness: 0.9 }),
    door: new THREE.MeshStandardMaterial({ color: 0x0b1a2e, roughness: 0.6 }),
    dockLip: new THREE.MeshStandardMaterial({ color: 0x8ea3b8, roughness: 0.8 }),
    bumper: new THREE.MeshStandardMaterial({ color: 0x1b1b1d, roughness: 0.9 }),
    stripe: new THREE.MeshStandardMaterial({ color: 0x2f7cff, emissive: 0x2f7cff, emissiveIntensity: 0.6, roughness: 0.8 }),
    route: new THREE.MeshBasicMaterial({ color: 0x1f6fff, transparent: true, opacity: 0.85 }),
    shirt: new THREE.MeshStandardMaterial({ color: 0xf2f0ec, roughness: 0.8 }),
    vest: new THREE.MeshStandardMaterial({ color: 0x2f7cff, roughness: 0.6 }),
    pants: new THREE.MeshStandardMaterial({ color: 0x14192a, roughness: 0.8 }),
    wood: new THREE.MeshStandardMaterial({ color: 0xcfb08a, roughness: 0.85 }),
    box: new THREE.MeshStandardMaterial({ map: cardboardTexture(), roughness: 0.82 }),
  };
}

export type Materials = ReturnType<typeof createMaterials>;

function cardboardTexture(): THREE.CanvasTexture {
  return canvasTex(256, 256, (c, w, h) => {
    c.fillStyle = "#b8875a"; c.fillRect(0, 0, w, h);
    noise(c, w, h, 9000, 0.18, "#8a6034", "#e2bd8f");
    c.fillStyle = "rgba(214,170,112,.55)"; c.fillRect(w * 0.43, 0, w * 0.14, h);
    c.strokeStyle = "rgba(70,45,20,.55)"; c.lineWidth = 5; c.strokeRect(0, 0, w, h);
  });
}

/** Unit cardboard box shared by cargo, pallets and carried boxes. */
export const BOX_GEO = new RoundedBoxGeometry(1, 1, 1, 2, 0.035);
