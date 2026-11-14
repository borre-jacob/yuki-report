/* Yuki Report service worker: makes the app work offline.
   - App files (index.html, privacy page, manifest, icons, fonts) and the map libraries are precached. The page itself is
     network-first so the daily avalanche update is picked up.
   - Lifts and facilities per resort (data/osm/places/): stale-while-revalidate. A resort is kept once it
     has been opened, and the app's "Spara offline" button fetches a whole area.
   - Snow, avalanche bulletins and measured snow for all resorts (data/snow/, data/avalanche/, data/obs/, fetched
     centrally every 3 hours) and the webcam list (data/cams/, daily),
     Open-Meteo, Varsom and EAWS: network-first,
     falling back to the last cached answer.
   - Overpass (OpenStreetMap): stale-while-revalidate.
   - OpenFreeMap: style, fonts and sprites stale-while-revalidate; visited map tiles are kept,
     at most TILE_MAX of them (oldest removed first).
   - Google Maps tiles and scripts are never cached (Google's terms): they go straight to the network.
   - Cloudflare Web Analytics (static.cloudflareinsights.com) and Windy's webcam images and players are never cached:
     other hosts go straight to the network.
   Bump VERSION when this file or the precache list changes; the app then offers "Ny version finns". */
const VERSION = "v17";
const SHELL = "yuki-shell-" + VERSION;
const LIBS = "yuki-libs-" + VERSION;
const DATA = "yuki-data";
const MAPMETA = "yuki-map-meta";
const TILES = "yuki-tiles";
const PLACES = "yuki-places";
const KEEP = [SHELL, LIBS, DATA, MAPMETA, TILES, PLACES];  // others (e.g. the old Google Fonts cache) are removed
const TILE_MAX = 1500;
const NET_TIMEOUT = 8000;

const SHELL_FILES = [
  "./", "index.html", "manifest.webmanifest",
  "icons/icon.svg", "icons/logo.svg", "icons/icon-192.png", "icons/icon-512.png",
  "icons/icon-maskable-192.png", "icons/icon-maskable-512.png", "icons/apple-touch-icon.png",
  "integritet.html", "fonts/fonts.css",
  "fonts/ibm-plex-mono-400-latin-ext.woff2",
  "fonts/ibm-plex-mono-400-latin.woff2",
  "fonts/ibm-plex-mono-500-latin-ext.woff2",
  "fonts/ibm-plex-mono-500-latin.woff2",
  "fonts/ibm-plex-sans-latin-ext.woff2",
  "fonts/ibm-plex-sans-latin.woff2",
  "fonts/zen-kaku-gothic-new-500-latin-ext.woff2",
  "fonts/zen-kaku-gothic-new-500-latin.woff2",
  "fonts/zen-kaku-gothic-new-700-latin-ext.woff2",
  "fonts/zen-kaku-gothic-new-700-latin.woff2",
  "fonts/zen-kaku-gothic-new-900-latin-ext.woff2",
  "fonts/zen-kaku-gothic-new-900-latin.woff2",
];
// Versioned URLs, so they never change: cache-first
const LIB_FILES = [
  "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css",
  "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js",
  "https://cdnjs.cloudflare.com/ajax/libs/leaflet.markercluster/1.5.3/MarkerCluster.css",
  "https://cdnjs.cloudflare.com/ajax/libs/leaflet.markercluster/1.5.3/leaflet.markercluster.js",
  "https://cdnjs.cloudflare.com/ajax/libs/maplibre-gl/4.7.1/maplibre-gl.css",
  "https://cdnjs.cloudflare.com/ajax/libs/maplibre-gl/4.7.1/maplibre-gl.js",
  "https://cdn.jsdelivr.net/npm/@maplibre/maplibre-gl-leaflet@0.0.22/leaflet-maplibre-gl.js",
  "https://unpkg.com/leaflet.gridlayer.googlemutant@0.14.1/dist/Leaflet.GoogleMutant.js",
];

self.addEventListener("install", e => {
  e.waitUntil((async () => {
    await (await caches.open(SHELL)).addAll(SHELL_FILES.map(u => new Request(u, {cache: "reload"})));
    // A CDN hiccup must not stop the install: the libraries are also cached on first use
    const libs = await caches.open(LIBS);
    await Promise.all(LIB_FILES.map(u => libs.add(new Request(u, {mode: "cors"})).catch(() => {})));
  })());
  // No skipWaiting here: the page shows "Ny version finns" and the user decides when to reload
});

self.addEventListener("activate", e => {
  e.waitUntil((async () => {
    for (const k of await caches.keys()) if (!KEEP.includes(k)) await caches.delete(k);
    await self.clients.claim();
  })());
});

self.addEventListener("message", e => {
  if (e.data?.type === "SKIP_WAITING") self.skipWaiting();
});

// Google Maps (tiles, scripts, images)
const isGoogleMaps = h => /(^|\.)(google\.[a-z.]+|googleapis\.com|gstatic\.com|ggpht\.com|googleusercontent\.com)$/.test(h);

