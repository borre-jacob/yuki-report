"""Fetch ski lift lines around every resort.

Usage: python3 tools/fetch_lifts.py index.html data/osm/lifts.json [resorts per query, default 20]
Resorts already in data/osm/lifts.json with lifts are kept; the rest are fetched in groups (20 unless given; fewer when the servers are busy)
(one Overpass query for all resorts at once is too big for the servers).
"""
import json, math, os, re, subprocess, sys, time

html = open(sys.argv[1], encoding="utf-8").read()
resorts = [(i, float(a), float(b)) for i, a, b in re.findall(r'\{id:"(\w+)",name:"[^"]+",jp:"[^"]*",region:"[^"]+",lat:([\d.]+),lon:([\d.]+)', html)]
KINDS = "chair_lift|gondola|cable_car|mixed_lift|drag_lift|t-bar|j-bar|platter|rope_tow|magic_carpet"
URLS = ["https://maps.mail.ru/osm/tools/overpass/api/interpreter", "https://overpass-api.de/api/interpreter"]
out = json.load(open(sys.argv[2], encoding="utf-8")) if os.path.exists(sys.argv[2]) else {}
todo = [r for r in resorts if not out.get(r[0])]


def dist(a, b, c, d):
    t = math.radians; h = math.sin(t(c-a)/2)**2 + math.cos(t(a))*math.cos(t(c))*math.sin(t(d-b)/2)**2
    return 2*6371*math.asin(math.sqrt(h))


def fetch(group):
    q = "[out:json][timeout:170];(" + "".join(f'way["aerialway"~"^({KINDS})$"](around:7000,{la},{lo});' for _, la, lo in group) + ");out geom tags;"
    for attempt in range(6):
        r = subprocess.run(["curl", "-s", "-m", "200", "-A", "YukiReport/1.0 (personal ski trip planner)", URLS[attempt % 2],
                            "--data-urlencode", "data=" + q], capture_output=True, text=True)
        try:
            return json.loads(r.stdout)["elements"]
        except Exception:
            print("retry", attempt, file=sys.stderr); time.sleep(15 * (attempt + 1))
    return None


GROUP = int(sys.argv[3]) if len(sys.argv) > 3 else 20
todo.sort(key=lambda r: (round(r[1]), r[2]))
for n in range(0, len(todo), GROUP):
    group = todo[n:n + GROUP]
    els = fetch(group)
    if els is None:
        print("group failed:", [g[0] for g in group], file=sys.stderr); continue
    for rid, la, lo in group:
        out[rid] = []
        for w in els:
            g = w.get("geometry") or []
            if len(g) < 2: continue
            pts = [[round(p["lat"], 5), round(p["lon"], 5)] for p in g]
            mid = pts[len(pts)//2]
            if dist(la, lo, mid[0], mid[1]) <= 7.5:
                t = w.get("tags", {})
                out[rid].append([t["aerialway"], t.get("name:en") or t.get("name") or "", pts])
    json.dump(out, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"{n + len(group)}/{len(todo)}", [(g[0], len(out[g[0]])) for g in group], file=sys.stderr)
    time.sleep(3)
