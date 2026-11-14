"""Fetch the car parks at each resort from OpenStreetMap, measured from the lifts rather than from the resort point.

Usage: python3 tools/fetch_parking.py index.html data/osm/lifts.json data/osm/pois.json [resort ids…]
Replaces the "Parkering…" rows in data/osm/pois.json (other rows are kept); then run tools/build_places.py.
Progress is kept in data/osm/parking_cache.json, so an interrupted run carries on where it stopped.

Most car parks at ski areas in OSM have neither a name nor a capacity, so the old rule (a name, or 50+ spaces)
left out nearly all of them. Now a car park is kept when:
  - it lies within 1 km of a lift (any point of a lift line), or is named or has 50+ spaces within 4 km of the
    resort, or (touring areas) lies within 2 km of the start;
  - it is not private, not along a street, not underground (hotel garages) and not tiny (< ~250 m², about 10 cars).
Car parks within 60 m of each other count as one (the larger is kept). Near a named lift (400 m) the row says
"vid <lift>".
"""
import json, math, os, re, subprocess, sys, time

html_path, lifts_path, pois_path = sys.argv[1:4]
only = set(sys.argv[4:])
html = open(html_path, encoding="utf-8").read()
resorts = []
for row in re.findall(r'^  \{id:"\w+".*\},$', html, re.M):
    g = lambda k: (re.search(r'(?<![a-z])' + k + r':([-\d.]+)', row) or [None, None])[1]
    rid = re.search(r'id:"(\w+)"', row)[1]
    if only and rid not in only: continue
    resorts.append({"id": rid, "lat": float(g("lat")), "lon": float(g("lon")),
                    "slat": float(g("slat")) if g("slat") else None, "slon": float(g("slon")) if g("slon") else None})
lifts = json.load(open(lifts_path, encoding="utf-8"))
cache_path = os.path.join(os.path.dirname(pois_path), "parking_cache.json")
cache = json.load(open(cache_path, encoding="utf-8")) if os.path.exists(cache_path) else {}
URLS = ["https://overpass-api.de/api/interpreter", "https://maps.mail.ru/osm/tools/overpass/api/interpreter"]
UA = "YukiReport/1.0 (personal ski trip app; github.com/borre-jacob/yuki-report)"


def km(a, b, c, d):
    t = math.radians
    h = math.sin(t(c - a) / 2) ** 2 + math.cos(t(a)) * math.cos(t(c)) * math.sin(t(d - b) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(min(1, h)))


