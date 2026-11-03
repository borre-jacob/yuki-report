"""Give each Alpine resort its avalanche forecast micro-region (EAWS), e.g. "AT-07-14-01" or "CH-4113".

Usage: python3 tools/assign_eaws.py data/osm/alps.json
Region outlines come from regions.avalanches.org. The resort point is tested against the current outlines
(end_date empty); a resort just outside every outline (point in a valley between regions) gets the
nearest region within 15 km. Adds "eaws" to each row, or removes it when nothing is close.
"""
import json, math, subprocess, sys, time

REGIONS = ["AT-02", "AT-03", "AT-04", "AT-05", "AT-06", "AT-07", "AT-08", "CH", "FR",
           "IT-21", "IT-23", "IT-25", "IT-32-BZ", "IT-32-TN", "IT-34", "IT-36"]
UA = "YukiReport/1.0 (personal ski trip app; github.com/borre-jacob/yuki-report)"


def get(url):
    return json.loads(subprocess.run(["curl", "-sSfL", "-m", "60", "-A", UA, url], capture_output=True, check=True).stdout)


def rings(geom):
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    # each poly: [outer, hole, ...]; points can carry a third value (height), which is dropped
    return [[[(pt[0], pt[1]) for pt in ring] for ring in p] for p in polys]


def inside_ring(lon, lat, ring):
    hit = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > lat) != (y2 > lat) and lon < x1 + (lat - y1) * (x2 - x1) / (y2 - y1):
            hit = not hit
    return hit


def inside(lon, lat, poly):
    return inside_ring(lon, lat, poly[0]) and not any(inside_ring(lon, lat, h) for h in poly[1:])


def km_to_ring(lon, lat, ring):
    kx = 111.32 * math.cos(math.radians(lat))
    return min(math.hypot((x - lon) * kx, (y - lat) * 110.57) for x, y in ring)


features = []
for reg in REGIONS:
    for f in get(f"https://regions.avalanches.org/micro-regions/{reg}_micro-regions.geojson.json")["features"]:
        if not f["properties"].get("end_date"):
            features.append((f["properties"]["id"], rings(f["geometry"])))
    time.sleep(0.5)
print(len(features), "current micro-regions", file=sys.stderr)

rows = json.load(open(sys.argv[1], encoding="utf-8"))
missing = []
for r in rows:
    hit = next((fid for fid, polys in features if any(inside(r["lon"], r["lat"], p) for p in polys)), None)
    if not hit:
        d, fid = min((min(km_to_ring(r["lon"], r["lat"], p[0]) for p in polys), fid) for fid, polys in features)
        hit = fid if d <= 15 else None
    if hit:
        r["eaws"] = hit
    else:
        r.pop("eaws", None); missing.append(r["name"])
json.dump(rows, open(sys.argv[1], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(len(rows) - len(missing), "resorts assigned; no region:", missing, file=sys.stderr)
