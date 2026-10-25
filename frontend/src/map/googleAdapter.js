import { setOptions, importLibrary } from "@googlemaps/js-api-loader";
import { COLORS, KEY_CITIES } from "./mapConfig";
import { truckSvg } from "./truckSvg";

// Restrained code-defined style (no Map ID): light grey, POIs/transit/road labels off; our own city labels on top.
const STYLE = [
  { elementType: "geometry", stylers: [{ color: "#EEEFF1" }] },
  { elementType: "labels.icon", stylers: [{ visibility: "off" }] },
  { elementType: "labels.text.fill", stylers: [{ color: "#8A8E95" }] },
  { elementType: "labels.text.stroke", stylers: [{ color: "#F4F5F7" }] },
  { featureType: "poi", stylers: [{ visibility: "off" }] },
  { featureType: "transit", stylers: [{ visibility: "off" }] },
  { featureType: "road", elementType: "geometry", stylers: [{ color: "#FFFFFF" }] },
  { featureType: "road", elementType: "labels", stylers: [{ visibility: "off" }] },
  { featureType: "road.highway", elementType: "geometry", stylers: [{ color: "#E2E4E8" }] },
  { featureType: "road.local", stylers: [{ visibility: "off" }] },
  { featureType: "water", elementType: "geometry", stylers: [{ color: "#D9DCE2" }] },
  { featureType: "water", elementType: "labels", stylers: [{ visibility: "off" }] },
  { featureType: "landscape.natural", elementType: "geometry", stylers: [{ color: "#ECEDEF" }] },
  { featureType: "administrative", elementType: "geometry.stroke", stylers: [{ color: "#CDD0D6" }] },
  { featureType: "administrative.locality", elementType: "labels", stylers: [{ visibility: "off" }] },
  { featureType: "administrative.neighborhood", stylers: [{ visibility: "off" }] },
  { featureType: "administrative.land_parcel", stylers: [{ visibility: "off" }] },
];
const CANDIDATES = [[30, -22], [30, 22], [-30, -22], [-30, 22], [0, -34], [0, 34], [40, 0], [-40, 0], [52, -40], [-52, -40], [52, 40], [-52, 40], [0, -56], [0, 56]];
const overlap = (a, b) =>
  Math.max(0, Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x)) * Math.max(0, Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y));

let loading = null;
function loadGoogle(apiKey) {
  if (!loading) {
    setOptions({ key: apiKey, v: "weekly" });
    loading = importLibrary("maps").then(() => window.google);
  }
  return loading;
}

function lineStyle(f, g) {
  const { kind, dim, sel } = f.properties;
  const op = (on, off) => (dim ? off : on);
  if (kind === "done") return [{ strokeColor: COLORS.done, strokeWeight: 2.5, strokeOpacity: op(0.9, 0.2), zIndex: 1 }];
  if (kind === "empty")
    return [{ strokeOpacity: 0, zIndex: 2, icons: [{ icon: { path: g.maps.SymbolPath.CIRCLE, scale: sel ? 1.8 : 1.5, fillColor: COLORS.empty, fillOpacity: op(0.95, 0.2), strokeOpacity: 0 }, offset: "0", repeat: "9px" }] }];
  const casing = { strokeColor: "#FFFFFF", strokeWeight: sel ? 9 : 6.5, strokeOpacity: op(0.95, 0.15), zIndex: 3 };
  if (kind === "confirmed") return [casing, { strokeColor: sel ? COLORS.purpleDeep : COLORS.confirmed, strokeWeight: sel ? 4.5 : 3, strokeOpacity: op(0.95, 0.15), zIndex: 4 }];
  const dash = { path: "M 0,-1 0,1", strokeColor: COLORS.purple, strokeOpacity: op(1, 0.2), strokeWeight: sel ? 4.5 : 3.4, scale: 3 };
  return [casing, { strokeOpacity: 0, zIndex: 5, icons: [{ icon: dash, offset: "0", repeat: "14px" }] }];
}

