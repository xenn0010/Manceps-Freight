import json, math, urllib.request

ROUTES = {
    "R-L101-RET": [(-118.2301, 34.0039), (-119.9618, 36.0080), (-122.3900, 37.7400)],
    "R-O1-EMPTY-PU": [(-118.2301, 34.0039), (-118.2620, 33.8317)],
    "R-O1-LOADED": [(-118.2620, 33.8317), (-119.9618, 36.0080), (-122.2900, 37.7985)],
    "R-O1-EMPTY-SF": [(-122.2900, 37.7985), (-122.3900, 37.7400)],
    "R-L103": [(-122.3900, 37.7400), (-121.6555, 36.6777), (-120.6596, 35.2828), (-119.6982, 34.4208), (-118.2301, 34.0039)],
    "R-L201": [(-119.7900, 36.7600), (-121.2908, 37.9577)],
    "R-L301": [(-121.4944, 38.5816), (-122.2711, 37.8044)],
}


def dp(points, eps):
    if len(points) < 3:
        return points
    a, b = points[0], points[-1]
    dmax, idx = 0, 0
    for i in range(1, len(points) - 1):
        p = points[i]
        num = abs((b[1] - a[1]) * p[0] - (b[0] - a[0]) * p[1] + b[0] * a[1] - b[1] * a[0])
        den = math.hypot(b[1] - a[1], b[0] - a[0]) or 1e-12
        d = num / den
        if d > dmax:
            dmax, idx = d, i
    if dmax > eps:
        return dp(points[: idx + 1], eps)[:-1] + dp(points[idx:], eps)
    return [a, b]


out = {}
for rid, pts in ROUTES.items():
    coords = ";".join(f"{x},{y}" for x, y in pts)
    url = f"https://router.project-osrm.org/route/v1/driving/{coords}?overview=full&geometries=geojson"
    data = json.load(urllib.request.urlopen(url, timeout=60))
    line = data["routes"][0]["geometry"]["coordinates"]
    simp = dp(line, 0.0015)
    out[rid] = {"miles": round(data["routes"][0]["distance"] / 1609.34), "coordinates": [[round(x, 5), round(y, 5)] for x, y in simp]}
    print(rid, len(line), "->", len(simp), out[rid]["miles"], "mi")

with open("/app/frontend/src/data/routeGeometry.json", "w") as f:
    json.dump(out, f, separators=(",", ":"))
