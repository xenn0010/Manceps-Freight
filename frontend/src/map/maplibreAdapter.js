import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { BASEMAP_STYLE_URL, COLORS, KEY_CITIES } from "./mapConfig";
import { truckSvg } from "./truckSvg";

const EMPTY = { type: "FeatureCollection", features: [] };
const CANDIDATES = [[30, -22], [30, 22], [-30, -22], [-30, 22], [0, -34], [0, 34], [40, 0], [-40, 0], [52, -40], [-52, -40], [52, 40], [-52, 40], [0, -56], [0, 56]];
const dimOpacity = (on, off) => ["case", ["get", "dim"], off, on];
const selWidth = (sel, base) => ["case", ["get", "sel"], sel, base];

function muteBasemap(map) {
  map.getStyle().layers.forEach((l) => {
    if (l.type === "symbol") map.setLayoutProperty(l.id, "visibility", "none");
    else if (l.type === "background") map.setPaintProperty(l.id, "background-color", "#EEEFF1");
    else if (l.type === "fill" && /water/.test(l.id)) map.setPaintProperty(l.id, "fill-color", "#D9DCE2");
    else if (l.type === "fill" && /park|landuse|landcover|wood|grass/.test(l.id)) map.setPaintProperty(l.id, "fill-opacity", 0.25);
  });
}

function addLayers(map) {
  map.addSource("routes", { type: "geojson", data: EMPTY });
  map.addSource("stops", { type: "geojson", data: EMPTY });
  const line = (id, filter, paint, layout = {}) =>
    map.addLayer({ id, type: "line", source: "routes", filter, paint, layout: { "line-cap": "round", "line-join": "round", ...layout } });
  line("route-done", ["==", ["get", "kind"], "done"], { "line-color": COLORS.done, "line-width": 2.5, "line-opacity": dimOpacity(0.9, 0.2) });
  line("route-casing", ["in", ["get", "kind"], ["literal", ["confirmed", "proposed"]]], {
    "line-color": "#FFFFFF", "line-width": selWidth(9, 6.5), "line-opacity": dimOpacity(0.95, 0.15),
  });
  line("route-empty", ["==", ["get", "kind"], "empty"], {
    "line-color": COLORS.empty, "line-width": selWidth(3.4, 2.8), "line-opacity": dimOpacity(0.95, 0.2), "line-dasharray": [0.1, 2],
  });
  line("route-confirmed", ["==", ["get", "kind"], "confirmed"], {
    "line-color": ["case", ["get", "sel"], COLORS.purpleDeep, COLORS.confirmed], "line-width": selWidth(4.5, 3), "line-opacity": dimOpacity(0.95, 0.15),
  });
  line("route-proposed", ["==", ["get", "kind"], "proposed"], {
    "line-color": COLORS.purple, "line-width": selWidth(4.5, 3.4), "line-opacity": dimOpacity(1, 0.2), "line-dasharray": [1.6, 1.3],
  }, { "line-cap": "butt" });
  map.addLayer({
    id: "stops", type: "circle", source: "stops",
    paint: {
      "circle-radius": selWidth(6, 5),
      "circle-color": ["case", ["==", ["get", "type"], "pickup"], "#FFFFFF", ["get", "color"]],
      "circle-stroke-color": ["case", ["==", ["get", "type"], "pickup"], ["get", "color"], "#FFFFFF"],
      "circle-stroke-width": 2.5,
      "circle-opacity": dimOpacity(1, 0.25),
      "circle-stroke-opacity": dimOpacity(1, 0.25),
    },
  });
}

const overlap = (a, b) =>
  Math.max(0, Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x)) * Math.max(0, Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y));


