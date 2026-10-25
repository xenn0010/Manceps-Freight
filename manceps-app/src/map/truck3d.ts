import * as THREE from "three";

export interface TruckMaterials {
  trailerM: THREE.MeshStandardMaterial;
  stripeM: THREE.MeshStandardMaterial;
}

/** Truck length in meters, used to scale the model to a pixel size. */
export const TRUCK_LENGTH_M = 18.5;

const WHEEL_X = [-7, -5.8, 4.4, 6.0, 8.0];
const WHEEL_Y = [-1.15, 1.15];
const WHEEL_SEGMENTS = 14;

/**
 * Build the low-poly tractor-trailer. Units are meters: +x forward, y lateral, z up.
 *
 * Returns:
 *   The truck group; `userData` holds the trailer and stripe materials for selection styling.
 */
export function buildTruck(): THREE.Group {
  const g = new THREE.Group();
  const mat = (c: number, o: THREE.MeshStandardMaterialParameters = {}): THREE.MeshStandardMaterial =>
    new THREE.MeshStandardMaterial({ color: c, roughness: 0.55, metalness: 0.1, side: THREE.DoubleSide, ...o });
  const box = (m: THREE.Material, x0: number, x1: number, y0: number, y1: number, z0: number, z1: number): void => {
    const b = new THREE.Mesh(new THREE.BoxGeometry(x1 - x0, y1 - y0, z1 - z0), m);
    b.position.set((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2);
    g.add(b);
  };
  const trailerM = mat(0xf7f9fc), stripeM = mat(0x2272ad, { emissive: 0x2272ad, emissiveIntensity: 0.25 });
  const cabM = mat(0x0b1626, { roughness: 0.35, metalness: 0.4 }), glass = mat(0x8fb8da, { roughness: 0.1, metalness: 0.6 });
  const tire = mat(0x14171c, { roughness: 0.9 }), chrome = mat(0xc9d3de, { metalness: 0.9, roughness: 0.2 });
  box(trailerM, -8.2, 5.4, -1.3, 1.3, 1.25, 4.0);
  box(stripeM, -8.21, 5.41, -1.31, 1.31, 1.45, 1.75);
  box(chrome, -8.3, 5.4, -1.15, 1.15, 0.95, 1.25);
  box(cabM, 5.7, 8.9, -1.25, 1.25, 0.9, 3.0);
  box(cabM, 6.3, 8.9, -1.2, 1.2, 3.0, 3.75);
  box(glass, 8.5, 8.92, -1.1, 1.1, 2.4, 3.3);
  box(chrome, 8.9, 9.15, -1.2, 1.2, 0.9, 1.4);
  for (const x of WHEEL_X) for (const y of WHEEL_Y) {
    const w = new THREE.Mesh(new THREE.CylinderGeometry(0.55, 0.55, 0.45, WHEEL_SEGMENTS), tire);
    w.position.set(x, y, 0.55);
    g.add(w);
  }
  const shadow = new THREE.Mesh(new THREE.PlaneGeometry(TRUCK_LENGTH_M, 3.6), new THREE.MeshBasicMaterial({ color: 0x0a1a2e, transparent: true, opacity: 0.18, depthWrite: false }));
  shadow.position.set(0.4, 0, 0.02);
  g.add(shadow);
  const ud: TruckMaterials = { trailerM, stripeM };
  g.userData = ud;
  return g;
}
