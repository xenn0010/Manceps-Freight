import type { MancepsMap } from "./engine";

let current: MancepsMap | null = null;

/**
 * Register the live map so actions can drive it.
 *
 * Args:
 *   m: The map, or null when it unmounts.
 */
export function setMap(m: MancepsMap | null): void {
  current = m;
}

/**
 * The live map, if mounted.
 *
 * Returns:
 *   The map controller or null.
 */
export function getMap(): MancepsMap | null {
  return current;
}
