"""Average snowfall per season and per month for every resort, from Open-Meteo's historical (ERA5) data.

Usage: python3 tools/fetch_climate.py index.html data/climate.json
Run by hand now and then (the numbers hardly change), not by the workflow. Writes
{"seasons": "2015/16-2024/25", "n": 10, "resorts": {id: {"s": cm per season, "m": [cm in Oct, Nov, Dec, Jan, Feb, Mar, Apr, May]}}}.
The figures are modelled new snow (snowfall) at the resort's mid height, averaged over the seasons (July to June), not measured
snow depth; a reanalysis smooths the mountains, so they are indicative.
CLIMATE_AREAS (default scandinavia,alps) limits which areas are fetched; Japan is left out because ERA5 gives far too little snow there (Niseko about 340 cm). Resumable: resorts already in the output file are skipped, a run does at most CLIMATE_BATCHES (20) batches of 10 resorts, and when Open-Meteo says the daily limit is used up the script
saves what it has and stops; run it again later (the next day) to continue.
"""
import json, os, re, subprocess, sys, time

UA = "YukiReport/1.0 (ski trip app; github.com/borre-jacob/yuki-report)"
FIRST, LAST = 2015, 2024          # seasons 2015/16 ... 2024/25 (July to June)
START, END = f"{FIRST}-07-01", f"{LAST + 1}-06-30"
BATCH = 10
MAX_BATCHES = int(os.environ.get("CLIMATE_BATCHES", "20"))   # per run, to stay well inside Open-Meteo's daily limit
html = open(sys.argv[1], encoding="utf-8").read()
path = sys.argv[2]
AREAS = set(os.environ.get("CLIMATE_AREAS", "scandinavia,alps").split(","))
resorts = []
for row in re.findall(r'^  \{id:"\w+".*\},$', html, re.M):
    f = dict(re.findall(r'(\w+):("[^"]*"|-?[\d.]+)', row))
    if json.loads(f.get("area", '"japan"')) not in AREAS:
        continue
    resorts.append({"id": json.loads(f["id"]), "lat": f["lat"], "lon": f["lon"], "mid": round((float(f["base"]) + float(f["top"])) / 2)})
try:
    data = json.load(open(path))
except Exception:
    data = {"seasons": f"{FIRST}/{str(FIRST + 1)[2:]}-{LAST}/{str(LAST + 1)[2:]}", "n": LAST - FIRST + 1, "resorts": {}}
todo = [r for r in resorts if r["id"] not in data["resorts"]]
print(len(todo), "resorts left of", len(resorts), file=sys.stderr)


def save():
    json.dump(data, open(path, "w"), separators=(",", ":"))


for i in range(0, min(len(todo), MAX_BATCHES * BATCH), BATCH):
    part = todo[i:i + BATCH]
    url = ("https://archive-api.open-meteo.com/v1/archive?latitude=" + ",".join(r["lat"] for r in part)
           + "&longitude=" + ",".join(r["lon"] for r in part) + "&elevation=" + ",".join(str(r["mid"]) for r in part)
           + f"&start_date={START}&end_date={END}&daily=snowfall_sum&timezone=UTC")
    answers = None
    for attempt in range(5):
        out = subprocess.run(["curl", "-sS", "-m", "180", "-A", UA, url], capture_output=True, text=True).stdout
        try:
            d = json.loads(out)
            if isinstance(d, dict) and d.get("error"):
                reason = str(d.get("reason"))
                if "minutely" in reason.lower():
                    print("Minute limit, waiting", file=sys.stderr)
                    time.sleep(70)
                    continue
                if "limit" in reason.lower() or "exceeded" in reason.lower():
                    print("Stopped by Open-Meteo:", reason[:120], file=sys.stderr)
                    save(); sys.exit(0)
                raise ValueError(reason)
            answers = d if isinstance(d, list) else [d]
            break
        except Exception as e:
            print("retry", attempt, str(e)[:100], file=sys.stderr)
            time.sleep(20 * (attempt + 1))
    if answers is None or len(answers) != len(part):
        print("Giving up on this batch, saving", file=sys.stderr)
        save(); sys.exit(1)
    for r, a in zip(part, answers):
        tot, mon = 0.0, {m: 0.0 for m in (10, 11, 12, 1, 2, 3, 4, 5)}
        for day, v in zip(a["daily"]["time"], a["daily"]["snowfall_sum"]):
            if v is None:
                continue
            tot += v
            m = int(day[5:7])
            if m in mon:
                mon[m] += v
        n = data["n"]
        data["resorts"][r["id"]] = {"s": round(tot / n), "m": [round(mon[m] / n) for m in (10, 11, 12, 1, 2, 3, 4, 5)]}
    save()
    print(len(data["resorts"]), "done", file=sys.stderr)
    time.sleep(65)   # about one batch a minute keeps under the per-minute limit
print("All done", file=sys.stderr)
