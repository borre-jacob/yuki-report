"""Find the webcams at each resort with the Windy Webcams API (run once a day on GitHub).

Usage: WINDY_KEY=... python3 tools/fetch_cams.py index.html data/osm/places data/cams
Writes <dir>/<area>.json = {"at": fetch time (UTC), "tpl": URL patterns, "resorts": {resort id: [cam]}}, where a
cam is {"id", "t": title, "a": height (m), "d": km to the nearest lift}. Its still image ("img"), day timelapse
player ("play") and page on windy.com ("url") are Windy's URLs as delivered; since they all follow one pattern with
the id in it, the pattern is stored once in "tpl" and a cam only carries a URL that differs from it.

Only webcams at most MAX_KM from a lift count (from the resort's point when it has no lifts), and only those
updated in the last week. At most four per resort, the highest first, since they show the snow best.
Heights come from Open-Meteo's elevation API (Windy gives none).
Without WINDY_KEY, or when the published files are younger than 20 hours, nothing is fetched and the files in
<dir> are kept (the workflow puts the published ones there first).
"""
import json, math, os, re, subprocess, sys, time
from datetime import datetime, timedelta, timezone

UA = "YukiReport/1.0 (ski trip app; github.com/borre-jacob/yuki-report)"
MAX_KM, MAX_CAMS = 3, 4
html = open(sys.argv[1], encoding="utf-8").read()
places_dir, out_dir = sys.argv[2], sys.argv[3]
os.makedirs(out_dir, exist_ok=True)
key = os.environ.get("WINDY_KEY", "").strip()
now = datetime.now(timezone.utc)

if not key:
    print("No WINDY_KEY, keeping the webcam files as they are", file=sys.stderr)
    sys.exit(0)
fresh = []
for fn in os.listdir(out_dir):
    try:
        at = datetime.fromisoformat(json.load(open(os.path.join(out_dir, fn)))["at"].replace("Z", "+00:00"))
        fresh.append(now - at < timedelta(hours=20))
    except Exception:
        fresh.append(False)
if fresh and all(fresh) and os.environ.get("CAMS_FORCE") != "1":
    print("Webcam files are less than 20 hours old, keeping them", file=sys.stderr)
    sys.exit(0)

resorts = []
for row in re.findall(r'^  \{id:"\w+".*\},$', html, re.M):
    f = {k: json.loads(v) for k, v in re.findall(r'(\w+):("[^"]*"|-?[\d.]+)', row)}
    resorts.append({"id": f["id"], "area": f.get("area", "japan"), "lat": f["lat"], "lon": f["lon"]})


def get(url, headers=()):
    args = ["curl", "-sS", "-m", "60", "-A", UA]
    for h in headers:
        args += ["-H", h]
    for attempt in range(3):
        p = subprocess.run(args + [url], capture_output=True, text=True)
        try:
            return json.loads(p.stdout)
        except Exception:
            print("retry", attempt, url[:80], p.stdout[:80], file=sys.stderr)
            time.sleep(5 * (attempt + 1))
    return None


def km(a, b, c, d):
    x = math.sin(math.radians(c - a) / 2) ** 2 + math.cos(math.radians(a)) * math.cos(math.radians(c)) * math.sin(math.radians(d - b) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(x))


def seg_km(p, a, b):
    """Distance from point p to the segment a–b, in a flat projection around p (fine at these distances)."""
    k = math.cos(math.radians(p[0]))
    ax, ay, bx, by = (a[1] - p[1]) * k, a[0] - p[0], (b[1] - p[1]) * k, b[0] - p[0]
    dx, dy = bx - ax, by - ay
    t = 0 if dx == dy == 0 else max(0, min(1, -(ax * dx + ay * dy) / (dx * dx + dy * dy)))
    return math.hypot(ax + t * dx, ay + t * dy) * 111.2


def lift_lines(rid):
    try:
        d = json.load(open(os.path.join(places_dir, rid + ".json")))
    except Exception:
        return []
    return [l[2] for l in d.get("lifts", []) if len(l) > 2 and len(l[2]) >= 2]


