import { createMaplibreAdapter } from "./maplibreAdapter";
import { createGoogleAdapter } from "./googleAdapter";

/*
 Map adapter interface (provider-agnostic):
   setTrucks(trucks), setRoutes(featureCollection), setStops(featureCollection),
   fitTo(coords, { maxZoom, padLeft }), zoomIn(), zoomOut(), resize(), destroy()
 handlers: onTruckHover(id | null, {x, y}), onTruckClick(id), onBackgroundClick()
 Google Maps first; falls back to MapLibre automatically if the key is missing or rejected.
 Dev check: append ?map=maplibre or ?gmapsKey=invalid to the URL.
*/
const REPLAY = ["setRoutes", "setStops", "setTrucks", "fitTo"];

export function createMapAdapter(container, handlers) {
  const params = new URLSearchParams(window.location.search);
  const key = params.get("gmapsKey") || process.env.REACT_APP_GOOGLE_MAPS_API_KEY;
  const last = {};
  let impl = null;
  let dead = false;
  let fellBack = false;
  const mark = (provider, reason = "") => {
    container.dataset.mapProvider = provider;
    window.__freightosMap = { provider, reason };
  };
  const replay = () => REPLAY.forEach((m) => last[m] && impl[m](...last[m]));
  const fallbackToMaplibre = (reason) => {
    if (dead || fellBack) return;
    fellBack = true;
    if (reason) console.warn(`[map] Falling back to MapLibre: ${reason}`);
    impl?.destroy();
    impl = createMaplibreAdapter(container, handlers);
    mark("maplibre", reason || "");
    replay();
  };

  if (!key || params.get("map") === "maplibre") fallbackToMaplibre(key ? "forced by ?map=maplibre" : "no Google Maps key");
  else
    createGoogleAdapter(container, handlers, key, fallbackToMaplibre)
      .then((gAdapter) => {
        if (dead || fellBack) return gAdapter.destroy();
        impl = gAdapter;
        mark("google");
        replay();
      })
      .catch((e) => fallbackToMaplibre(e?.message || "Google Maps failed to load"));

  const call = (m) => (...args) => {
    last[m] = args;
    impl?.[m](...args);
  };
  return {
    setTrucks: call("setTrucks"),
    setRoutes: call("setRoutes"),
    setStops: call("setStops"),
    fitTo: call("fitTo"),
    zoomIn: () => impl?.zoomIn(),
    zoomOut: () => impl?.zoomOut(),
    resize: () => impl?.resize(),
    destroy() {
      dead = true;
      impl?.destroy();
    },
  };
}
