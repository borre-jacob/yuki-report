"""Fetch every avalanche bulletin the app shows, once for all users (run every 3 hours on GitHub).

Usage: python3 tools/fetch_avalanche.py index.html data/avalanche
Writes <dir>/<area>.json, read by the app instead of asking each service itself:
  japan.json       {"at", "jan": {areaId: {date, url, levels:[alpine, treeline, belowTreeline], advice, problems, summary}}}
  scandinavia.json {"at", "se": {slug: {level, label, published, validTo, message, url, problems}},
                    "no": {"warnings": {"<RegionId>-<date>": Varsom warning}, "resorts": {resortId: {date: key}}}}
  alps.json        {"at", "eaws": {"bulletins": {bulletinID: EAWS CAAML bulletin}, "resorts": {resortId: {date: bulletinID}}}}
Varsom and EAWS hold today and tomorrow (local date), trimmed to the fields the app uses.
Problems also carry how likely and how large avalanches are, when the service gives it (JAN: like + size [min, max];
Sweden: spread, sensitivity, sizeMeter 0-100; Varsom and EAWS: their own fields).
AVAL_DATE=YYYY-MM-DD fetches the bulletins of that day instead of today, for testing outside the season.
Levels: 0 = no rating, 1 = low ... 5 = very high. A JAN or Swedish problem can have grid: three rings
(alpine/kalfjäll, treeline, below treeline) of eight aspects (N, NE, E, SE, S, SW, W, NW),
0 = not exposed, 1 = exposed, 2 = most exposed.
A part that fails keeps what the file already had (the workflow puts the published files there first).
"""
import html, json, os, re, subprocess, sys, time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

AREAS = [2, 3, 4, 6, 7, 1]  # Hakuba, Myoko, Kagura/Tanigawa/Hotaka, SW Hokkaido, Central Hokkaido, Tateyama
BASE = "https://data.nadare.jp"
LEVEL = {"No rating": 0, "Low": 1, "Moderate": 2, "Considerable": 3, "High": 4, "Extreme": 5}
UA = "YukiReport/1.0 (personal ski trip app; github.com/borre-jacob/yuki-report)"


def get(url):
    # curl instead of urllib: works the same on macOS and on GitHub Actions
    r = subprocess.run(["curl", "-sSfL", "-m", "30", "-A", UA, url], capture_output=True, check=True)
    return r.stdout.decode("utf-8")


def lines(page):
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", page, flags=re.S)
    t = re.sub(r'<img[^>]*alt="([^"]+)"[^>]*>', r"\n[IMG:\1]\n", t)
    return [l.strip() for l in html.unescape(re.sub(r"<[^>]+>", "\n", t)).split("\n") if l.strip()]


def section(L, start, stops):
    if start not in L:
        return []
    out = []
    for l in L[L.index(start) + 1:]:
        if l in stops:
            break
        out.append(l)
    return out


ASPECTS = ["n", "ne", "e", "se", "s", "sw", "w", "nw"]
BANDS = ["alp", "tl", "btl"]


JAN_LIKE = {"certain", "very_likely", "likely", "possible", "unlikely"}


def jan_details(page):
    """Per problem: the aspect/elevation rose, likelihood and size range, all drawn as images.
    Rose: one layer per highlighted sector, info2_<band>_<aspect>_<a|b>.png (a = most exposed, b = exposed).
    Likelihood: info3_graph_<likelihood>_on. Size: info4_size_<10..50>_on per half size step (10 = size 1)."""
    start, end = re.search(r">\s*Avalanche Problem\s*<", page), re.search(r">\s*概要\s*<", page)
    sec = page[start.end() if start else 0:end.start() if end else len(page)]
    out, cur = {}, None
    for m in re.finditer(r"<h[1-6][^>]*>(.*?)</h[1-6]>|/assets/info2_(alp|tl|btl)_(n|ne|e|se|s|sw|w|nw)_([ab])-"
                         r"|/assets/info3_graph_([a-z_]+?)_on|/assets/info4_size_(\d+)_on", sec, re.S):
        if m.group(1) is not None:
            cur = {"grid": [[0] * 8 for _ in BANDS], "sizes": []}
            out[html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip()] = cur
        elif cur is None:
            continue
        elif m.group(2):
            band, asp, ab = m.group(2, 3, 4)
            cur["grid"][BANDS.index(band)][ASPECTS.index(asp)] = 2 if ab == "a" else 1
        elif m.group(5) in JAN_LIKE:
            cur["like"] = m.group(5)
        elif m.group(6):
            cur["sizes"].append(int(m.group(6)) / 10)
    res = {}
    for name, d in out.items():
        row = {}
        if any(map(any, d["grid"])):
            row["grid"] = d["grid"]
        if d.get("like"):
            row["like"] = d["like"]
        if d["sizes"]:
            row["size"] = [min(d["sizes"]), max(d["sizes"])]
        res[name] = row
    return res


