"""Fetch the snow forecast for every resort once, for all users (run every few hours on GitHub).

Usage: python3 tools/fetch_snow.py index.html data/snow
Writes <dir>/<area>.json = {"at": fetch time (UTC), "resorts": {id: forecast}}. Each forecast is Open-Meteo's
answer for the resort's mid height, trimmed: hourly snowfall from "start" (local time, one value an hour) and
the daily snowfall and temperatures. The app reads these files instead of asking Open-Meteo itself, so the
number of calls stays the same however many people use it.
An area whose fetch fails keeps the file already in <dir> (the workflow puts the published one there first).
"""
import json, os, re, subprocess, sys, time
from datetime import datetime, timezone

UA = "YukiReport/1.0 (ski trip app; github.com/borre-jacob/yuki-report)"
html = open(sys.argv[1], encoding="utf-8").read()
out_dir = sys.argv[2]
os.makedirs(out_dir, exist_ok=True)

areas = {}
for row in re.findall(r'^  \{id:"\w+".*\},$', html, re.M):
    f = dict(re.findall(r'(\w+):("[^"]*"|-?[\d.]+)', row))
    area = json.loads(f.get("area", '"japan"'))
    areas.setdefault(area, []).append({"id": json.loads(f["id"]), "lat": f["lat"], "lon": f["lon"],
                                       "mid": round((float(f["base"]) + float(f["top"])) / 2)})


def fetch(part):
    # Same question as the app's own fallback in loadOverview()
    url = ("https://api.open-meteo.com/v1/forecast?latitude=" + ",".join(r["lat"] for r in part)
           + "&longitude=" + ",".join(r["lon"] for r in part)
           + "&elevation=" + ",".join(str(r["mid"]) for r in part)
           + "&hourly=snowfall&daily=snowfall_sum,temperature_2m_min,temperature_2m_max"
           + "&past_days=3&forecast_days=7&timezone=auto")
    for attempt in range(4):
        out = subprocess.run(["curl", "-sS", "-m", "120", "-A", UA, url], capture_output=True, text=True).stdout
        try:
            data = json.loads(out)
            if isinstance(data, dict) and data.get("error"):
                raise ValueError(data.get("reason"))
            return data if isinstance(data, list) else [data]
        except Exception as e:
            print("retry", attempt, str(e)[:80], file=sys.stderr)
            time.sleep(30 * (attempt + 1))
    return None


r1 = lambda v: None if v is None else round(v, 1)
failed = []
for area, resorts in areas.items():
    result = {}
    for i in range(0, len(resorts), 100):
        part = resorts[i:i + 100]
        answers = fetch(part)
        if answers is None or len(answers) != len(part):
            result = None
            break
        for r, d in zip(part, answers):
            result[r["id"]] = {
                "utc_offset_seconds": d.get("utc_offset_seconds", 0),
                "start": d["hourly"]["time"][0],
                "snowfall": [r1(v) for v in d["hourly"]["snowfall"]],
                "daily": {k: [r1(v) for v in d["daily"][k]] if k != "time" else d["daily"]["time"]
                          for k in ("time", "snowfall_sum", "temperature_2m_min", "temperature_2m_max")},
            }
        time.sleep(10)  # Open-Meteo fair use: every resort counts as a call
    if result is None:
        failed.append(area)
        continue
    at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    json.dump({"at": at, "resorts": result}, open(os.path.join(out_dir, area + ".json"), "w"), separators=(",", ":"))
    print(area, len(result), "resorts", file=sys.stderr)

if failed:
    print("failed, keeping the old file:", failed, file=sys.stderr)
