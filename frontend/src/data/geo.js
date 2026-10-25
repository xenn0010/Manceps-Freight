export function bearing([lng1, lat1], [lng2, lat2]) {
  const r = Math.PI / 180;
  const y = Math.sin((lng2 - lng1) * r) * Math.cos(lat2 * r);
  const x =
    Math.cos(lat1 * r) * Math.sin(lat2 * r) -
    Math.sin(lat1 * r) * Math.cos(lat2 * r) * Math.cos((lng2 - lng1) * r);
  return (Math.atan2(y, x) / r + 360) % 360;
}

export function nearestIndex(coords, [lng, lat]) {
  let best = 0;
  let bestD = Infinity;
  coords.forEach(([x, y], i) => {
    const d = (x - lng) ** 2 + (y - lat) ** 2;
    if (d < bestD) {
      bestD = d;
      best = i;
    }
  });
  return best;
}
