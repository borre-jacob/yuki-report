"""Build the published site: the app plus one page per resort and language, for search engines.

Usage: python3 tools/build_site.py <repo dir> <out dir>
Copies the app (index.html, data/, fonts/, icons/, …) to <out dir> and adds:
  /sv/ and /en/                 the start page in each language, with links to every resort
  /sv/<id>/ and /en/<id>/       one page per resort, with its own title, description, links between the languages,
                                schema.org data and a short text with the latest snow numbers, so search engines see
                                the content without running the app. The app starts as usual and replaces the text.
  sitemap.xml, robots.txt
The big inline style and script of index.html go to app.<hash>.css and app.<hash>.js, so the ~1,000 pages share
one cached copy. The name changes with the content, so a new version is never mixed with an old cached one.
index.html in the repo stays one self-contained file for local testing.
"""
import hashlib, html, json, math, os, re, shutil, subprocess, sys
from datetime import datetime, timedelta, timezone

SITE = "https://yukireport.com"
src, out = sys.argv[1], sys.argv[2]
SKIP = {".git", ".github", ".claude", "tools", "_site", "__pycache__", "README.md", ".gitignore", ".DS_Store"}
now = datetime.now(timezone.utc)
today = now.strftime("%Y-%m-%d")

if os.path.exists(out):
    shutil.rmtree(out)
shutil.copytree(src, out, ignore=lambda d, names: [n for n in names if n in SKIP or n == "dl"])

page = open(os.path.join(src, "index.html"), encoding="utf-8").read()

