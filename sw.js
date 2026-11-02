/* Yuki Radar service worker: makes the app work offline.
   - App files (index.html, manifest, icons) and the map libraries are precached. The page itself is
     network-first so the daily avalanche update is picked up.
   - Lifts and facilities per resort (data/osm/places/): stale-while-revalidate. A resort is kept once it
     has been opened, and the app's "Spara offline" button fetches a whole area.
   - Open-Meteo and Varsom: network-first, falling back to the last cached answer.
   - Overpass (OpenStreetMap): stale-while-revalidate.
   - OpenFreeMap: style, fonts and sprites stale-while-revalidate; visited map tiles are kept,
     at most TILE_MAX of them (oldest removed first).
   - Google Maps tiles and scripts are never cached (Google's terms): they go straight to the network.
   Bump VERSION when this file or the precache list changes; the app then offers "Ny version finns". */
const VERSION = "v3";
const SHELL = "yuki-shell-" + VERSION;
const LIBS = "yuki-libs-" + VERSION;
const DATA = "yuki-data";
const MAPMETA = "yuki-map-meta";
const TILES = "yuki-tiles";
const FONTS = "yuki-fonts";
const PLACES = "yuki-places";
const KEEP = [SHELL, LIBS, DATA, MAPMETA, TILES, FONTS, PLACES];
const TILE_MAX = 1500;
const NET_TIMEOUT = 8000;

const SHELL_FILES = [
  "./", "index.html", "manifest.webmanifest",
  "icons/icon.svg", "icons/logo.svg", "icons/icon-192.png", "icons/icon-512.png",
  "icons/icon-maskable-192.png", "icons/icon-maskable-512.png", "icons/apple-touch-icon.png",
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

// Google Maps (tiles, scripts, images) — but not Google Fonts, which may be cached
const isGoogleMaps = h => /(^|\.)(google\.[a-z.]+|googleapis\.com|gstatic\.com|ggpht\.com|googleusercontent\.com)$/.test(h)
  && !/^fonts\.(googleapis|gstatic)\.com$/.test(h);

self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  const h = url.hostname;
  if (isGoogleMaps(h)) return;

  if (req.mode === "navigate") return e.respondWith(page(req));
  if (url.origin === location.origin && url.pathname.includes("/data/osm/places/")) return e.respondWith(staleWhileRevalidate(req, PLACES));
  if (url.origin === location.origin) return e.respondWith(cacheFirst(req, SHELL));
  if (h === "api.open-meteo.com" || h === "api01.nve.no") return e.respondWith(networkFirst(req, DATA));
  if (/overpass/.test(h) || url.pathname.includes("/overpass/")) return e.respondWith(staleWhileRevalidate(req, DATA));
  if (h === "tiles.openfreemap.org"){
    return e.respondWith(/\.pbf$/.test(url.pathname) ? tile(req, e) : staleWhileRevalidate(req, MAPMETA));
  }
  if (/^fonts\.(googleapis|gstatic)\.com$/.test(h)) return e.respondWith(staleWhileRevalidate(req, FONTS));
  if (["cdnjs.cloudflare.com", "cdn.jsdelivr.net", "unpkg.com"].includes(h)) return e.respondWith(cacheFirst(req, LIBS));
});

function timeout(promise, ms){
  return Promise.race([promise, new Promise((_, rej) => setTimeout(() => rej(new Error("timeout")), ms))]);
}

// The page: fresh from the network when possible (picks up new avalanche data), else the cached copy
async function page(req){
  const cache = await caches.open(SHELL);
  try {
    const res = await timeout(fetch(req), NET_TIMEOUT);
    if (res.ok) cache.put("index.html", res.clone());
    return res;
  } catch {
    return (await cache.match("index.html")) || (await cache.match("./")) || Response.error();
  }
}

async function cacheFirst(req, name){
  const cache = await caches.open(name);
  const hit = await cache.match(req, {ignoreSearch: name === SHELL});
  if (hit) return hit;
  const res = await fetch(req);
  if (res.ok || res.type === "opaque") cache.put(req, res.clone());
  return res;
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