def latest(area):
    page = get(f"{BASE}/avalanche_informations?area_id={area}&locale=en")
    rows = re.findall(r'href="/avalanche_informations/(\d+)">\s*([\d/]+ [\d:]+)\s*</a>.*?<td>([^<]+)</td>(.*?)</tr>', page, re.S)
    if TEST_DATE:  # the list holds the season's bulletins, newest first
        rows = [r for r in rows if r[1].replace("/", "-").startswith(TEST_DATE)]
    if not rows:
        return None
    bid, date, name, cells = rows[0]
    levels = [LEVEL.get(a, 0) for a in re.findall(r'alt="([^"]+)"', cells)][:3]

    page = get(f"{BASE}/avalanche_informations/{bid}?locale=en")
    L = lines(page)
    advice = " ".join(section(L, "Travel and Terrain Advice", {"Avalanche Problem", "概要"}))
    problems, cur = [], None
    for l in section(L, "Avalanche Problem", {"概要"}):
        if l.startswith("[IMG:"):
            continue
        if cur is None or (cur.get("text") is not None):
            # A short line without a full stop starts a new problem; the next line is its description
            if len(l) < 40 and not l.endswith("."):
                cur = {"name": l, "text": None}
                problems.append(cur)
                continue
        if cur is not None and cur["text"] is None:
            cur["text"] = l
    details = jan_details(page)
    for p in problems:
        p.update(details.get(p["name"], {}))
    summary = {k: " ".join(section(L, k, {"Avalanche", "Snowpack", "Weather", "Print/PDF"})) for k in ("Avalanche", "Snowpack", "Weather")}
    return {"name": name.strip(), "date": date.replace("/", "-"), "url": f"{BASE}/avalanche_informations/{bid}?locale=en",
            "levels": levels, "advice": advice, "problems": problems, "summary": summary}


SE_BASE = "https://www.lavinprognoser.se/oversikt-alla-omraden/"
SE_AREAS = ["abisko_riksgransfjallen", "kebnekaisefjallen", "sodra_jamtlandsfjallen",
            "sodra_lapplandsfjallen", "vastra_harjedalsfjallen", "vastra_vindelfjallen"]


def se_time(text):
    """'torsdag 22-10-2026 08:00' (Swedish local time) -> ISO string with offset."""
    m = re.search(r"(\d{2})-(\d{2})-(\d{4}) (\d{2}):(\d{2})", text or "")
    if not m:
        return None
    d, mo, y, h, mi = map(int, m.groups())
    return datetime(y, mo, d, h, mi, tzinfo=ZoneInfo("Europe/Stockholm")).isoformat()


SE_DIRS = ["northPanel", "northEastPanel", "eastPanel", "southEastPanel", "southPanel", "southWestPanel", "westPanel", "northWestPanel"]
SE_RINGS = ["altitudeMeterAboveTreeline", "altitudeMeterTreeline", "altitudeMeterBelowTreeline"]


def se_problems(page):
    """Avalanche problems from the JSON the page embeds for its React app: name, rose and metres."""
    i = page.find('"avalancheProblem":')
    if i < 0:
        return []
    try:
        data, _ = json.JSONDecoder().raw_decode(page, i + len('"avalancheProblem":'))
    except ValueError:
        return []
    out = []
    for p in data.get("problems") or []:
        alt, d = p.get("altitude") or {}, p.get("direction") or {}
        aspects = [1 if (d.get(k) or {}).get("state") else 0 for k in SE_DIRS]
        grid = [aspects if (alt.get(k) or {}).get("state") else [0] * 8 for k in SE_RINGS]
        name = ((p.get("symbol") or {}).get("image") or {}).get("alt") or (p.get("description") or {}).get("title") or ""
        row = {"name": name}
        spread = p.get("spread") or {}
        for key, src in (("spread", "spread"), ("sensitivity", "sensitivity"), ("sizeMeter", "sizeMeterValue")):
            if spread.get(src) is not None:
                row[key] = spread[src]
        # Where the problem is found, in Swedish. Some texts carry leftovers from Word ("Normal 0 false ...")
        where = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", (p.get("position") or {}).get("content") or ""))).strip()
        if where and not re.search(r"\bfalse\b|\bNormal 0\b", where):
            row["where"] = where[:400]
        if any(map(any, grid)):
            row["grid"] = grid
        if alt.get("metersAbove") or alt.get("metersBelow"):
            row["meters"] = [alt.get("metersAbove"), alt.get("metersBelow")]
        out.append(row)
    return out


