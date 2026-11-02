"""Find ski resorts in Norway, Sweden and Finland from OpenStreetMap.

Usage: python3 tools/discover_resorts.py data/osm/scandinavia.json data/osm/scandinavia_found.json
       python3 tools/discover_resorts.py data/osm/alps.json data/osm/alps_found.json --countries AT,CH,FR,IT --alps --top 300

A resort is a named ski area (landuse=winter_sports) with lifts. Each lift is assigned to the
nearest named ski area within 2.5 km. Base/top come from the lowest/highest lift station
(Open-Meteo elevation data). Small hills are dropped: at least 150 m vertical or 4 lifts.
Areas within 3 km of a resort already in the first file (if it exists) are skipped.
--countries: ISO codes, one Overpass query per country (default NO,SE,FI).
--alps: keep only areas inside a rough outline of the Alps (drops the Pyrenees, Massif Central,
Vosges and Apennines). --min-vert / --min-lifts change the size filter; --top keeps the N largest.
"""
import argparse, json, math, os, subprocess, sys, time

UA = "YukiRadar/1.0 (personal ski trip app; github.com/borre-jacob/yuki-radar)"
OVERPASS = ["https://maps.mail.ru/osm/tools/overpass/api/interpreter", "https://overpass-api.de/api/interpreter"]
KINDS = "chair_lift|gondola|cable_car|mixed_lift|drag_lift|t-bar|j-bar|platter"
ap = argparse.ArgumentParser()
ap.add_argument("existing"); ap.add_argument("out")
ap.add_argument("--countries", default="NO,SE,FI")
ap.add_argument("--alps", action="store_true")
ap.add_argument("--min-vert", type=int, default=150); ap.add_argument("--min-lifts", type=int, default=4)
ap.add_argument("--top", type=int, default=0)
opt = ap.parse_args()
COUNTRIES = opt.countries.split(",")
# (lon, lat) outline of the Alps, generous to the north so Austria's eastern Alps and the Swiss Jura stay in
ALPS = [(5.2, 43.6), (7.5, 43.7), (8.2, 44.0), (8.7, 44.7), (9.6, 45.55), (12.4, 45.65), (13.7, 45.75),
        (16.5, 46.4), (16.5, 48.3), (9.5, 48.3), (7.5, 47.6), (5.8, 47.3), (5.2, 46.0)]


def inside(lon, lat, poly):
    hit = False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        if (y1 > lat) != (y2 > lat) and lon < x1 + (lat - y1) * (x2 - x1) / (y2 - y1):
            hit = not hit
    return hit


def curl(url, data=None):
    cmd = ["curl", "-sS", "-m", "300", "-A", UA, url]
    if data:
        cmd += ["--data-urlencode", "data=" + data]
    return subprocess.run(cmd, capture_output=True, text=True).stdout


def overpass(q):
    # Answers are kept in data/dl/ (not in git) so a rerun does not hit the busy servers again
    import hashlib
    path = os.path.join("data", "dl", "overpass-" + hashlib.sha1(q.encode()).hexdigest()[:16] + ".json")
    if os.path.exists(path):
        return json.load(open(path, encoding="utf-8"))
    for attempt in range(6):
        try:
            els = json.loads(curl(OVERPASS[attempt % 2], q))["elements"]
            os.makedirs(os.path.dirname(path), exist_ok=True)
            json.dump(els, open(path, "w", encoding="utf-8"))
            return els
        except Exception:
            print("overpass retry", attempt, file=sys.stderr)
            time.sleep(15 * (attempt + 1))
    raise SystemExit("Overpass failed")


