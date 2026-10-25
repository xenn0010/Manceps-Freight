export const BASEMAP_STYLE_URL = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json";

export const COLORS = {
  ink: "#181A1A",
  purple: "#AF6EFF",
  purpleDeep: "#8B45F0",
  confirmed: "#3A3D42",
  empty: "#9A9DA4",
  done: "#C4C6CC",
  amber: "#F2A93B",
  green: "#6CC24A",
  idle: "#9A9DA4",
};

export const HEALTH_COLOR = { working: COLORS.ink, risk: COLORS.amber, on_track: COLORS.green, idle: COLORS.idle };

// Key California cities. side = which side of the dot the name sits on.
export const KEY_CITIES = [
  { name: "San Francisco", coord: [-122.4194, 37.7749], side: "left" },
  { name: "Oakland", coord: [-122.2711, 37.8044], side: "right" },
  { name: "San Jose", coord: [-121.8863, 37.3382], side: "right" },
  { name: "Sacramento", coord: [-121.4944, 38.5816], side: "right" },
  { name: "Stockton", coord: [-121.2908, 37.9577], side: "right" },
  { name: "Fresno", coord: [-119.7871, 36.7378], side: "left" },
  { name: "Los Angeles", coord: [-118.2437, 34.0522], side: "left" },
];