def sweden(slug, date=None):
    """Latest Naturvårdsverket forecast: level 0-5, published/valid times, main message and problems.
    date (YYYY-MM-DD) fetches an old forecast instead, for testing outside the season."""
    date = date or TEST_DATE
    page = get(SE_BASE + slug + "/" + (f"?forecast_date={date}" if date else ""))
    L = lines(page)
    after = lambda key: L[L.index(key) + 1] if key in L and L.index(key) + 1 < len(L) else ""
    level = next((int(l[9:-1]) for l in L if re.fullmatch(r"\[IMG:Risk \d\]", l)), 0)
    msg = " ".join(section(L, "Hoppa över karta", {"Se tidigare prognoser", "calendar", "Så här läser du lavinprognosen"}))
    msg = msg.split("[IMG:")[0]  # the rest of the page follows the message: problems, links, tomorrow
    msg = re.sub(r"\s*Normal \d+ (?:(?:false|true|\d+|[A-Z]{2}|X-NONE)\s+)+", " ", msg).strip()  # Word leftovers
    row = {"level": level, "label": after("Lavinfara"), "published": se_time(after("Publicerad:")),
           "validTo": se_time(after("Gäller till:")), "message": msg[:800], "url": SE_BASE + slug + "/",
           "problems": se_problems(page)}
    # "Förväntad utveckling": the expected level for the next day, drawn as an image just before the heading
    if "Förväntad utveckling" in L:
        k = L.index("Förväntad utveckling")
        m = re.fullmatch(r"\[IMG:Risk (\d)\]", L[k - 1])
        day = next((l for l in L[k + 1:k + 5] if re.fullmatch(r"\d{4}-\d{2}-\d{2}", l)), None)
        if m and day:
            row["next"] = {"level": int(m.group(1)), "date": day}
    return row


def resorts(index_html):
    """Resort rows from index.html: id, lat, lon, area, country and EAWS micro-region."""
    out = []
    for row in re.findall(r'^  \{id:"\w+".*\},$', open(index_html, encoding="utf-8").read(), re.M):
        f = {k: json.loads(v) if v.startswith('"') else float(v) for k, v in re.findall(r'(\w+):("[^"]*"|-?[\d.]+)', row)}
        out.append({"id": f["id"], "lat": f["lat"], "lon": f["lon"], "area": f.get("area", "japan"),
                    "country": f.get("country", "Japan"), "eaws": f.get("eaws")})
    return out


TEST_DATE = os.environ.get("AVAL_DATE")


def local_days(tz):
    today = datetime.strptime(TEST_DATE, "%Y-%m-%d").date() if TEST_DATE else datetime.now(ZoneInfo(tz)).date()
    return [str(today), str(today + timedelta(days=1))]


VARSOM = "https://api01.nve.no/hydrology/forecast/avalanche/v6.3.0/api/AvalancheWarningByCoordinates/Detail/{lat}/{lon}/2/{d0}/{d1}"
VARSOM_KEYS = ["RegId", "RegionId", "RegionName", "RegionTypeName", "DangerLevel", "PublishTime", "ValidFrom", "ValidTo", "MainText"]
VARSOM_PROBLEM_KEYS = ["AvalancheProblemTypeName", "ValidExpositions", "AvalCauseName", "ExposedHeight1", "ExposedHeight2", "ExposedHeightFill",
                       "AvalProbabilityName", "DestructiveSizeExtId", "AvalTriggerSensitivityName"]


def norway(rows):
    """Varsom warning for each Norwegian resort, today and tomorrow. Resorts in the same region share one warning."""
    d0, d1 = local_days("Europe/Oslo")
    warnings, by_resort = {}, {}
    for r in rows:
        try:
            for w in json.loads(get(VARSOM.format(lat=r["lat"], lon=r["lon"], d0=d0, d1=d1))):
                # RegId is 0 for every region when no warning is issued (off season): key on region and day instead
                rid = f'{w["RegionId"]}-{w["ValidFrom"][:10]}'
                warnings[rid] = {**{k: w.get(k) for k in VARSOM_KEYS},
                                 "Advices": [a["Text"].strip() for a in w.get("AvalancheAdvices") or [] if (a.get("Text") or "").strip()],
                                 "AvalancheProblems": [{k: p.get(k) for k in VARSOM_PROBLEM_KEYS} for p in w.get("AvalancheProblems") or []]}
                by_resort.setdefault(r["id"], {})[w["ValidFrom"][:10]] = rid
        except Exception as e:
            print("varsom", r["id"], "failed:", e, file=sys.stderr)
        time.sleep(0.3)
    print("varsom", len(by_resort), "resorts,", len(warnings), "warnings", file=sys.stderr)
    return {"warnings": warnings, "resorts": by_resort} if by_resort else None


