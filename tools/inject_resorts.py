"""Write an area's resorts into the RESORTS list in index.html.

Usage: python3 tools/inject_resorts.py index.html data/osm/alps.json alps "Alperna"
The rows go between "// ----- <area>:start" and "// ----- <area>:end" markers (added before the end of
RESORTS the first time), grouped by country in the file's order.
"""
import json, re, sys

html_path, rows_path, area, title = sys.argv[1:5]
s = open(html_path, encoding="utf-8").read()
rows = json.load(open(rows_path, encoding="utf-8"))

q = lambda v: json.dumps(v, ensure_ascii=False)
lines, country = [f"  // ----- {area}:start · {title}: found in OpenStreetMap (named ski areas with lifts), base/top = lowest/highest lift station -----"], None
for r in rows:
    if r["country"] != country:
        country = r["country"]
        lines.append(f"  // {country}")
    lines.append(f'  {{id:{q(r["id"])},name:{q(r["name"])},jp:"",region:{q(r["region"])},lat:{r["lat"]},lon:{r["lon"]},'
                 f'base:{r["base"]},top:{r["top"]},area:{q(area)},country:{q(country)}'
                 + (f',eaws:{q(r["eaws"])}' if r.get("eaws") else "") + "},")
lines.append(f"  // ----- {area}:end -----")
block = "\n".join(lines) + "\n"

marker = re.compile(rf"  // ----- {area}:start.*?  // ----- {area}:end -----\n", re.S)
if marker.search(s):
    s = marker.sub(lambda m: block, s)
else:
    end = s.index("\n];\nRESORTS.forEach") + 1
    s = s[:end] + block + s[end:]
open(html_path, "w", encoding="utf-8").write(s)
print(len(rows), "resorts written for", area, file=sys.stderr)
