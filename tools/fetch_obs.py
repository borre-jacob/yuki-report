"""Fetch measured snow depth from weather stations near each resort (run every few hours on GitHub).

Usage: python3 tools/fetch_obs.py index.html data/obs
Writes <dir>/<area>.json = {"at": fetch time (UTC), "stations": {id: station}, "resorts": {resort id: [station id]}}.
A station is {"n": name, "a": height (m), "src": source, "t0": first time (UTC, ISO hour), "dt": hours between
values, "v": snow depth in cm (null where missing)}, about the last 7 days.

Sources, all open and without keys:
  Japan        JMA AMeDAS (snow depth every hour; history from the hourly map files)
  Switzerland  SLF IMIS (automatic stations in the mountains, every 30 min; the bulk call gives 24 h, so a station
               without history in the previous file gets its week in a call of its own)
  Austria      GeoSphere Austria TAWES (every 10 min)
  Sweden       SMHI (one depth a day, mostly measured in the morning)
  Finland      FMI (automatic snow depth)
  Norway       MET Norway Frost (needs a free client ID in the environment variable FROST_CLIENT_ID; without it
               Norway is skipped)
France and Italy have no station source yet.

A resort gets a station only when one stands in the ski area: at most 3 km from a lift (lifts from
data/osm/places) and between 50 m below the base and 100 m above the top; the highest such station is used. The app
shows its reading as the resort's snow depth, and the model's estimate where there is none. The workflow puts the published files in <dir> first, so history that a
source only gives for a short time (JMA, SLF) is kept between runs, and a source that fails keeps its data.
"""
import json, math, os, re, subprocess, sys, time
from datetime import datetime, timedelta, timezone

UA = "YukiReport/1.0 (ski trip app; github.com/borre-jacob/yuki-report)"
DAYS = 7
html = open(sys.argv[1], encoding="utf-8").read()
out_dir = sys.argv[2]
os.makedirs(out_dir, exist_ok=True)
NOW = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
START = NOW - timedelta(days=DAYS)
CC = {"Sverige": "SE", "Norge": "NO", "Finland": "FI", "Österrike": "AT", "Schweiz": "CH", "Frankrike": "FR", "Italien": "IT"}

resorts = []
for row in re.findall(r'^  \{id:"\w+".*\},$', html, re.M):
    f = {k: json.loads(v) for k, v in re.findall(r'(\w+):("[^"]*"|-?[\d.]+)', row)}
    resorts.append({"id": f["id"], "area": f.get("area", "japan"), "cc": CC.get(f.get("country"), "JP"),
                    "lat": f["lat"], "lon": f["lon"], "base": f["base"], "top": f["top"]})


def get(url, tries=3):
    for attempt in range(tries):
        p = subprocess.run(["curl", "-sSf", "-m", "90", "-A", UA, url], capture_output=True, text=True)
        if p.returncode == 0:
            return p.stdout
        print("retry", attempt, url[:90], p.stderr[:80], file=sys.stderr)
        time.sleep(10 * (attempt + 1))
    return None


def km(a, b, c, d):
    x = math.sin(math.radians(c - a) / 2) ** 2 + math.cos(math.radians(a)) * math.cos(math.radians(c)) * math.sin(math.radians(d - b) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(x))


def iso(t):
    return t.strftime("%Y-%m-%dT%H:00Z")


