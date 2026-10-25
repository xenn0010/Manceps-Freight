// Phase 3 seed additions: editable fleet fields, per-truck cost, AI settings.
export const DEFAULT_SETTINGS = { negotiationFloor: 2, maxCounterSteps: 2, autoContactBrokers: true, requireApproval: true, driverTone: "Friendly" };

const DRIVER_EXTRA = {
  "D-101": { phone: "555-0111", homeLocation: "San Francisco", preferences: "Prefers SF ⇄ LA lanes" },
  "D-102": { phone: "555-0112", homeLocation: "Fresno", preferences: "Short regional runs" },
  "D-103": { phone: "555-0113", homeLocation: "Sacramento", preferences: "Home most nights" },
  "D-104": { phone: "555-0114", homeLocation: "San Jose", preferences: "No overnight team runs" },
};
const TRIP_EXTRA = {
  "L-101": { commodity: "Electronics", weight: 28000 },
  "L-103": { commodity: "Dry groceries", weight: 36000 },
  "L-201": { commodity: "Boxed produce", weight: 30000 },
  "L-301": { commodity: "Paper goods", weight: 22000 },
};

export function applyPhase3(seed) {
  Object.assign(seed.carrier, {
    contactName: "Jordan Diaz", phone: "555-0100", email: "dispatch@demowestfreight.example",
    homeBase: "Oakland, CA", preferredLanes: "Bay Area ⇄ Los Angeles; Central Valley", maxDeadhead: 75, minRatePerMile: 2.2,
    avoidRegions: "Mountain passes in snow",
  });
  seed.carriers = {};
  Object.values(seed.trucks).forEach((t) => Object.assign(t, { costPerMile: seed.carrier.costPerMile, opStatus: "Active" }));
  Object.entries(DRIVER_EXTRA).forEach(([id, x]) => Object.assign(seed.drivers[id], x));
  Object.entries(TRIP_EXTRA).forEach(([id, x]) => Object.assign(seed.trips[id], x));
  seed.settings = { ...DEFAULT_SETTINGS };
  return seed;
}
