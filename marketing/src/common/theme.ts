// Palette and type taken from the Manceps app (manceps-app/src/components/ui.tsx and styles).
export const INK = "#010D1D";
export const BLUE = "#2272AD";
export const BLUE_LIGHT = "#4C9BFF";
export const MIST = "#F4F6F9";
export const SLATE = "#64748A";
export const SLATE_LIGHT = "#8C9AAD";
export const FONT = "'Alliance No.2', 'Helvetica Neue', Helvetica, Arial, sans-serif";
export const FPS = 30;
export const WIDTH = 1920;
export const HEIGHT = 1080;
/** Apple-like decelerating curve used for nearly every move. */
export const EASE_OUT: [number, number, number, number] = [0.16, 1, 0.3, 1];
export const EASE_IN_OUT: [number, number, number, number] = [0.65, 0, 0.35, 1];

/**
 * Convert seconds to a whole frame index.
 *
 * Args:
 *   s: Seconds.
 *
 * Returns:
 *   Frame number at FPS.
 */
export function sec(s: number): number {
  return Math.round(s * FPS);
}
