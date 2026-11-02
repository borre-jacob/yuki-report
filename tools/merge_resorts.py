"""Merge discovered resorts into an area file and give every resort its country and county/region.

Usage: python3 tools/merge_resorts.py data/osm/scandinavia.json data/osm/scandinavia_found.json data/scandinavia_extra.json
       python3 tools/merge_resorts.py data/osm/alps.json data/osm/alps_found.json
Every row gets: id, name, country, region (county/state, from Nominatim), lat, lon, base, top.
The area file is created if it does not exist; the extra file (hand-added resorts) is optional.
Ids never clash with resorts already in index.html.
"""
import json, os, re, subprocess, sys, time, unicodedata

UA = "YukiRadar/1.0 (personal ski trip app; github.com/borre-jacob/yuki-radar)"
COUNTRY = {"no": "Norge", "se": "Sverige", "fi": "Finland",
           "at": "Österrike", "ch": "Schweiz", "fr": "Frankrike", "it": "Italien"}
SKIP = re.compile(r"hopp|skiklubb|sprungschanze|tremplin|trampolino", re.I)
# "Skigebiet Ischgl" -> "Ischgl", "Domaine skiable de Tignes" -> "Tignes"
PREFIX = re.compile(r"^(Skigebiet|Skiregion|Skizentrum|Skiarena|Skiresort|Ski resort|Domaine skiable|Station de ski|"
                    r"Comprensorio sciistico|Area sciistica|Comprensorio|Stazione sciistica)( (de|du|des|d'|di|del|della|dei))? ?", re.I)


def slug(name):
    s = unicodedata.normalize("NFKD", name.lower().replace("ø", "o").replace("æ", "ae"))
    s = re.sub(r"[^a-z0-9]+", "", s.encode("ascii", "ignore").decode())
    return s[:24] or "resort"


def county(lat, lon):
    url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&zoom=8&format=json&accept-language=sv"
    for attempt in range(4):
        try:
            d = json.loads(subprocess.run(["curl", "-sS", "-m", "30", "-A", UA, url], capture_output=True, text=True).stdout)
            a = d.get("address", {})
            time.sleep(1.2)  # Nominatim allows one request per second
            return COUNTRY.get(a.get("country_code")), re.sub(r"s? län$| fylke$", "", a.get("state") or a.get("county") or a.get("region") or "")
        except Exception:
            time.sleep(5)
    return None, ""


rows = json.load(open(sys.argv[1], encoding="utf-8")) if os.path.exists(sys.argv[1]) else []
for r in rows:
    r.setdefault("country", r["region"])
new = [r for r in json.load(open(sys.argv[2], encoding="utf-8")) if not SKIP.search(r["name"])]
if len(sys.argv) > 3:
    new += json.load(open(sys.argv[3], encoding="utf-8"))
taken = set(re.findall(r'\{id:"(\w+)"', open("index.html", encoding="utf-8").read())) if os.path.exists("index.html") else set()
ids = taken | {r["id"] for r in rows}
for r in new:
    name = r["name"].title() if r["name"].isupper() else r["name"]
    name = PREFIX.sub("", name).strip() or name
    i = base = slug(name)
    n = 2
    while i in ids:
        i, n = f"{base}{n}", n + 1
    ids.add(i)
    rows.append({"id": i, "name": name, "lat": r["lat"], "lon": r["lon"], "base": r["base"], "top": r["top"]})

for r in rows:
    c, reg = county(r["lat"], r["lon"])
    r["country"] = c or r.get("country")
    r["region"] = reg or r["country"]
    print(r["id"], r["country"], r["region"], file=sys.stderr)

order = {c: i for i, c in enumerate(["Sverige", "Norge", "Finland", "Österrike", "Schweiz", "Frankrike", "Italien"])}
rows.sort(key=lambda r: (order.get(r["country"], 9), r["region"], r["name"]))
json.dump(rows, open(sys.argv[1], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(len(rows), "resorts", file=sys.stderr)