# --- Minify ---
# esbuild (pinned, fetched by npx on GitHub's runner) takes out comments and white space and shortens expressions, but never
# renames anything, so the app behaves exactly as written. If esbuild is missing (a local build without node) or fails,
# or its answer is not smaller, the file is published as it is.
ESBUILD = ["npx", "--yes", "esbuild@0.24.0"]
def minify(body, kind):
    flags = ["--loader=js", "--minify-whitespace", "--minify-syntax"] if kind == "js" else ["--loader=css", "--minify"]
    try:
        r = subprocess.run(ESBUILD + flags, input=body.encode("utf-8"), capture_output=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as e:
        print(f"No minifying of the {kind} ({type(e).__name__})", file=sys.stderr)
        return body
    small = r.stdout.decode("utf-8")
    if r.returncode != 0 or not small.strip() or len(small) >= len(body):
        print(f"No minifying of the {kind}: " + r.stderr.decode("utf-8", "replace")[:300], file=sys.stderr)
        return body
    print(f"Minified the {kind}: {len(body)} -> {len(small)} characters", file=sys.stderr)
    return small

# --- Move the main style and the app script out of the page ---
def externalize(page, tag, pattern, ext):
    m = re.search(pattern, page, re.S)
    body = minify(m.group(1), ext)
    h = hashlib.sha256(body.encode()).hexdigest()[:10]
    name = f"app.{h}.{ext}"
    open(os.path.join(out, name), "w", encoding="utf-8").write(body)
    ref = f'<link rel="stylesheet" href="{name}">' if tag == "style" else f'<script src="{name}"></script>'
    return page[:m.start()] + ref + page[m.end():]

page = externalize(page, "style", r"<style>\n(.*?)</style>", "css")
page = externalize(page, "script", r"<script>\n(// ---------- Language ----------.*?)</script>(?=\s*</body>)", "js")
# Nothing from the map libraries may hold up the first paint: their scripts and the app's own run with "defer"
# (still in order, so the app finds the libraries), and their stylesheets load without blocking. The text built
# into each page shows at once. index.html in the repo keeps plain tags, since its app script is inline.
page = re.sub(r'<script src="(https://[^"]+)"></script>', r'<script defer src="\1"></script>', page)
page = re.sub(r'<script src="(app\.[0-9a-f]+\.js)"></script>', r'<script defer src="\1"></script>', page)
page = re.sub(r'<link rel="stylesheet" href="(https://[^"]+)">',
              '<link rel="stylesheet" href="\\1" media="print" onload="this.media=\'all\'">', page)
hosts = sorted(set(re.findall(r'(?:src|href)="(https://[^/"]+)/[^"]*"(?: media="print")?', page)) & {
    "https://cdnjs.cloudflare.com", "https://cdn.jsdelivr.net", "https://unpkg.com"})
page = page.replace("<title>", "".join(f'<link rel="preconnect" href="{h}">\n' for h in hosts) + "<title>", 1)

# --- Resorts as the app lists them ---
CC_EN = {"Sverige": "Sweden", "Norge": "Norway", "Finland": "Finland", "Österrike": "Austria", "Schweiz": "Switzerland",
         "Frankrike": "France", "Italien": "Italy", "Japan": "Japan"}
CC_ISO = {"Sverige": "SE", "Norge": "NO", "Finland": "FI", "Österrike": "AT", "Schweiz": "CH", "Frankrike": "FR", "Italien": "IT", "Japan": "JP"}
AREA = {"japan": ("Japan", "Japan"), "scandinavia": ("Skandinavien", "Scandinavia"), "alps": ("Alperna", "The Alps")}
src_html = open(os.path.join(src, "index.html"), encoding="utf-8").read()
resorts = []
for row in re.findall(r'^  \{id:"\w+".*\},$', src_html, re.M):
    f = {k: json.loads(v) for k, v in re.findall(r'(\w+):("[^"]*"|-?[\d.]+)', row)}
    f.setdefault("area", "japan")
    f.setdefault("country", "Japan")
    resorts.append(f)


def load(kind, area):
    try:
        return json.load(open(os.path.join(src, "data", kind, area + ".json")))
    except Exception:
        return {}


snow = {a: load("snow", a) for a in AREA}
obs = {a: load("obs", a) for a in AREA}
cams = {a: load("cams", a) for a in AREA}

# One small webcam file per resort (data/cams/r/<id>.json), so the app does not download a whole area's list for one
# resort. Every resort gets one, empty when it has no cameras, so the app never asks for a file that is not there. The
# area files stay as they are: the workflow restores them from the published site before the next daily fetch.
os.makedirs(os.path.join(out, "data", "cams", "r"), exist_ok=True)
for r in resorts:
    c = cams[r["area"]]
    json.dump({"tpl": c.get("tpl", {}), "cams": c.get("resorts", {}).get(r["id"], [])},
              open(os.path.join(out, "data", "cams", "r", r["id"] + ".json"), "w"), separators=(",", ":"), ensure_ascii=False)


# --- "Om orten": facts from the places file and a hand-written text (about/<id>.json) ---
# The app builds the same page on the client (loadAbout in index.html); here the facts go into the page for search engines.
# about/ids.json tells the app which resorts have a hand-written text, so it never asks for a file that is not there.
ABOUT_DIR = os.path.join(src, "about")
about_ids = sorted(f[:-5] for f in os.listdir(ABOUT_DIR) if f.endswith(".json") and f != "ids.json") if os.path.isdir(ABOUT_DIR) else []
os.makedirs(os.path.join(out, "about"), exist_ok=True)
json.dump(about_ids, open(os.path.join(out, "about", "ids.json"), "w"))


def line_m(pts):
    m = 0.0
    for a, b in zip(pts, pts[1:]):
        p1, p2 = math.radians(a[0]), math.radians(b[0])
        h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(b[1] - a[1]) / 2) ** 2
        m += 2 * 6371000 * math.asin(math.sqrt(h))
    return m