def km(a, b, c, d):
    t = math.radians
    h = math.sin(t(c - a) / 2) ** 2 + math.cos(t(a)) * math.cos(t(c)) * math.sin(t(d - b) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


ELEV_CACHE = os.path.join("data", "dl", "elevations.json")


def topodata(chunk):
    # Fallback when Open-Meteo's daily quota is used up: OpenTopoData (1 call a second, 100 points a call)
    url = "https://api.opentopodata.org/v1/mapzen?locations=" + "|".join(f"{p[0]:.5f},{p[1]:.5f}" for p in chunk)
    for attempt in range(5):
        data = json.loads(curl(url) or "{}")
        if data.get("status") == "OK":
            return [r["elevation"] for r in data["results"]]
        print("opentopodata retry", attempt, str(data)[:80], file=sys.stderr)
        time.sleep(10 * (attempt + 1))
    raise SystemExit("elevation API failed")


def elevations(points):
    # Open-Meteo counts every point as a call (fair use: 600 a minute), so go slowly.
    # Answers are kept in data/dl/ so a rerun only asks for new points.
    cache = json.load(open(ELEV_CACHE)) if os.path.exists(ELEV_CACHE) else {}
    key = lambda p: f"{p[0]:.5f},{p[1]:.5f}"
    todo = list(dict.fromkeys(key(p) for p in points if key(p) not in cache))
    daily = False
    for i in range(0, len(todo), 100):
        chunk = [tuple(map(float, k.split(","))) for k in todo[i:i + 100]]
        got = None
        for attempt in range(0 if daily else 20):
            data = json.loads(curl("https://api.open-meteo.com/v1/elevation?latitude=" + ",".join(f"{p[0]:.5f}" for p in chunk)
                                   + "&longitude=" + ",".join(f"{p[1]:.5f}" for p in chunk)) or "{}")
            if "elevation" in data:
                got = data["elevation"]
                break
            print("elevation retry", attempt, str(data)[:80], file=sys.stderr)
            if "Daily" in str(data.get("reason")):
                daily = True
                break
            # Over the hourly limit: wait for the next hour rather than give up
            time.sleep(300 if "Hourly" in str(data.get("reason")) else 20 * (attempt + 1))
        if got is None:
            got = topodata(chunk)
        cache.update(zip(todo[i:i + 100], got))
        os.makedirs(os.path.dirname(ELEV_CACHE), exist_ok=True)
        json.dump(cache, open(ELEV_CACHE, "w"))
        print(f"elevations {i + len(chunk)}/{len(todo)}", file=sys.stderr)
        time.sleep(2 if daily else 12)
    return [cache[key(p)] for p in points]


existing = json.load(open(opt.existing, encoding="utf-8")) if os.path.exists(opt.existing) else []
areas, lifts = [], []
for c in COUNTRIES:
    for e in overpass(f'[out:json][timeout:280];area["ISO3166-1"="{c}"][admin_level=2]->.a;'
                      f'nwr["landuse"="winter_sports"]["name"](area.a);out bb tags;'):
        b = e.get("bounds") or {"minlat": e.get("lat"), "maxlat": e.get("lat"), "minlon": e.get("lon"), "maxlon": e.get("lon")}
        if b["minlat"] is None:
            continue
        lat, lon = (b["minlat"] + b["maxlat"]) / 2, (b["minlon"] + b["maxlon"]) / 2
        if not opt.alps or inside(lon, lat, ALPS):
            areas.append({"name": e["tags"].get("name:en") or e["tags"]["name"], "lat": lat, "lon": lon, "bb": b,
                          "size": km(b["minlat"], b["minlon"], b["maxlat"], b["maxlon"]), "lifts": []})
    for w in overpass(f'[out:json][timeout:280];area["ISO3166-1"="{c}"][admin_level=2]->.a;'
                      f'way["aerialway"~"^({KINDS})$"](area.a);out geom;'):
        if len(w.get("geometry", [])) >= 2:
            lifts.append(w["geometry"])
    print(c, len(areas), "named ski areas,", len(lifts), "lifts so far", file=sys.stderr)
    time.sleep(5)

# A lift belongs to the biggest named area whose outline box holds it, so a linked domain (e.g. Ski Arlberg) gets all its
# lifts instead of losing them to its parts. Boxes over MAX_AREA_KM are umbrella names for several resorts
# (e.g. Les 3 Vallées): those only get lifts no smaller area holds (Courchevel and Méribel have no area of their own
# in OSM, Val Thorens does). A lift outside every box goes to the nearest area within 2.5 km.
MAX_AREA_KM = 30
def holds(b, m):
    return b["minlat"] - .002 <= m["lat"] <= b["maxlat"] + .002 and b["minlon"] - .003 <= m["lon"] <= b["maxlon"] + .003


for g in lifts:
    m = g[len(g) // 2]
    boxes = [a for a in areas if holds(a["bb"], m)]
    small = [a for a in boxes if a["size"] <= MAX_AREA_KM]
    if small or boxes:
        (max(small, key=lambda a: a["size"]) if small else min(boxes, key=lambda a: a["size"]))["lifts"].append(g)
        continue
    best = min(areas, key=lambda a: km(a["lat"], a["lon"], m["lat"], m["lon"]), default=None)
    if best and km(best["lat"], best["lon"], m["lat"], m["lon"]) <= 2.5:
        best["lifts"].append(g)

# Several OSM areas can share a name (e.g. two slopes of one resort): merge same-name areas within 5 km
merged = []
for a in sorted((a for a in areas if a["lifts"]), key=lambda a: -len(a["lifts"])):
    twin = next((b for b in merged if b["name"] == a["name"] and km(a["lat"], a["lon"], b["lat"], b["lon"]) < 5), None)
    if twin:
        twin["lifts"] += a["lifts"]
    else:
        merged.append(a)

def length(g):
    return sum(km(p["lat"], p["lon"], q["lat"], q["lon"]) for p, q in zip(g, g[1:]))


found = []
for a in merged:
    all_ends = [(g[0]["lat"], g[0]["lon"]) for g in a["lifts"]] + [(g[-1]["lat"], g[-1]["lon"]) for g in a["lifts"]]
    lat, lon = sum(p[0] for p in all_ends) / len(all_ends), sum(p[1] for p in all_ends) / len(all_ends)
    # Base/top from the ends of the 8 longest lifts: they span most of the vertical and keep the elevation calls down
    longest = sorted(a["lifts"], key=length, reverse=True)[:8]
    ends = [(g[0]["lat"], g[0]["lon"]) for g in longest] + [(g[-1]["lat"], g[-1]["lon"]) for g in longest]
    if any(km(lat, lon, r["lat"], r["lon"]) < 3 for r in existing + found):
        continue
    a.update(lat=round(lat, 3), lon=round(lon, 3), ends=ends, liftCount=len(a["lifts"]))
    found.append(a)
if opt.top:
    # Only the largest candidates need elevations; the vertical filter below then drops some more
    found = sorted(found, key=lambda a: -a["liftCount"])[:int(opt.top * 1.4)]
print(len(found), "new candidate areas, fetching elevations", file=sys.stderr)

flat = [p for a in found for p in a["ends"]]
el = iter(elevations(flat))
out = []
for a in found:
    e = [next(el) for _ in a["ends"]]
    base, top = int(round(min(e), -1)), int(round(max(e), -1))
    if top - base < opt.min_vert and a["liftCount"] < opt.min_lifts:
        continue
    out.append({"name": a["name"], "lat": a["lat"], "lon": a["lon"], "base": base, "top": top, "liftCount": a["liftCount"]})
# Size = lifts and vertical together, so both big linked areas and steep single valleys rank high
out.sort(key=lambda r: -(r["liftCount"] * 100 + (r["top"] - r["base"])))
if opt.top:
    out = out[:opt.top]
json.dump(out, open(opt.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(len(out), "resorts kept", file=sys.stderr)
