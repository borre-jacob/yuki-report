"""Place new resorts precisely from their lifts in OpenStreetMap.

Usage: python3 tools/refine_resorts.py in.json out.json
in.json:  [{"id", "name", "region", "lat", "lon"}, ...]   (approximate centre)
out.json: same rows with lat/lon moved to the centre of the lifts within 5 km,
          base/top = lowest/highest lift station (Open-Meteo elevation data) and liftCount.
"""
import json, subprocess, sys, time

KINDS = "chair_lift|gondola|cable_car|mixed_lift|drag_lift|t-bar|j-bar|platter|rope_tow"
UA = "YukiReport/1.0 (personal ski trip app; github.com/borre-jacob/yuki-report)"
OVERPASS = ["https://maps.mail.ru/osm/tools/overpass/api/interpreter", "https://overpass-api.de/api/interpreter"]


def curl(url, data=None):
    cmd = ["curl", "-sS", "-m", "180", "-A", UA, url]
    if data:
        cmd += ["--data-urlencode", "data=" + data]
    return subprocess.run(cmd, capture_output=True, text=True).stdout


def overpass(q):
    for attempt in range(6):
        try:
            return json.loads(curl(OVERPASS[attempt % 2], q))
        except Exception:
            time.sleep(10 * (attempt + 1))
    raise SystemExit("Overpass failed")


def elevations(points):
    out = []
    for i in range(0, len(points), 100):
        chunk = points[i:i + 100]
        url = ("https://api.open-meteo.com/v1/elevation?latitude=" + ",".join(f"{p[0]:.5f}" for p in chunk)
               + "&longitude=" + ",".join(f"{p[1]:.5f}" for p in chunk))
        for attempt in range(6):
            data = json.loads(curl(url) or "{}")
            if "elevation" in data:
                out += data["elevation"]
                break
            time.sleep(5 * (attempt + 1))  # rate limited, wait and retry
        else:
            raise SystemExit("elevation API failed")
        time.sleep(1)
    return out


rows = json.load(open(sys.argv[1], encoding="utf-8"))
q = "[out:json][timeout:170];(" + "".join(
    f'way["aerialway"~"^({KINDS})$"](around:5000,{r["lat"]},{r["lon"]});' for r in rows) + ");out geom;"
ways = [w for w in overpass(q)["elements"] if len(w.get("geometry", [])) >= 2]

for r in rows:
    near = []
    for w in ways:
        g = w["geometry"]; m = g[len(g) // 2]
        if abs(m["lat"] - r["lat"]) < 0.045 and abs(m["lon"] - r["lon"]) < 0.045 / max(0.2, abs(__import__("math").cos(__import__("math").radians(r["lat"])))):
            near.append(g)
    r["liftCount"] = len(near)
    if not near:
        print("NO LIFTS", r["id"], file=sys.stderr)
        continue
    ends = [(g[0]["lat"], g[0]["lon"]) for g in near] + [(g[-1]["lat"], g[-1]["lon"]) for g in near]
    r["lat"] = round(sum(p[0] for p in ends) / len(ends), 3)
    r["lon"] = round(sum(p[1] for p in ends) / len(ends), 3)
    el = elevations(ends)
    r["base"], r["top"] = int(round(min(el), -1)), int(round(max(el), -1))
    print(r["id"], r["liftCount"], "lifts", r["lat"], r["lon"], r["base"], "-", r["top"], file=sys.stderr)

json.dump(rows, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