def about_facts(r, lang):
    """Paragraphs (plain text) about the resort: heights, lifts, parking and the hand-written text if there is one."""
    vert = r["top"] - r["base"]
    out_ = []
    if r.get("kind") == "tour":
        out_.append(T(lang, f"Turen startar på {r['base']} m och toppen är {r['top']} m: {vert} m höjdmeter upp.",
                      f"The tour starts at {r['base']} m and the top is {r['top']} m: {vert} m of climbing."))
    else:
        out_.append(T(lang, f"Dalnivån är {r['base']} m och toppen {r['top']} m, alltså {vert} m höjdskillnad.",
                      f"The base is {r['base']} m and the top {r['top']} m, a vertical of {vert} m."))
        try:
            pl = json.load(open(os.path.join(src, "data", "osm", "places", r["id"] + ".json")))
        except Exception:
            pl = {}
        lifts = sorted(((line_m(pts), name, kind) for kind, name, pts in pl.get("lifts", [])), reverse=True)
        if lifts:
            km = sum(l[0] for l in lifts) / 1000
            top = lifts[0]
            kms = f"{km:.1f}"
            out_.append(T(lang, f"Här finns {len(lifts)} liftar på sammanlagt {kms.replace('.', ',')} km" + (f", längst är {top[1]} på {round(top[0] / 5) * 5} m." if top[1] else "."),
                          f"There are {len(lifts)} lifts with a total length of {kms} km" + (f", the longest is {top[1]} at {round(top[0] / 5) * 5} m." if top[1] else ".")))
        parks = [p for p in pl.get("pois", []) if p[0] == "park"]
        if parks:
            out_.append(T(lang, "Det finns en parkering." if len(parks) == 1 else f"Det finns {len(parks)} parkeringar.",
                          "There is one car park." if len(parks) == 1 else f"There are {len(parks)} car parks."))
    try:
        out_ += json.load(open(os.path.join(ABOUT_DIR, r["id"] + ".json"), encoding="utf-8")).get(lang, [])
    except Exception:
        pass
    return out_


def snow_numbers(r):
    """New snow at mid height: the next 3 days from today and the 3 days before, from the central snow file."""
    d = snow[r["area"]].get("resorts", {}).get(r["id"])
    if not d:
        return None
    local = (now + timedelta(seconds=d.get("utc_offset_seconds", 0))).strftime("%Y-%m-%d")
    days, sums = d["daily"]["time"], d["daily"]["snowfall_sum"]
    if local not in days:
        return None
    i = days.index(local)
    nxt = sum(x or 0 for x in sums[i:i + 3])
    past = sum(x or 0 for x in sums[max(0, i - 3):i])
    return round(nxt), round(past)


def depth(r):
    """The measured snow depth from the station in the ski area, as on the resort page."""
    o = obs[r["area"]]
    for k in o.get("resorts", {}).get(r["id"], [])[:1]:
        s = o["stations"].get(k)
        vals = [v for v in (s or {}).get("v", []) if v is not None]
        if vals:
            return s["n"], s.get("a"), vals[-1]
    return None


E = html.escape
T = lambda lang, sv, en: sv if lang == "sv" else en
country = lambda r, lang: r["country"] if lang == "sv" else CC_EN.get(r["country"], r["country"])


def head(p, lang, title, desc, path, alt, ld=None):
    """Title, description, canonical address, the other language and data for sharing and search engines."""
    url = SITE + path
    tags = [f'<link rel="canonical" href="{url}">']
    for l, pth in alt.items():
        tags.append(f'<link rel="alternate" hreflang="{l}" href="{SITE + pth}">')
    tags += [f'<meta property="og:type" content="website">', f'<meta property="og:site_name" content="Yuki Report">',
             f'<meta property="og:title" content="{E(title)}">', f'<meta property="og:description" content="{E(desc)}">',
             f'<meta property="og:url" content="{url}">', f'<meta property="og:image" content="{SITE}/icons/icon-512.png">',
             f'<meta property="og:locale" content="{"sv_SE" if lang == "sv" else "en_GB"}">', '<meta name="twitter:card" content="summary">']
    if ld:
        tags.append('<script type="application/ld+json">' + json.dumps(ld, ensure_ascii=False) + "</script>")
    p = re.sub(r"<title>.*?</title>", f"<title>{E(title)}</title>", p, count=1)
    p = re.sub(r'<meta name="description" content="[^"]*">', f'<meta name="description" content="{E(desc)}">\n' + "\n".join(tags), p, count=1)
    p = p.replace('<html lang="sv">', f'<html lang="{lang}">', 1)
    if lang == "en":   # the menu button has a name before the app starts (the app sets it again)
        p = p.replace('id="menubtn" class="menubtn" aria-label="Inställningar"', 'id="menubtn" class="menubtn" aria-label="Settings"', 1)
    return p


def with_app(p, inner):
    return p.replace('<main id="app"></main>', f'<main id="app"><div class="pre">{inner}</div></main>', 1)