export function createMaplibreAdapter(container, handlers) {
  const map = new maplibregl.Map({
    container, style: BASEMAP_STYLE_URL, center: [-120.4, 36.3], zoom: 5.4,
    attributionControl: false, dragRotate: false, pitchWithRotate: false, renderWorldCopies: false,
  });
  map.touchZoomRotate.disableRotation();
  map.addControl(new maplibregl.AttributionControl({ compact: false }), "bottom-right");

  let loaded = false;
  const queue = [];
  const whenReady = (fn) => (loaded ? fn() : queue.push(fn));
  const trucks = new Map();
  const cityEls = [];
  let lastFit = null;
  let raf = 0;

  function placeCities(truckBoxes) {
    const dots = cityEls.map((el) => {
      const p = map.project(el._coord);
      return { x: p.x - 6, y: p.y - 6, w: 12, h: 12 };
    });
    const placed = [...dots];
    cityEls.forEach((el) => {
      const name = el.querySelector(".city-name");
      const p = map.project(el._coord);
      const w = name.offsetWidth;
      const h = 16;
      const side = el._side === "left" ? -1 : 1;
      const sx = (dir, gap) => (dir > 0 ? gap : -gap - w);
      const cands = [
        [sx(side, 9), -8], [sx(-side, 9), -8], [sx(side, 9), -22], [sx(side, 9), 6], [sx(-side, 9), -22], [sx(-side, 9), 6],
        [sx(side, 41), -8], [sx(-side, 41), -8],
        [-w / 2, -58], [-w / 2, 42], [sx(side, 41), -34], [sx(side, 41), 18], [sx(-side, 41), -34], [sx(-side, 41), 18],
      ];
      const routeLayers = (map.getStyle()?.layers || []).filter((l) => l.id.startsWith("route")).map((l) => l.id);
      let best = null;
      cands.forEach(([dx, dy], i) => {
        const box = { x: p.x + dx - 2, y: p.y + dy - 2, w: w + 4, h: h + 4 };
        const onRoute = routeLayers.length ? map.queryRenderedFeatures([[box.x, box.y], [box.x + box.w, box.y + box.h]], { layers: routeLayers }).length : 0;
        const score = [...truckBoxes, ...placed].reduce((s, o) => s + overlap(box, o), 0) * 10 + (onRoute ? 150 : 0) + i * 20;
        if (!best || score < best.score) best = { dx, dy, box, score };
      });
      name.style.left = `${best.dx}px`;
      name.style.top = `${best.dy}px`;
      const cx = Math.max(best.dx, Math.min(0, best.dx + w));
      const cy = Math.max(best.dy, Math.min(0, best.dy + h));
      const dist = Math.hypot(cx, cy);
      const leader = el.querySelector(".city-leader");
      leader.style.opacity = dist > 14 ? 1 : 0;
      leader.style.width = `${Math.max(0, dist - 7)}px`;
      leader.style.transform = `rotate(${Math.atan2(cy, cx)}rad) translateX(4px)`;
      placed.push(best.box);
    });
    return placed;
  }

  function placeLabels() {
    const cr = container.getBoundingClientRect();
    const pts = [...trucks.values()].map((m) => ({ m, p: map.project(m.marker.getLngLat()) }));
    const truckBoxes = pts.map(({ p }) => ({ x: p.x - 18, y: p.y - 18, w: 36, h: 36 }));
    const iconBoxes = pts.map(({ p }) => ({ x: p.x - 38, y: p.y - 38, w: 76, h: 76 }));
    const obstacles = [...placeCities(iconBoxes), ...truckBoxes, { x: 0, y: 0, w: cr.width, h: 58 }];
    pts.sort((a, b) => Number(b.m.selected) - Number(a.m.selected));
    pts.forEach(({ m, p }) => {
      const w = m.label.offsetWidth || 44;
      const h = m.label.offsetHeight || 24;
      let best = null;
      CANDIDATES.forEach(([dx, dy], i) => {
        const box = { x: p.x + dx - w / 2, y: p.y + dy - h / 2, w, h };
        let score = obstacles.reduce((s, o) => s + overlap(box, o), 0) + i * 0.5;
        if (box.x < 4 || box.y < 4 || box.x + w > cr.width - 4 || box.y + h > cr.height - 4) score += 4000;
        if (!best || score < best.score) best = { dx, dy, box, score };
      });
      obstacles.push(best.box);
      m.label.style.transform = `translate(${best.dx - w / 2}px, ${best.dy - h / 2}px)`;
      const len = Math.hypot(best.dx, best.dy);
      const ux = best.dx / len;
      const uy = best.dy / len;
      m.leader.setAttribute("x1", ux * 15);
      m.leader.setAttribute("y1", uy * 15);
      m.leader.setAttribute("x2", best.dx - ux * 8);
      m.leader.setAttribute("y2", best.dy - uy * 8);
      m.leader.style.opacity = len > 38 ? 1 : 0;
    });
  }
  const schedulePlace = () => {
    cancelAnimationFrame(raf);
    raf = requestAnimationFrame(placeLabels);
  };

  map.on("load", () => {
    muteBasemap(map);
    addLayers(map);
    KEY_CITIES.forEach((c) => {
      const el = document.createElement("div");
      el.className = "city-label";
      el.innerHTML = `<span class="city-leader"></span><span class="city-dot"></span><span class="city-name" data-testid="city-label-${c.name.toLowerCase().replace(/\s+/g, "-")}">${c.name}</span>`;
      el._coord = c.coord;
      el._side = c.side;
      new maplibregl.Marker({ element: el, anchor: "center" }).setLngLat(c.coord).addTo(map);
      cityEls.push(el);
    });
    loaded = true;
    queue.splice(0).forEach((f) => f());
    schedulePlace();
  });
  map.on("move", schedulePlace);
  map.on("idle", schedulePlace);
  document.fonts?.ready.then(schedulePlace);
  map.on("movestart", () => handlers.onTruckHover?.(null));
  map.on("click", (e) => {
    if (e.originalEvent?.target?.closest?.(".truck-marker")) return;
    handlers.onBackgroundClick?.();
  });

  let resizeTimer = 0;
  const ro = new ResizeObserver(() => {
    map.resize();
    schedulePlace();
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => lastFit && fit(lastFit.coords, lastFit.opts), 260);
  });
  ro.observe(container);

  function fit(coords, opts = {}) {
    if (!coords?.length) return;
    lastFit = { coords, opts };
    const b = coords.reduce((acc, c) => acc.extend(c), new maplibregl.LngLatBounds(coords[0], coords[0]));
    const h = container.clientHeight;
    map.fitBounds(b, { padding: { top: Math.min(110, h * 0.2), bottom: Math.min(48, h * 0.09), left: opts.padLeft ?? 90, right: 90 }, maxZoom: opts.maxZoom ?? 7.2, duration: opts.instant ? 0 : 900 });
  }

  function createTruck(t) {
    const el = document.createElement("div");
    el.className = "truck-marker";
    el.tabIndex = 0;
    el.setAttribute("role", "button");
    el.setAttribute("data-testid", `truck-marker-${t.unit}`);
    el.innerHTML = `<svg class="truck-leader" width="1" height="1"><line stroke="#181A1A" stroke-width="1.2" stroke-dasharray="2 2"/></svg><span class="truck-pulse"></span><span class="truck-icon"></span><span class="truck-label" data-testid="truck-label-${t.unit}">${t.unit}</span>`;
    const point = () => map.project(trucks.get(t.id).marker.getLngLat());
    el.addEventListener("mouseenter", () => handlers.onTruckHover?.(t.id, point()));
    el.addEventListener("mouseleave", () => handlers.onTruckHover?.(null));
    el.addEventListener("focus", () => handlers.onTruckHover?.(t.id, point()));
    el.addEventListener("blur", () => handlers.onTruckHover?.(null));
    el.addEventListener("click", (e) => {
      e.stopPropagation();
      handlers.onTruckClick?.(t.id);
    });
    el.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        handlers.onTruckClick?.(t.id);
      }
    });
    const marker = new maplibregl.Marker({ element: el, anchor: "center" }).setLngLat(t.position).addTo(map);
    return { marker, el, label: el.querySelector(".truck-label"), leader: el.querySelector("line"), icon: el.querySelector(".truck-icon"), sig: "" };
  }

  return {
    setTrucks(list) {
      const nextIds = new Set(list.map((t) => t.id));
      for (const [id, m] of trucks) {
        if (!nextIds.has(id)) {
          cancelAnimationFrame(m.anim);
          m.marker.remove();
          trucks.delete(id);
        }
      }
      list.forEach((t) => {
        if (!trucks.has(t.id)) trucks.set(t.id, createTruck(t));
        const m = trucks.get(t.id);
        m.selected = t.selected;
        const cur = m.marker.getLngLat();
        if (Math.abs(cur.lng - t.position[0]) + Math.abs(cur.lat - t.position[1]) > 1e-6) {
          cancelAnimationFrame(m.anim);
          const from = [cur.lng, cur.lat];
          const t0 = performance.now();
          const step = (ts) => {
            const k = Math.min(1, (ts - t0) / 1200);
            const e = 1 - (1 - k) ** 3;
            m.marker.setLngLat([from[0] + (t.position[0] - from[0]) * e, from[1] + (t.position[1] - from[1]) * e]);
            schedulePlace();
            if (k < 1) m.anim = requestAnimationFrame(step);
          };
          m.anim = requestAnimationFrame(step);
        }
        const sig = `${t.color}|${t.heading}`;
        if (sig !== m.sig) {
          m.icon.innerHTML = truckSvg(t.color, t.heading);
          m.sig = sig;
        }
        m.el.classList.toggle("is-selected", t.selected);
        m.el.classList.toggle("is-dim", t.dim);
        m.el.style.zIndex = t.selected ? 5 : 3;
        m.el.setAttribute("aria-label", `Truck ${t.unit}, ${t.driverName}, ${t.status}`);
        m.el.setAttribute("aria-pressed", String(t.selected));
      });
      schedulePlace();
    },
    setRoutes: (fc) => whenReady(() => map.getSource("routes").setData(fc)),
    setStops: (fc) => whenReady(() => map.getSource("stops").setData(fc)),
    fitTo: (coords, opts) => whenReady(() => fit(coords, opts)),
    zoomIn: () => map.zoomIn(),
    zoomOut: () => map.zoomOut(),
    resize: () => map.resize(),
    destroy() {
      ro.disconnect();
      cancelAnimationFrame(raf);
      map.remove();
    },
  };
}
