import json, re, sys, time, math, subprocess, os

html = open(sys.argv[1], encoding="utf-8").read()
out_path = sys.argv[2]
resorts = re.findall(r'\{id:"(\w+)",name:"[^"]+",jp:"[^"]*",region:"[^"]+",lat:([\d.]+),lon:([\d.]+)', html)
PRIO = ['happo','goryu','iwatake','tsugaike','cortina','akakura','arai','nozawa','madarao','shiga']
resorts.sort(key=lambda x: PRIO.index(x[0]) if x[0] in PRIO else 99)
result = json.load(open(out_path)) if os.path.exists(out_path) else {}
URLS = ["https://maps.mail.ru/osm/tools/overpass/api/interpreter", "https://overpass-api.de/api/interpreter"]

def dist(a, b, c, d):
    R = 6371; t = math.radians
    h = math.sin(t(c-a)/2)**2 + math.cos(t(a))*math.cos(t(c))*math.sin(t(d-b)/2)**2
    return 2*R*math.asin(math.sqrt(h))

def classify(t):
    name = t.get("name", "")
    if t.get("leisure") == "sauna":
        return "onsen", "Bastu"
    if t.get("leisure") == "water_park":
        return "onsen", "Äventyrsbad"
    if t.get("amenity") == "public_bath" or t.get("bath:type") == "onsen":
        japanese = re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", name)
        if t.get("fee") == "no": sub = "Gratis bad"
        elif t.get("bath:type") == "onsen" or re.search("温泉|湯", name): sub = "Onsen"
        else: sub = "Badhus / sento" if japanese else "Badhus"
        return "onsen", sub
    if t.get("amenity") == "toilets":
        return "toilet", "Toalett · dygnet runt" if t.get("opening_hours") == "24/7" else "Toalett"
    if "道の駅" in name: return "park", "Michi-no-eki · parkering + toalett 24 h"
    if re.search("RVパーク|RV Park", name, re.I): return "park", "RV Park · ställplats"
    if t.get("tourism") == "caravan_site": return "park", "Husbilsplats"
    if t.get("tourism") == "camp_site": return "park", "Camping" + (" (stängd vintertid)" if t.get("winter") == "no" else "")
    if t.get("highway") == "services": return "park", "Serviceområde (motorväg)"
    if t.get("highway") == "rest_area": return "park", "Rastplats"
    if t.get("amenity") == "parking":
        if not name and not (t.get("capacity", "").isdigit() and int(t["capacity"]) >= 50): return None
        sub = "Parkering" + (" · avgift" if t.get("fee") == "yes" else " · gratis" if t.get("fee") == "no" else "")
        if t.get("capacity"): sub += f" · {t['capacity']} platser"
        return "park", sub
    return None

for rid, lat, lon in resorts:
    if rid in result: continue
    lat, lon = float(lat), float(lon)
    bb = f"{lat-0.3:.3f},{lon-0.4:.3f},{lat+0.3:.3f},{lon+0.4:.3f}"
    q = f'''[out:json][timeout:90][bbox:{bb}];(
nwr["amenity"="public_bath"];nwr["bath:type"="onsen"];nwr["leisure"="sauna"]["access"!="private"];nwr["leisure"="water_park"];
nwr["highway"~"^(rest_area|services)$"];nwr["tourism"~"^(caravan_site|camp_site)$"];
nwr["name"~"道の駅|RVパーク"];
nwr["amenity"="toilets"](around:12000,{lat},{lon});
nwr["amenity"="parking"](around:4000,{lat},{lon}););out center tags;'''
    data = None
    for attempt in range(4):
        url = URLS[attempt % len(URLS)]
        r = subprocess.run(["curl", "-s", "-m", "120", "-A", "YukiReport/1.0 (personal ski trip planner)", url, "--data-urlencode", "data=" + q], capture_output=True, text=True)
        try:
            data = json.loads(r.stdout); break
        except Exception:
            print(rid, "retry", attempt, r.stdout[:80].replace("\n", " "), file=sys.stderr); time.sleep(10 * (attempt + 1))
    if not data:
        print(rid, "FAILED", file=sys.stderr); continue
    seen, items = set(), []
    for e in data["elements"]:
        t = e.get("tags", {}); la = e.get("lat") or e.get("center", {}).get("lat"); lo = e.get("lon") or e.get("center", {}).get("lon")
        if la is None: continue
        c = classify(t)
        if not c: continue
        typ, sub = c
        name = t.get("name:en") or t.get("name") or ""
        jp = t.get("name", "") if t.get("name:en") and t.get("name") != t.get("name:en") else ""
        key = typ + "|" + (name or f"{la:.4f},{lo:.4f}")
        if key in seen: continue
        seen.add(key)
        items.append([typ, name, jp, round(la, 5), round(lo, 5), sub, t.get("opening_hours", ""), round(dist(lat, lon, la, lo), 1)])
    items.sort(key=lambda x: x[7])
    result[rid] = items
    json.dump(result, open(out_path, "w"), ensure_ascii=False, separators=(",", ":"))
    print(rid, len(items), {k: sum(1 for i in items if i[0] == k) for k in ("onsen", "toilet", "park")}, file=sys.stderr)
    time.sleep(3)