def resort_list(lang, only=None):
    """Links to every resort (or the ones in `only`), by area, country and region."""
    out_ = []
    for a, (sv, en) in AREA.items():
        rs = [r for r in resorts if r["area"] == a and (only is None or r in only)]
        if not rs:
            continue
        out_.append(f"<h2>{E(T(lang, sv, en))}</h2>")
        for c in dict.fromkeys(r["country"] for r in rs):
            cr = [r for r in rs if r["country"] == c]
            if a != "japan":
                out_.append(f"<h3>{E(country(cr[0], lang))}</h3>")
            for reg in dict.fromkeys(r["region"] for r in cr):
                links = " · ".join(f'<a href="/{lang}/{r["id"]}/">{E(r["name"])}</a>' for r in cr if r["region"] == reg)
                out_.append(f"<p><b>{E(reg)}</b>: {links}</p>")
    return "\n".join(out_)


urls = []   # (path, {lang: path}) for the sitemap

# --- Start pages ---
START = {
    "sv": ("Yuki Report – snörapport, puder och lavinprognos för skidåkare",
           "Snöprognos timme för timme, puder, lavinläge, uppmätt snö och webbkameror för skidorter i Japan, Skandinavien och Alperna."),
    "en": ("Yuki Report – snow forecast, powder and avalanche conditions for skiers",
           "Hour-by-hour snow forecasts, powder, avalanche conditions, measured snow and webcams for ski resorts in Japan, Scandinavia and the Alps."),
}
alt_start = {"sv": "/sv/", "en": "/en/", "x-default": "/"}
for lang, (title, desc) in START.items():
    p = head(page, lang, title, desc, f"/{lang}/", alt_start)
    p = with_app(p, f"<h1>{E(title)}</h1><p>{E(desc)}</p>\n{resort_list(lang)}")
    os.makedirs(os.path.join(out, lang), exist_ok=True)
    open(os.path.join(out, lang, "index.html"), "w", encoding="utf-8").write(p)
urls.append(("/", alt_start))
# The root picks the language in the browser, as before; for search engines it is the default for both
p = head(page, "sv", START["sv"][0], START["sv"][1], "/", alt_start)
p = with_app(p, f"<h1>Yuki Report</h1><p>{E(START['sv'][1])}</p><p>{E(START['en'][1])}</p>"
                f'<p><a href="/sv/">Svenska</a> · <a href="/en/">English</a></p>')
open(os.path.join(out, "index.html"), "w", encoding="utf-8").write(p)

