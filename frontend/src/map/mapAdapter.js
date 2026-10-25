import { createMaplibreAdapter } from "./maplibreAdapter";

/*
 Map adapter interface (provider-agnostic):
   setTrucks(trucks), setRoutes(featureCollection), setStops(featureCollection),
   fitTo(coords, { maxZoom }), zoomIn(), zoomOut(), resize(), destroy()
 handlers: onTruckHover(id | null, {x, y}), onTruckClick(id), onBackgroundClick()
 To switch to Google Maps, implement the same interface and return it here.
*/
export function createMapAdapter(container, handlers) {
  return createMaplibreAdapter(container, handlers);
}