self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  const h = url.hostname;
  if (isGoogleMaps(h)) return;

  if (req.mode === "navigate") return e.respondWith(page(req));
  if (url.origin === location.origin && url.pathname.includes("/data/osm/places/")) return e.respondWith(staleWhileRevalidate(req, PLACES));
  if (url.origin === location.origin && /\/data\/(snow|avalanche|obs|cams)\//.test(url.pathname)) return e.respondWith(networkFirst(req, DATA));
  if (url.origin === location.origin) return e.respondWith(cacheFirst(req, SHELL));
  // Weather and avalanche bulletins: fresh when online, the last answer offline (out in the mountains)
  if (h === "api.open-meteo.com" || h === "api01.nve.no" || h === "static.avalanche.report") return e.respondWith(networkFirst(req, DATA));
  if (/overpass/.test(h) || url.pathname.includes("/overpass/")) return e.respondWith(staleWhileRevalidate(req, DATA));
  if (h === "tiles.openfreemap.org"){
    return e.respondWith(/\.pbf$/.test(url.pathname) ? tile(req, e) : staleWhileRevalidate(req, MAPMETA));
  }
  if (["cdnjs.cloudflare.com", "cdn.jsdelivr.net", "unpkg.com"].includes(h)) return e.respondWith(cacheFirst(req, LIBS));
});

function timeout(promise, ms){
  return Promise.race([promise, new Promise((_, rej) => setTimeout(() => rej(new Error("timeout")), ms))]);
}

// A page (the app, a resort page such as /sv/hemsedal/, or the privacy page): fresh from the network when possible
// (picks up new avalanche data), else the cached copy. Each page is stored under its own address; a resort page
// that was never opened falls back to the app, which shows the resort from the address.
async function page(req){
  const cache = await caches.open(SHELL);
  const path = new URL(req.url).pathname;
  const name = path.endsWith("/integritet.html") ? "integritet.html" : path === "/" || path.endsWith("/index.html") ? "index.html" : path;
  try {
    // no-cache: always ask GitHub (cheap 304 when unchanged) instead of the browser's 10-minute HTTP cache
    const res = await timeout(fetch(req.url, {cache: "no-cache", credentials: "same-origin"}), NET_TIMEOUT);
    if (res.ok) cache.put(name, res.clone());
    return res;
  } catch {
    return (await cache.match(name)) || (await cache.match("index.html")) || (await cache.match("./")) || Response.error();
  }
}

async function cacheFirst(req, name){
  const cache = await caches.open(name);
  const hit = await cache.match(req, {ignoreSearch: name === SHELL});
  if (hit) return hit;
  const res = await fetch(req);
  if (res.ok || res.type === "opaque") cache.put(req, res.clone()).then(() => pruneApp(cache, req.url));
  return res;
}

// The app's script and style have the content hash in their name (app.<hash>.js, built by tools/build_site.py), so
// each version is a new file. Keep the three newest of each, for pages cached with an older version.
async function pruneApp(cache, url){
  const m = /\/app\.[0-9a-f]+\.(js|css)$/.exec(new URL(url).pathname);
  if (!m) return;
  const old = (await cache.keys()).filter(k => new RegExp(`/app\\.[0-9a-f]+\\.${m[1]}$`).test(new URL(k.url).pathname));
  for (const k of old.slice(0, -3)) await cache.delete(k);
}

// Stores the response with the time it was fetched, so the app can say how old offline data is
async function putStamped(cache, req, res){
  const headers = new Headers(res.headers);
  headers.set("x-yuki-cached-at", new Date().toISOString());
  await cache.put(req, new Response(await res.clone().blob(), {status: res.status, statusText: res.statusText, headers}));
}

// Marks a cached answer so the page knows it is showing old data (and can show the offline banner)
async function asFallback(hit){
  const headers = new Headers(hit.headers);
  headers.set("x-yuki-offline", hit.headers.get("x-yuki-cached-at") || "");
  headers.append("access-control-expose-headers", "x-yuki-offline");
  return new Response(await hit.blob(), {status: hit.status, statusText: hit.statusText, headers});
}

async function networkFirst(req, name){
  const cache = await caches.open(name);
  try {
    const res = await timeout(fetch(req), NET_TIMEOUT);
    if (res.ok) await putStamped(cache, req, res);
    return res;
  } catch (err){
    const hit = await cache.match(req);
    if (hit) return asFallback(hit);
    throw err;
  }
}

async function staleWhileRevalidate(req, name){
  const cache = await caches.open(name);
  const hit = await cache.match(req);
  const fresh = fetch(req).then(async res => { if (res.ok) await putStamped(cache, req, res); return res; });
  if (hit){ fresh.catch(() => {}); return hit; }
  return fresh;
}

// Map tiles: URLs contain the tile set's date, so a cached tile never goes stale
let tilePuts = 0;
async function tile(req, e){
  const cache = await caches.open(TILES);
  const hit = await cache.match(req);
  if (hit) return hit;
  const res = await fetch(req);
  if (res.ok){
    await cache.put(req, res.clone());
    if (++tilePuts % 50 === 0) e.waitUntil(trimTiles(cache));
  }
  return res;
}

async function trimTiles(cache){
  const keys = await cache.keys();  // insertion order: oldest first
  for (const k of keys.slice(0, Math.max(0, keys.length - TILE_MAX))) await cache.delete(k);
}