out, cams_all = {}, {}
for n, r in enumerate(resorts):
    lines = lift_lines(r["id"])
    pts = [p for ln in lines for p in ln] or [[r["lat"], r["lon"]]]
    reach = max(km(r["lat"], r["lon"], p[0], p[1]) for p in pts) + MAX_KM
    radius = min(50, math.ceil(reach))
    d = get(f"https://api.windy.com/webcams/api/v3/webcams?nearby={r['lat']},{r['lon']},{radius}&limit=50"
            "&include=location,player,urls,images", [f"x-windy-api-key: {key}"])
    time.sleep(0.3)
    if d is None or "webcams" not in d:
        print("windy failed for", r["id"], str(d)[:100], file=sys.stderr)
        continue
    found = []
    for w in d["webcams"]:
        loc, img = w.get("location") or {}, (w.get("images") or {}).get("current") or {}
        if w.get("status") != "active" or not img.get("preview") or "latitude" not in loc:
            continue
        up = w.get("lastUpdatedOn")
        if up and now - datetime.fromisoformat(up.replace("Z", "+00:00")) > timedelta(days=7):
            continue
        p = (loc["latitude"], loc["longitude"])
        dist = min(seg_km(p, a, b) for ln in lines for a, b in zip(ln, ln[1:])) if lines else km(r["lat"], r["lon"], *p)
        if dist > MAX_KM:
            continue
        cid = str(w["webcamId"])
        cams_all[cid] = {"lat": p[0], "lon": p[1]}
        found.append({"id": cid, "t": w.get("title", ""), "d": round(dist, 1), "img": img["preview"],
                      "play": (w.get("player") or {}).get("day"), "url": (w.get("urls") or {}).get("detail")})
    if found:
        out.setdefault(r["area"], {})[r["id"]] = found
    if n % 50 == 0:
        print(n, "resorts done", file=sys.stderr)

# Heights for every camera, 100 at a time
ids = list(cams_all)
for i in range(0, len(ids), 100):
    part = ids[i:i + 100]
    url = ("https://api.open-meteo.com/v1/elevation?latitude=" + ",".join(str(cams_all[c]["lat"]) for c in part)
           + "&longitude=" + ",".join(str(cams_all[c]["lon"]) for c in part))
    for attempt in range(4):
        e = get(url) or {}
        if "elevation" in e:
            break
        print("elevation:", str(e.get("reason", e))[:80], file=sys.stderr)
        time.sleep(65)   # Open-Meteo limits calls per minute
    time.sleep(2)
    for c, h in zip(part, e.get("elevation", [])):
        cams_all[c]["a"] = round(h)

# Windy's URLs follow one pattern per kind with the webcam id in them. Each file stores the pattern once ("tpl",
# with {id} for the id) and a camera only keeps a URL of its own when it does not follow the pattern.
KINDS = ("img", "play", "url")
tpl = {}
for k in KINDS:
    seen = {}
    for cams in (c for a in out.values() for cs in a.values() for c in cs):
        if cams.get(k) and cams["id"] in cams[k]:
            pat = cams[k].replace(cams["id"], "{id}")
            seen[pat] = seen.get(pat, 0) + 1
    if seen:
        tpl[k] = max(seen, key=seen.get)

at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
for area in sorted({r["area"] for r in resorts}):
    res = {}
    for rid, cams in out.get(area, {}).items():
        best = sorted(cams, key=lambda c: -(cams_all[c["id"]].get("a") or 0))[:MAX_CAMS]
        res[rid] = []
        for c in best:
            o = {"id": c["id"], "t": c["t"], "a": cams_all[c["id"]].get("a"), "d": c["d"]}
            for k in KINDS:
                if c.get(k) and c[k] != tpl.get(k, "").replace("{id}", c["id"]):
                    o[k] = c[k]
            res[rid].append(o)
    json.dump({"at": at, "tpl": tpl, "resorts": res}, open(os.path.join(out_dir, area + ".json"), "w"),
              separators=(",", ":"), ensure_ascii=False)
    print(area, len(res), "resorts with webcams,", sum(len(v) for v in res.values()), "cams", file=sys.stderr)