def lift_pts(rid):
    """Every few points of every lift line, with the lift's name"""
    out = []
    for kind, name, pts in lifts.get(rid, []):
        step = max(1, len(pts) // 8)
        out += [(p[0], p[1], name or "") for p in pts[::step] + [pts[-1]]]
    return out


def area_m2(e):
    b = e.get("bounds")
    if not b: return None
    h = (b["maxlat"] - b["minlat"]) * 111000
    w = (b["maxlon"] - b["minlon"]) * 111000 * math.cos(math.radians(b["minlat"]))
    return h * w * 0.6   # a bounding box is larger than the car park itself


def query(parts):
    q = "[out:json][timeout:180];(" + "".join(parts) + ");out center tags bb;"
    for attempt in range(6):
        r = subprocess.run(["curl", "-s", "-m", "200", "-A", UA, URLS[attempt % 2], "--data-urlencode", "data=" + q],
                           capture_output=True, text=True)
        try:
            return json.loads(r.stdout)["elements"]
        except Exception:
            print("  retry", attempt, r.stdout[:60].replace("\n", " "), file=sys.stderr)
            time.sleep(15 * (attempt + 1))
    return None


def parts_for(r):
    lp = lift_pts(r["id"])
    out = [f'nwr["amenity"="parking"](around:4000,{r["lat"]},{r["lon"]});']
    if lp:
        la = [p[0] for p in lp]; lo = [p[1] for p in lp]
        out.append(f'nwr["amenity"="parking"]({min(la) - 0.01:.4f},{min(lo) - 0.02:.4f},{max(la) + 0.01:.4f},{max(lo) + 0.02:.4f});')
    if r["slat"]:
        out.append(f'nwr["amenity"="parking"](around:2000,{r["slat"]},{r["slon"]});')
    return out


def pick(r, els):
    lp = lift_pts(r["id"])
    cands = []
    for e in els:
        t = e.get("tags", {})
        b = e.get("bounds")   # with "out … bb" Overpass gives the bounds of areas but no centre
        la = e.get("lat") or e.get("center", {}).get("lat") or (b and (b["minlat"] + b["maxlat"]) / 2)
        lo = e.get("lon") or e.get("center", {}).get("lon") or (b and (b["minlon"] + b["maxlon"]) / 2)
        if la is None or t.get("amenity") != "parking": continue
        if t.get("access") in ("private", "no") or t.get("parking") in ("street_side", "lane", "underground", "garage_boxes", "carports", "rooftop"):
            continue
        name = t.get("name:en") or t.get("name") or ""
        cap = int(t["capacity"]) if t.get("capacity", "").isdigit() else None
        area = area_m2(e)
        if e["type"] == "node" and not name and not (cap and cap >= 20): continue
        if area is not None and area < 250 and not (cap and cap >= 10): continue
        near = min(((km(la, lo, p[0], p[1]), p[2]) for p in lp), default=(99, ""))
        d_res = km(r["lat"], r["lon"], la, lo)
        d_start = km(r["slat"], r["slon"], la, lo) if r["slat"] else 99
        if not (near[0] <= 1.0 or d_start <= 2.0 or (d_res <= 4 and (name or (cap and cap >= 50)))): continue
        sub = "Parkering" + (" · avgift" if t.get("fee") == "yes" else " · gratis" if t.get("fee") == "no" else "")
        if cap: sub += f" · {cap} platser"
        if near[0] <= 0.4 and near[1]: sub += f" · vid {near[1]}"
        size = cap or (area or 0) / 25
        cands.append((size, ["park", name, "", round(la, 5), round(lo, 5), sub, t.get("opening_hours", ""), round(d_res, 1)]))
    # One row per car park: those within 60 m of a larger one are left out
    kept = []
    for size, row in sorted(cands, key=lambda c: -c[0]):
        if all(km(row[3], row[4], k[3], k[4]) > 0.06 for k in kept): kept.append(row)
    return sorted(kept, key=lambda x: x[7])[:40]


todo = [r for r in resorts if r["id"] not in cache]
# A few resorts per query, grouped by place, to go easy on the Overpass servers
groups, group = [], []
for r in sorted(todo, key=lambda r: (round(r["lat"]), r["lon"])):
    if group and (len(group) >= 10 or km(group[0]["lat"], group[0]["lon"], r["lat"], r["lon"]) > 80):
        groups.append(group); group = []
    group.append(r)
if group: groups.append(group)
print(len(todo), "resorts in", len(groups), "queries", file=sys.stderr)
for n, g in enumerate(groups, 1):
    els = query([p for r in g for p in parts_for(r)])
    if els is None:
        print(n, "failed", [r["id"] for r in g], file=sys.stderr); continue
    for r in g:
        cache[r["id"]] = pick(r, els)
    json.dump(cache, open(cache_path, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(n, "/", len(groups), {r["id"]: len(cache[r["id"]]) for r in g}, file=sys.stderr)
    time.sleep(4)

# Into pois.json: the new car parks replace the old "Parkering…" rows; campsites, rest areas and the rest stay
pois = json.load(open(pois_path, encoding="utf-8"))
for rid, rows in cache.items():
    rest = [p for p in pois.get(rid, []) if not (p[0] == "park" and (p[5] or "").startswith("Parkering"))]
    pois[rid] = sorted(rest + rows, key=lambda x: x[7] if x[7] is not None else 99)
json.dump(pois, open(pois_path, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print("pois.json updated for", len(cache), "resorts", file=sys.stderr)
