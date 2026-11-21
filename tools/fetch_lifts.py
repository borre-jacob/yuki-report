"""Fetch which lifts are open and when the season opens, for the Norwegian resorts, from Fnugg (run with the snow data on GitHub).

Usage: python3 tools/fetch_lifts.py index.html data/lifts
Writes <dir>/norway.json = {"at": fetch time (UTC), "source": "fnugg.no", "resorts": {resort id: {...}}} where a resort is
{"open": lifts open, "count": lifts in all, "path": Fnugg's page for the resort, "isOpen": the resort's open flag, "opens": "YYYY-MM-DD", "closes": "YYYY-MM-DD", "upd": Fnugg's update time}.
Fnugg (https://api.fnugg.no/docs/v1) is Norway's ski status service; its terms ask for a credit to fnugg.no wherever the data is
shown (the app does that) and forbid copying fnugg.no itself. One request lists every resort; each of ours is matched to the
nearest Fnugg resort within MAX_KM. Without an answer the file already in <dir> is kept (the workflow puts the published one there).
"""
import json, math, os, re, subprocess, sys
from datetime import datetime, timezone

UA = "YukiReport/1.0 (ski trip app; github.com/borre-jacob/yuki-report)"
MAX_KM = 4
html = open(sys.argv[1], encoding="utf-8").read()
out_dir = sys.argv[2]
os.makedirs(out_dir, exist_ok=True)

ours = []
for row in re.findall(r'^  \{id:"\w+".*\},$', html, re.M):
    f = dict(re.findall(r'(\w+):("[^"]*"|-?[\d.]+)', row))
    if json.loads(f.get("country", '""')) == "Norge" and "kind" not in f:   # not the ski tours
        ours.append({"id": json.loads(f["id"]), "name": json.loads(f["name"]), "lat": float(f["lat"]), "lon": float(f["lon"])})


def km(a, b, c, d):
    p1, p2 = math.radians(a), math.radians(c)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(d - b) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


raw = subprocess.run(["curl", "-sS", "-m", "60", "-A", UA, "https://api.fnugg.no/search?q=&size=300"], capture_output=True, text=True).stdout
try:
    hits = [h["_source"] for h in json.loads(raw)["hits"]["hits"] if h.get("_type") == "resort"]
    assert hits
except Exception as e:
    print("No answer from Fnugg, keeping the file as it is:", str(e)[:100], file=sys.stderr)
    sys.exit(0)

day = lambda s: (s or "")[:10] or None
res = {}
for r in ours:
    best = min(((km(r["lat"], r["lon"], h["location"]["lat"], h["location"]["lon"]), h) for h in hits if h.get("location")), key=lambda x: x[0], default=None)
    if not best or best[0] > MAX_KM:
        continue
    h = best[1]
    lifts = h.get("lifts") or {}
    res[r["id"]] = {"fnugg": h.get("name"), "path": h.get("site_path"), "open": lifts.get("open", 0), "count": lifts.get("count", 0), "isOpen": bool(h.get("resort_open")),
                    "opens": day(h.get("resort_opening_date")), "closes": day(h.get("resort_closing_date")), "upd": h.get("last_updated")}
at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
json.dump({"at": at, "source": "fnugg.no", "resorts": res}, open(os.path.join(out_dir, "norway.json"), "w"), separators=(",", ":"), ensure_ascii=False)
print(len(res), "of", len(ours), "Norwegian resorts matched,", len(hits), "in Fnugg", file=sys.stderr)