def parse(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


# Previous files: the history of every station, keyed "src:id"
prev = {}
for fn in os.listdir(out_dir):
    if not fn.endswith(".json"):
        continue
    try:
        d = json.load(open(os.path.join(out_dir, fn)))
    except Exception:
        continue
    for sid, s in d.get("stations", {}).items():
        t0 = parse(s["t0"])
        prev[sid] = {iso(t0 + timedelta(hours=s["dt"] * i)): v for i, v in enumerate(s["v"]) if v is not None}

stations = {}   # "src:id" -> {"n", "a", "lat", "lon", "src", "cc", "dt", "ser": {iso hour: cm}}


def add(src, sid, name, alt, lat, lon, cc, dt=3):
    key = f"{src}:{sid}"
    stations[key] = {"n": name, "a": None if alt is None else round(alt), "lat": lat, "lon": lon, "src": src,
                     "cc": cc, "dt": dt, "ser": dict(prev.get(key, {}))}
    return stations[key]


def on_grid(t, dt=3):
    return t.minute == 0 and t.hour % dt == 0


# --- Japan: JMA AMeDAS. The map file for one hour has every station; take one every 3 hours (JST, = UTC+9).
def jma():
    table = json.loads(get("https://www.jma.go.jp/bosai/amedas/const/amedastable.json") or "{}")
    latest = (get("https://www.jma.go.jp/bosai/amedas/data/latest_time.txt") or "").strip()
    if not table or not latest:
        raise RuntimeError("JMA station list or time missing")
    last = parse(latest).astimezone(timezone.utc).replace(minute=0)
    last -= timedelta(hours=last.hour % 3)
    t, slots = last, []
    while t >= START:
        slots.append(t)
        t -= timedelta(hours=3)
    known = {}
    for k in list(prev):
        if k.startswith("jma:"):
            known[k] = prev[k]
    fetched = 0
    for t in slots:
        key = iso(t)
        if t != last and known and all(key in v for v in known.values()):
            continue   # already have this hour from an earlier run
        jst = t + timedelta(hours=9)
        raw = get(f"https://www.jma.go.jp/bosai/amedas/data/map/{jst.strftime('%Y%m%d%H')}0000.json")
        fetched += 1
        if not raw:
            continue
        for sid, v in json.loads(raw).items():
            if "snow" not in v or sid not in table:
                continue
            s = stations.get("jma:" + sid)
            if not s:
                m = table[sid]
                s = add("jma", sid, m["enName"], m["alt"], m["lat"][0] + m["lat"][1] / 60, m["lon"][0] + m["lon"][1] / 60, "JP")
            val, flag = v["snow"]
            if val is not None and flag == 0:
                s["ser"][key] = val
    print("jma", len(stations), "stations,", fetched, "map files", file=sys.stderr)


# --- Switzerland: SLF IMIS. One call has the last 24 hours of every station.
def slf():
    meta = json.loads(get("https://measurement-api.slf.ch/public/api/imis/stations") or "[]")
    meta = {m["code"]: m for m in meta if m.get("type") != "WIND"}
    data = json.loads(get("https://measurement-api.slf.ch/public/api/imis/measurements") or "[]")
    if not meta or not data:
        raise RuntimeError("SLF answered nothing")
    for m in meta.values():
        add("slf", m["code"], m["label"], m["elevation"], m["lat"], m["lon"], "CH")
    rows = list(data)
    # The bulk call only covers 24 hours. A station a resort uses and whose history is short gets the week in one call.
    ch = [s for k, s in stations.items() if k.startswith("slf:")]
    used = {id(x) for r in resorts if r["cc"] == "CH" for x in pick(r, ch)}
    for k, s in stations.items():
        if k.startswith("slf:") and id(s) in used and not any(parse(t) < NOW - timedelta(hours=60) for t in s["ser"]):
            rows += json.loads(get(f"https://measurement-api.slf.ch/public/api/imis/station/{k[4:]}/measurements?period_in_days={DAYS}") or "[]")
    for row in rows:
        s = stations.get("slf:" + row.get("station_code", ""))
        t = parse(row["measure_date"])
        if s and on_grid(t) and row.get("HS") is not None and row["HS"] >= 0:
            s["ser"][iso(t)] = round(row["HS"])


# --- Austria: GeoSphere TAWES, 10-minute values, the whole week in one call
def geosphere():
    meta = json.loads(get("https://dataset.api.hub.geosphere.at/v1/station/current/tawes-v1-10min/metadata") or "{}")
    act = [m for m in meta.get("stations", []) if m.get("is_active")]
    if not act:
        raise RuntimeError("GeoSphere station list missing")
    url = ("https://dataset.api.hub.geosphere.at/v1/station/historical/tawes-v1-10min?parameters=SCHNEE&station_ids="
           + ",".join(m["id"] for m in act) + f"&start={START.strftime('%Y-%m-%dT%H:%M')}&end={NOW.strftime('%Y-%m-%dT%H:%M')}")
    d = json.loads(get(url) or "{}")
    ts = [parse(t) for t in d.get("timestamps", [])]
    by = {m["id"]: m for m in act}
    for f in d.get("features", []):
        sid = f["properties"]["station"]
        vals = f["properties"]["parameters"]["SCHNEE"]["data"]
        if all(v is None for v in vals):
            continue
        m = by[sid]
        s = add("geo", sid, m["name"].title(), m["altitude"], m["lat"], m["lon"], "AT")
        for t, v in zip(ts, vals):
            if v is not None and on_grid(t) and v >= 0:
                s["ser"][iso(t)] = round(v)


# --- Finland: FMI, automatic snow depth every 3 hours (the open service gives at most 168 hours per call)
def fmi():
    names = {}
    x = get("https://opendata.fmi.fi/wfs?service=WFS&version=2.0.0&request=getFeature&storedquery_id=fmi::ef::stations") or ""
    for blk in x.split("<ef:EnvironmentalMonitoringFacility")[1:]:
        p = re.search(r"<gml:pos>([\d.]+) ([\d.]+)", blk)
        n = re.search(r"<ef:name>([^<]*)", blk)
        i = re.search(r'<gml:identifier codeSpace="[^"]*">(\d+)', blk)
        if p and n and i:
            names[(round(float(p[1]), 4), round(float(p[2]), 4))] = (i[1], n[1])
    st = NOW - timedelta(hours=165)
    st -= timedelta(hours=st.hour % 3)
    x = get("https://opendata.fmi.fi/wfs?service=WFS&version=2.0.0&request=getFeature&storedquery_id=fmi::observations::weather::simple"
            f"&bbox=19,59.5,32,70.2&parameters=snow_aws&timestep=180&starttime={st.strftime('%Y-%m-%dT%H:00:00Z')}&endtime={NOW.strftime('%Y-%m-%dT%H:00:00Z')}")
    if not x:
        raise RuntimeError("FMI answered nothing")
    for el in re.findall(r"<BsWfs:BsWfsElement.*?</BsWfs:BsWfsElement>", x, re.S):
        p = re.search(r"<gml:pos>([\d.]+) ([\d.]+)", el)
        t = re.search(r"<BsWfs:Time>([^<]+)", el)
        v = re.search(r"<BsWfs:ParameterValue>([^<]+)", el)
        if not (p and t and v) or v[1] == "NaN":
            continue
        lat, lon = float(p[1]), float(p[2])
        sid, name = names.get((round(lat, 4), round(lon, 4)), (f"{lat:.3f},{lon:.3f}", f"{lat:.2f}, {lon:.2f}"))
        s = stations.get("fmi:" + sid) or add("fmi", sid, name, None, lat, lon, "FI")
        val = float(v[1])
        if val >= 0:
            s["ser"][iso(parse(t[1]))] = round(val)


# --- Sweden: SMHI, one depth a day. Only the stations that some resort will use are asked (one call each).
def smhi():
    lst = json.loads(get("https://opendata-download-metobs.smhi.se/api/version/1.0/parameter/8.json") or "{}")
    act = [m for m in lst.get("station", []) if m.get("active")]
    if not act:
        raise RuntimeError("SMHI station list missing")
    cands = {str(m["id"]): add("smhi", str(m["id"]), m["name"], m["height"], m["latitude"], m["longitude"], "SE", dt=24) for m in act}
    used = set()
    for r in resorts:
        if r["cc"] == "SE":
            used.update(id(s) for s in pick(r, cands.values()))
    for sid, s in cands.items():
        if id(s) not in used:
            del stations["smhi:" + sid]
            continue
        d = json.loads(get(f"https://opendata-download-metobs.smhi.se/api/version/1.0/parameter/8/station/{sid}/period/latest-months/data.json") or "{}")
        for row in d.get("value", []):
            t = datetime.fromtimestamp(row["date"] / 1000, timezone.utc)
            if t >= START - timedelta(days=1) and row.get("value") not in (None, ""):
                s["ser"][iso(t)] = round(float(row["value"]) * 100)


# --- Norway: MET Norway Frost. Stations that measured snow depth in the last week, then their values.
def frost():
    cid = os.environ.get("FROST_CLIENT_ID", "").strip()
    if not cid:
        print("frost: no FROST_CLIENT_ID, Norway skipped", file=sys.stderr)
        return
    def fget(path):
        p = subprocess.run(["curl", "-sS", "-m", "90", "-A", UA, "-u", cid + ":", "https://frost.met.no/" + path],
                           capture_output=True, text=True)
        try:
            return json.loads(p.stdout)
        except Exception:
            return {}
    span = f"{START.strftime('%Y-%m-%dT%H:%M')}/{NOW.strftime('%Y-%m-%dT%H:%M')}"
    avail = fget(f"observations/availableTimeSeries/v0.jsonld?elements=surface_snow_thickness&referencetime={span}")
    ids = sorted({a["sourceId"].split(":")[0] for a in avail.get("data", [])})
    if not ids:
        raise RuntimeError("Frost: no stations with snow depth " + str(avail.get("error", ""))[:120])
    meta = {}
    for i in range(0, len(ids), 100):
        for m in fget("sources/v0.jsonld?ids=" + ",".join(ids[i:i + 100])).get("data", []):
            if m.get("geometry") and m.get("country", "Norge") in ("Norge", "Norway", "NO"):
                meta[m["id"]] = m
    cands = {sid: add("met", sid, m.get("shortName") or m["name"].title(), m.get("masl"),
                      m["geometry"]["coordinates"][1], m["geometry"]["coordinates"][0], "NO", dt=24) for sid, m in meta.items()}
    used = {id(x) for r in resorts if r["cc"] == "NO" for x in pick(r, cands.values())}
    keep = [sid for sid, s in cands.items() if id(s) in used]
    for sid in set(cands) - set(keep):
        del stations["met:" + sid]
    for i in range(0, len(keep), 50):
        d = fget("observations/v0.jsonld?elements=surface_snow_thickness&referencetime=" + span
                 + "&sources=" + ",".join(keep[i:i + 50]))
        for row in d.get("data", []):
            s = stations.get("met:" + row["sourceId"].split(":")[0])
            t = parse(row["referenceTime"])
            for o in row.get("observations", []):
                v = o.get("value")
                if s is None or v is None or v < 0:
                    continue
                if t.minute == 0:
                    s["ser"][iso(t)] = round(v)
    # A station with more than one reading a day is automatic and shown every 3 hours; a manual one gets its
    # daily reading at 06 UTC, so all of them share one grid
    for sid in keep:
        s = stations["met:" + sid]
        days = {k[:10] for k in s["ser"]}
        if len(s["ser"]) > len(days) * 1.5:
            s["dt"] = 3
            s["ser"] = {k: v for k, v in s["ser"].items() if parse(k).hour % 3 == 0}
        else:
            s["ser"] = {k[:10] + "T06:00Z": v for k, v in sorted(s["ser"].items())}


PLACES = os.path.join(os.path.dirname(os.path.abspath(sys.argv[1])), "data", "osm", "places")
MAX_KM = 3
_lines = {}


def lift_lines(rid):
    if rid not in _lines:
        try:
            d = json.load(open(os.path.join(PLACES, rid + ".json")))
            _lines[rid] = [l[2] for l in d.get("lifts", []) if len(l) > 2 and len(l[2]) >= 2]
        except Exception:
            _lines[rid] = []
    return _lines[rid]


def seg_km(p, a, b):
    """Distance from point p to the segment a–b, in a flat projection around p (fine at these distances)."""
    k = math.cos(math.radians(p[0]))
    ax, ay, bx, by = (a[1] - p[1]) * k, a[0] - p[0], (b[1] - p[1]) * k, b[0] - p[0]
    dx, dy = bx - ax, by - ay
    t = 0 if dx == dy == 0 else max(0, min(1, -(ax * dx + ay * dy) / (dx * dx + dy * dy)))
    return math.hypot(ax + t * dx, ay + t * dy) * 111.2


def pick(r, cands):
    """The station for the resort's snow depth: one that stands in the ski area, at most MAX_KM from a lift (from
    the resort's point when it has no lifts) and between 50 m below the base and 100 m above the top. The highest
    one wins. A list, empty when there is none."""
    lines, ok = lift_lines(r["id"]), []
    for s in cands:
        if s["cc"] != r["cc"]:
            continue
        if km(r["lat"], r["lon"], s["lat"], s["lon"]) > 40:
            continue
        if s["a"] is not None and not (r["base"] - 50 <= s["a"] <= r["top"] + 100):
            continue
        p = (s["lat"], s["lon"])
        d = min(seg_km(p, a, b) for ln in lines for a, b in zip(ln, ln[1:])) if lines else km(r["lat"], r["lon"], *p)
        if d <= MAX_KM:
            ok.append((d, s))
    if not ok:
        return []
    return [max(ok, key=lambda x: ((x[1]["a"] or 0), -x[0]))[1]]

for name, fn in (("jma", jma), ("slf", slf), ("geosphere", geosphere), ("fmi", fmi), ("smhi", smhi), ("frost", frost)):
    try:
        fn()
    except Exception as e:
        print(name, "failed:", e, file=sys.stderr)

# Keep the last DAYS days, on the station's own grid, and only stations that still have data
for s in stations.values():
    ser = {k: v for k, v in s["ser"].items() if parse(k) >= START - timedelta(hours=s["dt"] - 1)}
    s["ser"] = ser
live = [s for s in stations.values() if any(parse(k) >= NOW - timedelta(hours=36) for k in s["ser"])]

out = {}
for r in resorts:
    chosen = pick(r, live)
    if chosen:
        out.setdefault(r["area"], {})[r["id"]] = chosen

key_of = {id(s): k for k, s in stations.items()}
for area in sorted({r["area"] for r in resorts}):
    used = {}
    res = {}
    for rid, ss in out.get(area, {}).items():
        res[rid] = [key_of[id(s)] for s in ss]
        for s in ss:
            used[key_of[id(s)]] = s
    st = {}
    for k, s in used.items():
        times = sorted(parse(t) for t in s["ser"])
        t0, t1 = times[0], times[-1]
        n = int((t1 - t0).total_seconds() // 3600 // s["dt"]) + 1
        v = [s["ser"].get(iso(t0 + timedelta(hours=s["dt"] * i))) for i in range(n)]
        st[k] = {"n": s["n"], "a": s["a"], "lat": round(s["lat"], 4), "lon": round(s["lon"], 4), "src": s["src"],
                 "t0": iso(t0), "dt": s["dt"], "v": v}
    at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    json.dump({"at": at, "stations": st, "resorts": res}, open(os.path.join(out_dir, area + ".json"), "w"),
              separators=(",", ":"), ensure_ascii=False)
    print(area, len(res), "resorts,", len(st), "stations", file=sys.stderr)