export async function createGoogleAdapter(container, handlers, apiKey, onFail) {
  window.gm_authFailure = () => onFail("Google rejected the API key (gm_authFailure)");
  const g = await loadGoogle(apiKey);
  container.innerHTML = "";
  const map = new g.maps.Map(container, {
    center: { lat: 36.3, lng: -120.4 }, zoom: 6.4, styles: STYLE, disableDefaultUI: true, clickableIcons: false,
    keyboardShortcuts: false, gestureHandling: "greedy", backgroundColor: "#EEEFF1", isFractionalZoomEnabled: true,
  });
  let tilesOk = false;
  map.addListener("tilesloaded", () => (tilesOk = true));
  const watchdog = setTimeout(() => !tilesOk && onFail("Google tiles did not load within 10 s"), 10000);

  const trucks = new Map();
  const cityEls = [];
  let polylines = [];
  let stopMarkers = [];
  let routeCoords = [];
  let raf = 0;
  let lastFit = null;
  const layer = new g.maps.OverlayView();
  const root = document.createElement("div");
  root.style.cssText = "position:absolute;left:0;top:0;";
  const px = (lngLat) => layer.getProjection()?.fromLatLngToContainerPixel(new g.maps.LatLng(lngLat[1], lngLat[0]));
  const divPx = (lngLat) => layer.getProjection()?.fromLatLngToDivPixel(new g.maps.LatLng(lngLat[1], lngLat[0]));
  const posOf = (m) => m.pos;

  function positionAll() {
    if (!layer.getProjection()) return;
    [...cityEls, ...trucks.values()].forEach((m) => {
      const p = divPx(m.pos);
      m.wrap.style.transform = `translate(${p.x}px, ${p.y}px)`;
    });
    schedulePlace();
  }
  layer.onAdd = () => layer.getPanes().overlayMouseTarget.appendChild(root);
  layer.draw = positionAll;
  layer.onRemove = () => root.remove();
  layer.setMap(map);

  const wrapEl = (el, z) => {
    const w = document.createElement("div");
    w.style.cssText = `position:absolute;left:0;top:0;width:0;height:0;z-index:${z};`;
    el.style.position = "absolute";
    el.style.transform = "translate(-50%, -50%)";
    w.appendChild(el);
    root.appendChild(w);
    return w;
  };

  KEY_CITIES.forEach((c) => {
    const el = document.createElement("div");
    el.className = "city-label";
    el.innerHTML = `<span class="city-leader"></span><span class="city-dot"></span><span class="city-name" data-testid="city-label-${c.name.toLowerCase().replace(/\s+/g, "-")}">${c.name}</span>`;
    el.style.transform = "none";
    cityEls.push({ el, pos: c.coord, side: c.side, wrap: wrapEl(el, 1) });
  });

  const onRoute = (box) => routeCoords.some((c) => {
    const p = px(c);
    return p && p.x >= box.x && p.x <= box.x + box.w && p.y >= box.y && p.y <= box.y + box.h;
  });

  function placeCities(iconBoxes) {
    const placed = cityEls.map((c) => {
      const p = px(c.pos);
      return { x: p.x - 6, y: p.y - 6, w: 12, h: 12 };
    });
    cityEls.forEach((c) => {
      const name = c.el.querySelector(".city-name");
      const p = px(c.pos);
      const w = name.offsetWidth;
      const h = 16;
      const side = c.side === "left" ? -1 : 1;
      const sx = (dir, gap) => (dir > 0 ? gap : -gap - w);
      const cands = [[sx(side, 9), -8], [sx(-side, 9), -8], [sx(side, 9), -22], [sx(side, 9), 6], [sx(-side, 9), -22], [sx(-side, 9), 6], [sx(side, 41), -8], [sx(-side, 41), -8], [-w / 2, -58], [-w / 2, 42]];
      let best = null;
      cands.forEach(([dx, dy], i) => {
        const box = { x: p.x + dx - 2, y: p.y + dy - 2, w: w + 4, h: h + 4 };
        const score = [...iconBoxes, ...placed].reduce((s, o) => s + overlap(box, o), 0) * 10 + (onRoute(box) ? 150 : 0) + i * 20;
        if (!best || score < best.score) best = { dx, dy, box, score };
      });
      name.style.left = `${best.dx}px`;
      name.style.top = `${best.dy}px`;
      const cx = Math.max(best.dx, Math.min(0, best.dx + w));
      const cy = Math.max(best.dy, Math.min(0, best.dy + h));
      const dist = Math.hypot(cx, cy);
      const leader = c.el.querySelector(".city-leader");
      leader.style.opacity = dist > 14 ? 1 : 0;
      leader.style.width = `${Math.max(0, dist - 7)}px`;
      leader.style.transform = `rotate(${Math.atan2(cy, cx)}rad) translateX(4px)`;
      placed.push(best.box);
    });
    return placed;
  }

  function placeLabels() {
    if (!layer.getProjection()) return;
    const W = container.clientWidth;
    const H = container.clientHeight;
    const pts = [...trucks.values()].map((m) => ({ m, p: px(posOf(m)) }));
    const truckBoxes = pts.map(({ p }) => ({ x: p.x - 18, y: p.y - 18, w: 36, h: 36 }));
    const iconBoxes = pts.map(({ p }) => ({ x: p.x - 38, y: p.y - 38, w: 76, h: 76 }));
    const obstacles = [...placeCities(iconBoxes), ...truckBoxes, { x: 0, y: 0, w: W, h: 58 }];
    pts.sort((a, b) => Number(b.m.selected) - Number(a.m.selected));
    pts.forEach(({ m, p }) => {
      const w = m.label.offsetWidth || 44;
      const h = m.label.offsetHeight || 24;
      let best = null;
      CANDIDATES.forEach(([dx, dy], i) => {
        const box = { x: p.x + dx - w / 2, y: p.y + dy - h / 2, w, h };
        let score = obstacles.reduce((s, o) => s + overlap(box, o), 0) + i * 0.5;
        if (box.x < 4 || box.y < 4 || box.x + w > W - 4 || box.y + h > H - 4) score += 4000;
        if (!best || score < best.score) best = { dx, dy, box, score };
      });
      obstacles.push(best.box);
      m.label.style.transform = `translate(${best.dx - w / 2}px, ${best.dy - h / 2}px)`;
      const len = Math.hypot(best.dx, best.dy);
      m.leader.setAttribute("x1", (best.dx / len) * 15);
      m.leader.setAttribute("y1", (best.dy / len) * 15);
      m.leader.setAttribute("x2", best.dx - (best.dx / len) * 8);
      m.leader.setAttribute("y2", best.dy - (best.dy / len) * 8);
      m.leader.style.opacity = len > 38 ? 1 : 0;
    });
  }
  const schedulePlace = () => {
    cancelAnimationFrame(raf);
    raf = requestAnimationFrame(placeLabels);
  };
  map.addListener("idle", schedulePlace);
  map.addListener("dragstart", () => handlers.onTruckHover?.(null));
  map.addListener("click", () => handlers.onBackgroundClick?.());
  document.fonts?.ready.then(schedulePlace);
  const ro = new ResizeObserver(() => {
    schedulePlace();
    lastFit && setTimeout(() => fit(lastFit.coords, lastFit.opts), 260);
  });
  ro.observe(container);

  function fit(coords, opts = {}) {
    if (!coords?.length) return;
    lastFit = { coords, opts };
    const b = new g.maps.LatLngBounds();
    coords.forEach((c) => b.extend({ lat: c[1], lng: c[0] }));
    const h = container.clientHeight;
    map.fitBounds(b, { top: Math.min(110, h * 0.2), bottom: Math.min(48, h * 0.09), left: opts.padLeft ?? 90, right: 90 });
    const max = (opts.maxZoom ?? 7.2) + 1;
    g.maps.event.addListenerOnce(map, "idle", () => map.getZoom() > max && map.setZoom(max));
  }

  function createTruck(t) {
    const el = document.createElement("div");
    el.className = "truck-marker";
    el.tabIndex = 0;
    el.setAttribute("role", "button");
    el.setAttribute("data-testid", `truck-marker-${t.unit}`);
    el.innerHTML = `<svg class="truck-leader" width="1" height="1"><line stroke="#181A1A" stroke-width="1.2" stroke-dasharray="2 2"/></svg><span class="truck-pulse"></span><span class="truck-icon"></span><span class="truck-label" data-testid="truck-label-${t.unit}">${t.unit}</span>`;
    g.maps.OverlayView.preventMapHitsAndGesturesFrom(el);
    const point = () => px(trucks.get(t.id).pos);
    el.addEventListener("mouseenter", () => handlers.onTruckHover?.(t.id, point()));
    el.addEventListener("mouseleave", () => handlers.onTruckHover?.(null));
    el.addEventListener("click", (e) => {
      e.stopPropagation();
      handlers.onTruckClick?.(t.id);
    });
    el.addEventListener("keydown", (e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), handlers.onTruckClick?.(t.id)));
    return { el, pos: t.position, wrap: wrapEl(el, 3), label: el.querySelector(".truck-label"), leader: el.querySelector("line"), icon: el.querySelector(".truck-icon"), sig: "" };
  }

  return {
    provider: "google",
    setTrucks(list) {
      const ids = new Set(list.map((t) => t.id));
      for (const [id, m] of trucks) if (!ids.has(id)) (m.wrap.remove(), trucks.delete(id));
      list.forEach((t) => {
        if (!trucks.has(t.id)) trucks.set(t.id, createTruck(t));
        const m = trucks.get(t.id);
        m.selected = t.selected;
        m.pos = t.position;
        const sig = `${t.color}|${t.heading}`;
        if (sig !== m.sig) (m.icon.innerHTML = truckSvg(t.color, t.heading)), (m.sig = sig);
        m.el.classList.toggle("is-selected", t.selected);
        m.el.classList.toggle("is-dim", t.dim);
        m.wrap.style.zIndex = t.selected ? 5 : 3;
        m.el.setAttribute("aria-label", `Truck ${t.unit}, ${t.driverName}, ${t.status}`);
        m.el.setAttribute("aria-pressed", String(t.selected));
      });
      positionAll();
    },
    setRoutes(fc) {
      polylines.forEach((p) => p.setMap(null));
      polylines = [];
      routeCoords = [];
      fc.features.forEach((f) => {
        const path = f.geometry.coordinates.map(([lng, lat]) => ({ lat, lng }));
        f.geometry.coordinates.forEach((c, i) => i % 3 === 0 && routeCoords.push(c));
        lineStyle(f, g).forEach((o) => polylines.push(new g.maps.Polyline({ path, map, clickable: false, ...o })));
      });
      schedulePlace();
    },
    setStops(fc) {
      stopMarkers.forEach((m) => m.setMap(null));
      stopMarkers = fc.features.map((f) => {
        const { type, color, dim, sel } = f.properties;
        const pickup = type === "pickup";
        return new g.maps.Marker({
          map, clickable: false, zIndex: 6, position: { lat: f.geometry.coordinates[1], lng: f.geometry.coordinates[0] },
          icon: { path: g.maps.SymbolPath.CIRCLE, scale: sel ? 6 : 5, fillColor: pickup ? "#FFFFFF" : color, fillOpacity: dim ? 0.25 : 1, strokeColor: pickup ? color : "#FFFFFF", strokeOpacity: dim ? 0.25 : 1, strokeWeight: 2.5 },
        });
      });
    },
    fitTo: fit,
    zoomIn: () => map.setZoom(map.getZoom() + 1),
    zoomOut: () => map.setZoom(map.getZoom() - 1),
    resize: schedulePlace,
    destroy() {
      clearTimeout(watchdog);
      ro.disconnect();
      cancelAnimationFrame(raf);
      polylines.forEach((p) => p.setMap(null));
      stopMarkers.forEach((m) => m.setMap(null));
      layer.setMap(null);
      g.maps.event.clearInstanceListeners(map);
      container.innerHTML = "";
    },
  };
}
