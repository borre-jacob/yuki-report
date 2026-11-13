"""Split the OpenStreetMap data into one small file per resort, which the app loads when a resort is opened.

Usage: python3 tools/build_places.py data/osm/pois.json data/osm/lifts.json data/osm/places
Writes <dir>/<id>.json = {"pois": [...], "lifts": [...]} and <dir>/sizes.json = {id: bytes}, with only the
car parks (and onsen in Japan) within MAX_KM (10 km) of the resort,
which the app uses to say how much "Spara offline" downloads. Stale files for removed resorts are deleted.
Row formats are unchanged: see tools/fetch_pois.py and tools/fetch_lifts.py.
"""
import json, os, sys

import re
MAX_KM = 10   # facilities further from the resort than this are left out of the map
# The info map shows car parks everywhere and onsen in Japan; toilets, saunas outside Japan and overnight places
# (campsites, motorhome sites, rest areas, michi-no-eki) are left out. Japanese resorts have no area: in index.html.
html = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "index.html"), encoding="utf-8").read()
japan = {i for i, row in re.findall(r'^  \{id:"(\w+)"(.*)\},$', html, re.M) if 'area:"' not in row}
keep = lambda rid, p: p[0] == "park" and (p[5] or "").startswith("Parkering") or p[0] == "onsen" and rid in japan
pois = {rid: [p for p in rows if (p[7] is None or p[7] <= MAX_KM) and keep(rid, p)]
        for rid, rows in json.load(open(sys.argv[1], encoding="utf-8")).items()}
lifts = json.load(open(sys.argv[2], encoding="utf-8"))
out = sys.argv[3]
os.makedirs(out, exist_ok=True)

sizes = {}
for rid in sorted(set(pois) | set(lifts)):
    data = json.dumps({"pois": pois.get(rid, []), "lifts": lifts.get(rid, [])}, ensure_ascii=False, separators=(",", ":"))
    open(os.path.join(out, rid + ".json"), "w", encoding="utf-8").write(data)
    sizes[rid] = len(data.encode("utf-8"))

for f in os.listdir(out):
    if f.endswith(".json") and f != "sizes.json" and f[:-5] not in sizes:
        os.remove(os.path.join(out, f))
json.dump(sizes, open(os.path.join(out, "sizes.json"), "w", encoding="utf-8"), separators=(",", ":"))
print(len(sizes), "resorts,", sum(sizes.values()) // 1024, "kB in", out, file=sys.stderr)