EAWS = "https://static.avalanche.report/eaws_bulletins/{d}/{d}-{svc}.json"


def eaws_service(region):
    # Same split as eawsService() in the app: one file per country or region service
    if region[:2] in ("CH", "FR"):
        return region[:2]
    return region[:8] if region.startswith("IT-32-") else region[:5]


def alps(rows):
    """EAWS bulletins (CAAML v6) for the Alps resorts, today and tomorrow (Vienna date). Bulletins are named by
    the day they are valid; tomorrow's comes out around 17:00, so off season and in the morning many are missing."""
    want = {r["eaws"]: [] for r in rows if r["eaws"]}
    for r in rows:
        if r["eaws"]:
            want[r["eaws"]].append(r["id"])
    services = sorted({eaws_service(x) for x in want})
    bulletins, by_resort, fetched = {}, {}, False
    for d in local_days("Europe/Vienna"):
        for svc in services:
            try:
                r = subprocess.run(["curl", "-sSL", "-m", "30", "-A", UA, "-w", "%{http_code}", EAWS.format(d=d, svc=svc)], capture_output=True)
                body, code = r.stdout[:-3], r.stdout[-3:].decode()
                if code == "404":
                    fetched = True  # the service answered: no bulletin for that day
                    continue
                if code != "200":
                    raise ValueError("HTTP " + code)
                fetched = True
                for b in json.loads(body).get("bulletins") or []:
                    ours = [x for x in b.get("regions") or [] if x.get("regionID") in want]
                    if not ours:
                        continue
                    bid = b.get("bulletinID") or f"{svc}-{d}-{len(bulletins)}"
                    bulletins[bid] = {
                        "lang": b.get("lang"), "publicationTime": b.get("publicationTime"), "validTime": b.get("validTime"),
                        "regions": [{"regionID": x["regionID"], "name": x.get("name")} for x in ours],
                        "dangerRatings": b.get("dangerRatings") or [],
                        "avalancheProblems": [{k: p.get(k) for k in ("problemType", "aspects", "elevation", "avalancheSize", "frequency", "snowpackStability", "validTimePeriod")}
                                              for p in b.get("avalancheProblems") or []],
                        "tendency": [t["tendencyType"] for t in b.get("tendency") or [] if t.get("tendencyType")],
                        "avalancheActivity": {k: (b.get("avalancheActivity") or {}).get(k) for k in ("highlights", "comment")},
                        "snowpackStructure": {"comment": (b.get("snowpackStructure") or {}).get("comment")},
                    }
                    for x in ours:
                        for rid in want[x["regionID"]]:
                            by_resort.setdefault(rid, {})[d] = bid
            except Exception as e:
                print("eaws", d, svc, "failed:", e, file=sys.stderr)
            time.sleep(0.3)
    print("eaws", len(by_resort), "resorts,", len(bulletins), "bulletins", file=sys.stderr)
    return {"bulletins": bulletins, "resorts": by_resort} if fetched else None


def japan():
    out = {}
    for a in AREAS:
        try:
            b = latest(a)
            if b:
                out[str(a)] = b
                print(a, b["name"], b["date"], b["levels"], len(b["problems"]), "problems", file=sys.stderr)
        except Exception as e:  # keep the other areas if one fails
            print(a, "failed:", e, file=sys.stderr)
        time.sleep(1)
    return out


def sweden_all():
    out = {}
    for slug in SE_AREAS:
        try:
            out[slug] = b = sweden(slug)
            print(slug, b["level"], b["label"], b["published"], file=sys.stderr)
        except Exception as e:
            print(slug, "failed:", e, file=sys.stderr)
        time.sleep(1)
    return out


def main(index_html, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    rows = resorts(index_html)
    at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def save(area, parts):
        path = os.path.join(out_dir, area + ".json")
        try:
            old = json.load(open(path, encoding="utf-8"))
        except Exception:
            old = {}
        new = {"at": at}
        for key, value, merge in parts:
            prev = old.get(key)
            if value is None:          # the whole source failed: keep the last copy
                value = prev
            elif merge and prev:       # per-area sources: an area that failed keeps its last bulletin
                value = {**prev, **value}
            if value is not None:
                new[key] = value
        json.dump(new, open(path, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
        print(area, os.path.getsize(path), "bytes", file=sys.stderr)

    save("japan", [("jan", japan(), True)])
    save("scandinavia", [("se", sweden_all(), True), ("no", norway([r for r in rows if r["country"] == "Norge"]), False)])
    save("alps", [("eaws", alps([r for r in rows if r["area"] == "alps"]), False)])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
