"""Fetch the latest Japan Avalanche Network (JAN) bulletin for each forecast area.

Usage: python3 tools/fetch_avalanche.py data/avalanche.json
Writes {areaId: {date, url, levels:[alpine, treeline, belowTreeline], advice, problems:[...], summary:{...}}}.
Levels: 0 = no rating, 1 = low ... 5 = extreme.
Each problem can have grid: three rings (alpine/kalfjäll, treeline, below treeline) of eight aspects
(N, NE, E, SE, S, SW, W, NW), 0 = not exposed, 1 = exposed, 2 = most exposed.
"""
import html, json, re, subprocess, sys, time

AREAS = [2, 3, 4, 6, 7, 1]  # Hakuba, Myoko, Kagura/Tanigawa/Hotaka, SW Hokkaido, Central Hokkaido, Tateyama
BASE = "https://data.nadare.jp"
LEVEL = {"No rating": 0, "Low": 1, "Moderate": 2, "Considerable": 3, "High": 4, "Extreme": 5}
UA = "YukiRadar/1.0 (personal ski trip app; github.com/borre-jacob/yuki-radar)"


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


def jan_grids(page):
    """Aspect/elevation rose per problem. JAN draws it as one image layer per highlighted sector:
    info2_<band>_<aspect>_<a|b>.png, where a = darker (most exposed) and b = lighter (exposed)."""
    start, end = re.search(r">\s*Avalanche Problem\s*<", page), re.search(r">\s*概要\s*<", page)
    sec = page[start.end() if start else 0:end.start() if end else len(page)]
    grids, cur = {}, None
    for m in re.finditer(r"<h[1-6][^>]*>(.*?)</h[1-6]>|/assets/info2_(alp|tl|btl)_(n|ne|e|se|s|sw|w|nw)_([ab])-", sec, re.S):
        if m.group(1) is not None:
            cur = html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip()
            grids[cur] = [[0] * 8 for _ in BANDS]
        elif cur:
            band, asp, ab = m.group(2, 3, 4)
            grids[cur][BANDS.index(band)][ASPECTS.index(asp)] = 2 if ab == "a" else 1
    return {k: g for k, g in grids.items() if any(map(any, g))}


def latest(area):
    page = get(f"{BASE}/avalanche_informations?area_id={area}&locale=en")
    row = re.search(r'href="/avalanche_informations/(\d+)">\s*([\d/]+ [\d:]+)\s*</a>.*?<td>([^<]+)</td>(.*?)</tr>', page, re.S)
    if not row:
        return None
    bid, date, name, cells = row.groups()
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
    grids = jan_grids(page)
    for p in problems:
        if p["name"] in grids:
            p["grid"] = grids[p["name"]]
    summary = {k: " ".join(section(L, k, {"Avalanche", "Snowpack", "Weather", "Print/PDF"})) for k in ("Avalanche", "Snowpack", "Weather")}
    return {"name": name.strip(), "date": date.replace("/", "-"), "url": f"{BASE}/avalanche_informations/{bid}?locale=en",
            "levels": levels, "advice": advice, "problems": problems, "summary": summary}


SE_BASE = "https://www.lavinprognoser.se/oversikt-alla-omraden/"
SE_AREAS = ["abisko_riksgransfjallen", "kebnekaisefjallen", "sodra_jamtlandsfjallen",
            "sodra_lapplandsfjallen", "vastra_harjedalsfjallen", "vastra_vindelfjallen"]


def se_time(text):
    """'torsdag 22-10-2026 08:00' (Swedish local time) -> ISO string with offset."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
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
        if any(map(any, grid)):
            row["grid"] = grid
        if alt.get("metersAbove") or alt.get("metersBelow"):
            row["meters"] = [alt.get("metersAbove"), alt.get("metersBelow")]
        out.append(row)
    return out


def sweden(slug, date=None):
    """Latest Naturvårdsverket forecast: level 0-5, published/valid times, main message and problems.
    date (YYYY-MM-DD) fetches an old forecast instead, for testing outside the season."""
    page = get(SE_BASE + slug + "/" + (f"?forecast_date={date}" if date else ""))
    L = lines(page)
    after = lambda key: L[L.index(key) + 1] if key in L and L.index(key) + 1 < len(L) else ""
    level = next((int(l[9:-1]) for l in L if re.fullmatch(r"\[IMG:Risk \d\]", l)), 0)
    msg = section(L, "Hoppa över karta", {"Se tidigare prognoser", "calendar", "Så här läser du lavinprognosen"})
    return {"level": level, "label": after("Lavinfara"), "published": se_time(after("Publicerad:")),
            "validTo": se_time(after("Gäller till:")), "message": " ".join(msg)[:800], "url": SE_BASE + slug + "/",
            "problems": se_problems(page)}


def main(out):
    result = {}
    for a in AREAS:
        try:
            b = latest(a)
            if b:
                result[str(a)] = b
                print(a, b["name"], b["date"], b["levels"], len(b["problems"]), "problems", file=sys.stderr)
        except Exception as e:  # keep the other areas if one fails
            print(a, "failed:", e, file=sys.stderr)
        time.sleep(1)
    for slug in SE_AREAS:
        try:
            result["se_" + slug] = b = sweden(slug)
            print(slug, b["level"], b["label"], b["published"], file=sys.stderr)
        except Exception as e:
            print(slug, "failed:", e, file=sys.stderr)
        time.sleep(1)
    # No fetch timestamp in the file: the daily job only commits when a bulletin actually changed
    json.dump(result, open(out, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))


if __name__ == "__main__":
    main(sys.argv[1])
