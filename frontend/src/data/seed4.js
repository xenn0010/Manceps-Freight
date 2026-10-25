// Phase 4 seed additions: calling mode (Simulated by default so tests never dial), demo numbers, live calls.
export function applyPhase4(seed) {
  seed.calling = { mode: "simulated", numbers: {} };
  seed.liveCalls = {};
  seed.settings.speakUpdates = false;
  return seed;
}
