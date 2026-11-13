"""Fetch facilities for many resorts at once (groups of nearby resorts per Overpass query).

Usage: python3 tools/fetch_pois_batch.py index.html data/osm/pois.json [resorts per query, default 8]
Same output rows as tools/fetch_pois.py; resorts already in data/osm/pois.json are skipped.
Radii: 10 km for toilets, saunas/baths and overnight places, 4 km for car parks (the map shows 10 km).
"""
import json, math, os, re, subprocess, sys, time

html = open(sys.argv[1], encoding="utf-8").read()
out_path = sys.argv[2]
resorts = [(i, float(a), float(b)) for i, a, b in
           re.findall(r'\{id:"(\w+)",name:"[^"]+",jp:"[^"]*",region:"[^"]+",lat:([\d.]+),lon:([\d.]+)', html)]
result = json.load(open(out_path, encoding="utf-8")) if os.path.exists(out_path) else {}
todo = [r for r in resorts if r[0] not in result]
URLS = ["https://maps.mail.ru/osm/tools/overpass/api/interpreter", "https://overpass-api.de/api/interpreter"]
PER_QUERY = int(sys.argv[3]) if len(sys.argv) > 3 else 8  # fewer when the servers are busy and time out
UA = "YukiReport/1.0 (personal ski trip app; github.com/borre-jacob/yuki-report)"

# Reuse the classification rules from fetch_pois.py
src = open(os.path.join(os.path.dirname(__file__), "fetch_pois.py"), encoding="utf-8").read()
ns = {"re": re, "math": math}
exec(src[src.index("def dist"):src.index("for rid, lat, lon in resorts")], ns)
classify, dist = ns["classify"], ns["dist"]
RADIUS = {"toilet": 10, "onsen": 10, "park": 10}


def query(group):
    parts = []
    for _, la, lo in group:
        a = lambda r: f"(around:{r},{la},{lo})"
        parts += [f'nwr["amenity"="public_bath"]{a(30000)};', f'nwr["leisure"="sauna"]["access"!="private"]{a(30000)};',
                  f'nwr["leisure"="water_park"]{a(30000)};', f'nwr["amenity"="toilets"]{a(12000)};',
                  f'nwr["highway"~"^(rest_area|services)$"]{a(30000)};', f'nwr["tourism"~"^(caravan_site|camp_site)$"]{a(30000)};',
                  f'nwr["amenity"="parking"]{a(4000)};']
    q = "[out:json][timeout:240];(" + "".join(parts) + ");out center tags;"
    for attempt in range(6):
        r = subprocess.run(["curl", "-s", "-m", "260", "-A", UA, URLS[attempt % 2], "--data-urlencode", "data=" + q],
                           capture_output=True, text=True)
        try:
            return json.loads(r.stdout)["elements"]
        except Exception:
            print("retry", attempt, r.stdout[:60].replace("\n", " "), file=sys.stderr)
            time.sleep(15 * (attempt + 1))
    return None


# Group nearby resorts (greedy, within ~60 km, at most PER_QUERY per query)
groups = []
for r in sorted(todo, key=lambda r: (round(r[1]), r[2])):
    g = next((g for g in groups if len(g) < PER_QUERY and dist(g[0][1], g[0][2], r[1], r[2]) < 60), None)
    (g.append(r) if g else groups.append([r]))
print(len(todo), "resorts in", len(groups), "queries", file=sys.stderr)

for n, group in enumerate(groups, 1):
    els = query(group)
    if els is None:
        print("group failed:", [g[0] for g in group], file=sys.stderr)
        continue
    for rid, lat, lon in group:
        seen, items = set(), []
        for e in els:
            t = e.get("tags", {}); la = e.get("lat") or e.get("center", {}).get("lat"); lo = e.get("lon") or e.get("center", {}).get("lon")
            if la is None: continue
            c = classify(t)
            if not c: continue
            typ, sub = c
            d = dist(lat, lon, la, lo)
            if d > (4 if t.get("amenity") == "parking" else RADIUS[typ]): continue
            name = t.get("name:en") or t.get("name") or ""
            key = typ + "|" + (name or f"{la:.4f},{lo:.4f}")
            if key in seen: continue
            seen.add(key)
            jp = t.get("name", "") if t.get("name:en") and t.get("name") != t.get("name:en") else ""
            web = t.get("website") or t.get("contact:website") or ""
            phone = (t.get("phone") or t.get("contact:phone") or "").split(";")[0].strip()
            items.append([typ, name, jp, round(la, 5), round(lo, 5), sub, t.get("opening_hours", ""), round(d, 1), web, phone])
        items.sort(key=lambda x: x[7])
        result[rid] = items
    json.dump(result, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"{n}/{len(groups)}", [(g[0], len(result[g[0]])) for g in group], file=sys.stderr)
    time.sleep(3)
