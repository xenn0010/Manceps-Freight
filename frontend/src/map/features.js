import { ROUTES } from "../data/seed";
import { COLORS, HEALTH_COLOR } from "./mapConfig";

const LIVE_OFFER = ["proposed", "awaiting_broker"];

export function buildMapFeatures(data, selectedId) {
  const routes = [];
  const stops = [];
  const focus = {};
  const props = (truckId) => ({ truckId, dim: !!selectedId && selectedId !== truckId, sel: selectedId === truckId });
  const pushCoords = (truckId, coords) => (focus[truckId] = [...(focus[truckId] || []), ...coords]);

  const addLine = (truckId, coords, kind, key) => {
    routes.push({ type: "Feature", properties: { ...props(truckId), kind, key }, geometry: { type: "LineString", coordinates: coords } });
    pushCoords(truckId, coords);
  };
  const addRoutes = (truckId, list, loadedKind) =>
    list.forEach((r) => {
      const coords = ROUTES[r.id].coordinates;
      if (r.progressIndex != null) {
        addLine(truckId, coords.slice(0, r.progressIndex + 1), "done", `${r.id}-done`);
        addLine(truckId, coords.slice(r.progressIndex), r.kind === "loaded" ? loadedKind : "empty", r.id);
      } else addLine(truckId, coords, r.kind === "loaded" ? loadedKind : "empty", r.id);
    });
  const addStops = (truckId, list, proposed) =>
    list.forEach((s, i) =>
      stops.push({
        type: "Feature",
        properties: { ...props(truckId), type: s.type, label: s.label, color: proposed ? COLORS.purple : COLORS.confirmed, key: `${truckId}-${i}-${s.label}` },
        geometry: { type: "Point", coordinates: s.coord },
      })
    );

  Object.values(data.segments)
    .filter((s) => s.status === "planned")
    .forEach((s) => addLine(s.truckId, ROUTES[s.routeId].coordinates, "empty", s.id));
  Object.values(data.offers)
    .filter((o) => LIVE_OFFER.includes(o.status) && o.routes)
    .forEach((o) => {
      addRoutes(o.truckId, o.routes, "proposed");
      addStops(o.truckId, o.stops, true);
    });
  Object.values(data.trips)
    .filter((t) => ["active", "confirmed"].includes(t.status))
    .forEach((t) => {
      addRoutes(t.truckId, t.routes, "confirmed");
      addStops(t.truckId, t.stops, false);
    });

  const trucks = Object.values(data.trucks).map((t) => {
    pushCoords(t.id, [t.position]);
    return {
      id: t.id, unit: t.unit, position: t.position, heading: t.heading,
      color: selectedId === t.id ? COLORS.purpleDeep : HEALTH_COLOR[t.health],
      driverName: data.drivers[t.driverId].name, status: t.statusShort,
      selected: selectedId === t.id, dim: !!selectedId && selectedId !== t.id,
    };
  });

  return {
    routes: { type: "FeatureCollection", features: routes },
    stops: { type: "FeatureCollection", features: stops },
    trucks,
    focus,
    fleet: trucks.map((t) => t.position),
  };
}