# --- One page per resort and language ---
for r in resorts:
    alt = {"sv": f"/sv/{r['id']}/", "en": f"/en/{r['id']}/", "x-default": f"/en/{r['id']}/"}
    sn, dp, ncam = snow_numbers(r), depth(r), len(cams[r["area"]].get("resorts", {}).get(r["id"], []))
    mid = round((r["base"] + r["top"]) / 2)
    same = [x for x in resorts if x["region"] == r["region"] and x["id"] != r["id"]]
    for lang in ("sv", "en"):
        place = f"{r['region']}, {country(r, lang)}" if r["area"] != "japan" else f"{r['region']}, Japan"
        title = T(lang, f"{r['name']}: snöprognos, puder och lavinläge | Yuki Report",
                  f"{r['name']} snow forecast, powder and avalanche conditions | Yuki Report")
        snow_txt = ""
        if sn:
            snow_txt = T(lang, f"{sn[0]} cm nysnö väntas de kommande 3 dygnen på {mid} m, och {sn[1]} cm har fallit de senaste 3 dygnen.",
                         f"{sn[0]} cm of new snow is expected over the next 3 days at {mid} m, and {sn[1]} cm has fallen in the last 3 days.")
        desc = T(lang, f"Snöprognos för {r['name']} ({place}). " + (snow_txt + " " if snow_txt else "")
                 + "Timme för timme, snötyp, lavinläge, uppmätt snödjup och webbkameror.",
                 f"Snow forecast for {r['name']} ({place}). " + (snow_txt + " " if snow_txt else "")
                 + "Hour by hour, snow type, avalanche conditions, measured snow depth and webcams.")
        ld = {"@context": "https://schema.org", "@type": "Mountain" if r.get("kind") == "tour" else "SkiResort", "name": r["name"], "url": SITE + alt[lang],
              "geo": {"@type": "GeoCoordinates", "latitude": r["lat"], "longitude": r["lon"]},
              "address": {"@type": "PostalAddress", "addressRegion": r["region"], "addressCountry": CC_ISO.get(r["country"], "JP")}}
        p = head(page, lang, title, desc, alt[lang], alt, ld)
        parts = [f"<h1>{E(r['name'])}{(' ' + E(r['jp'])) if r.get('jp') else ''}</h1>",
                 f"<p>{E(place)} · " + (f"{T(lang, 'topptur', 'ski touring')} · start {r['base']} m" if r.get("kind") == "tour" else f"{T(lang, 'dal', 'base')} {r['base']} m")
                 + f" · {T(lang, 'topp', 'top')} {r['top']} m</p>"]
        if snow_txt:
            parts.append(f"<p>{E(snow_txt)}</p>")
        if dp:
            parts.append("<p>" + E(T(lang, f"Snödjup: {dp[2]} cm, uppmätt" + (f" på {dp[1]} m" if dp[1] else "") + f" vid {dp[0]}.",
                                     f"Snow depth: {dp[2]} cm, measured" + (f" at {dp[1]} m" if dp[1] else "") + f" at {dp[0]}.")) + "</p>")
        if ncam:
            parts.append("<p>" + E(T(lang, f"{ncam} webbkameror vid backen." if ncam > 1 else "En webbkamera vid backen.",
                                     f"{ncam} webcams at the slopes." if ncam > 1 else "One webcam at the slopes.")) + "</p>")
        parts.append(f"<h2>{E(T(lang, 'Om ' + r['name'], 'About ' + r['name']))}</h2>" + "".join(f"<p>{E(t)}</p>" for t in about_facts(r, lang)))
        parts.append("<p>" + E(T(lang, f"Yuki Report visar snöprognosen för {r['name']} timme för timme, snötyp och puderdagar, vad vädermodellerna säger, lavinläget, snödjupet och en karta med liftar och parkering.",
                                 f"Yuki Report shows the snow forecast for {r['name']} hour by hour, snow type and powder days, what the weather models say, the avalanche conditions, the snow depth and a map with lifts and parking.")) + "</p>")
        if same:
            parts.append(f"<h2>{E(T(lang, 'Fler orter i ' + r['region'], 'More resorts in ' + r['region']))}</h2><p>"
                         + " · ".join(f'<a href="/{lang}/{x["id"]}/">{E(x["name"])}</a>' for x in same) + "</p>")
        parts.append(f'<p><a href="/{lang}/">{E(T(lang, "Alla skidorter", "All ski resorts"))}</a> · '
                     f'<a href="{alt["en" if lang == "sv" else "sv"]}">{"English" if lang == "sv" else "Svenska"}</a></p>')
        p = with_app(p, "\n".join(parts))
        os.makedirs(os.path.join(out, lang, r["id"]), exist_ok=True)
        open(os.path.join(out, lang, r["id"], "index.html"), "w", encoding="utf-8").write(p)
    urls.append((alt["sv"], alt))
    urls.append((alt["en"], alt))
urls += [("/sv/", alt_start), ("/en/", alt_start)]

# An unknown address gets the app, which shows the start page (GitHub Pages answers 404 with this file)
shutil.copy(os.path.join(out, "index.html"), os.path.join(out, "404.html"))

# --- Sitemap and robots.txt ---
sm = ['<?xml version="1.0" encoding="UTF-8"?>',
      '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">']
for path, alt in urls:
    sm.append(f"<url><loc>{SITE + path}</loc><lastmod>{today}</lastmod>"
              + "".join(f'<xhtml:link rel="alternate" hreflang="{l}" href="{SITE + p_}"/>' for l, p_ in alt.items()) + "</url>")
sm.append("</urlset>")
open(os.path.join(out, "sitemap.xml"), "w").write("\n".join(sm) + "\n")
open(os.path.join(out, "robots.txt"), "w").write(f"User-agent: *\nAllow: /\n\nSitemap: {SITE}/sitemap.xml\n")
print(f"built {len(resorts)} resorts x 2 languages, {len(urls)} URLs in the sitemap", file=sys.stderr)
