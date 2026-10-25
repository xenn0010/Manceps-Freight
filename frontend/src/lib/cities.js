export const CITY_COORDS = {
  "San Francisco": [-122.4194, 37.7749],
  Oakland: [-122.2712, 37.8044],
  "San Jose": [-121.8863, 37.3382],
  Sacramento: [-121.4944, 38.5816],
  Stockton: [-121.2908, 37.9577],
  Modesto: [-120.9969, 37.6391],
  Fresno: [-119.7871, 36.7378],
  Bakersfield: [-119.0187, 35.3733],
  "Los Angeles": [-118.2437, 34.0522],
};
export const CITIES = Object.keys(CITY_COORDS);

const rad = (d) => (d * Math.PI) / 180;
export function roadMiles(a, b) {
  const [x1, y1] = CITY_COORDS[a];
  const [x2, y2] = CITY_COORDS[b];
  const h = Math.sin(rad(y2 - y1) / 2) ** 2 + Math.cos(rad(y1)) * Math.cos(rad(y2)) * Math.sin(rad(x2 - x1) / 2) ** 2;
  const mi = 3959 * 2 * Math.asin(Math.sqrt(h)) * 1.18;
  return Math.max(5, Math.round(mi / 5) * 5);
}

// Places a truck at a city, nudged so it doesn't stack on trucks already there.
export function placeNear(trucks, city, selfId) {
  const [x, y] = CITY_COORDS[city];
  const n = Object.values(trucks).filter((t) => t.id !== selfId && Math.hypot(t.position[0] - x, t.position[1] - y) < 0.2).length;
  return [x + n * 0.32, y + n * 0.16];
}
