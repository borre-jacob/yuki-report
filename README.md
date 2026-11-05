# Yuki Report

Snöprognos, lavinläge, liftar, onsen/bastu, toaletter och parkering för skidresor med husbil i **Japan**, **Skandinavien** (Sverige, Norge, Finland) och **Alperna** (Österrike, Schweiz, Frankrike, Italien).

- **Startsidan** har ett val mellan Japan, Skandinavien och Alperna och rankar orterna efter hur mycket snö som fallit de senaste 3 dygnen, eller hur mycket som väntas de kommande 3 dygnen.
- **Varje ort** har en detaljerad prognos (topp och dal, timme för timme, nollgradersgräns) och en karta med liftar, onsen, toaletter, michi-no-eki och andra ställplatser, med vägbeskrivning i Google Maps.
- **Svenska och engelska:** knappen i sidhuvudet byter språk. Svenska telefoner får svenska från början, alla andra engelska. Text i koden skrivs som `T("svenska", "English")`, och fast text i sidan som ett par med klasserna `t-sv` och `t-en`.

Appen är `index.html`, med platsdata per ort i `data/osm/places/`. Kör den med en lokal webbserver (`python3 -m http.server`) eller publicera repot med GitHub Pages. Direkt från filen fungerar inte, eftersom platsdatan hämtas med fetch.

## Installera som app

Yuki Report är en PWA och fungerar offline: prognoser, lavinläge och kartdelar som du redan har tittat på finns kvar utan täckning (med en gul banner "Offline – visar senast hämtade data").

- **iPhone:** öppna sidan i Safari → Dela → *Lägg till på hemskärmen*.
- **Android:** öppna sidan i Chrome → menyn ⋮ → *Installera app*.

Service workern ligger i `sw.js`. Höj `VERSION` där när `sw.js`, ikonerna, typsnitten, `integritet.html` eller manifestet ändras. Då visar appen "Ny version finns – ladda om". Ändringar i `index.html` kommer med automatiskt.

## Datakällor

- Väder: [Open-Meteo](https://open-meteo.com/). Snön för alla orter i översikten hämtas centralt var tredje timme av GitHub Actions (`.github/workflows/pages.yml` kör `tools/fetch_snow.py`) och publiceras som `data/snow/<område>.json` tillsammans med appen, utan att committas. Antalet anrop blir då detsamma hur många som än använder appen. Är filen äldre än 4 timmar hämtar appen direkt från Open-Meteo. Detaljsidan för en ort hämtar alltid live.
- Lavinprognos Norge: [Varsom](https://www.varsom.no/) (NVE), hämtas live i appen.
- Lavinprognos Alperna: de nationella och regionala lavintjänsterna (bl.a. SLF, Météo-France, Euregio/avalanche.report, AINEVA-regionerna) via [EAWS](https://www.avalanches.org/), som speglas på static.avalanche.report. Hämtas live i appen; varje ort är kopplad till sin prognosregion med `tools/assign_eaws.py`.
- Lavinprognos Sverige: [lavinprognoser.se](https://www.lavinprognoser.se/) (Naturvårdsverket), hämtas varje morgon tillsammans med JAN.
- Lavinprognos Japan: [Japan Avalanche Network](https://data.nadare.jp/avalanche_informations?locale=en). Hämtas varje morgon av GitHub Actions (`.github/workflows/avalanche.yml`) och byggs in i `index.html`.

Appen publiceras av arbetsflödet "Publicera appen" (`.github/workflows/pages.yml`), som kräver att Settings → Pages → Source är satt till "GitHub Actions".
- Liftar, onsen, toaletter och parkering: [OpenStreetMap](https://www.openstreetmap.org/copyright) via Overpass API. Datan ligger i en fil per ort i `data/osm/places/` som appen hämtar när man öppnar orten. Service workern sparar orterna för användning utan täckning: små områden automatiskt, större med knappen "Spara offline".
- Karta: [OpenFreeMap](https://openfreemap.org/), eller Google Maps om du lägger in en egen API-nyckel under "Kartinställning" längst ner på sidan.

## Lägga till orter

Orter i ett nytt område hittas i OpenStreetMap, får län/region och läggs in i appen:

```bash
python3 tools/discover_resorts.py data/osm/alps.json data/osm/alps_found.json --countries AT,CH,FR,IT --alps --top 300
python3 tools/merge_resorts.py data/osm/alps.json data/osm/alps_found.json
python3 tools/assign_eaws.py data/osm/alps.json
python3 tools/inject_resorts.py index.html data/osm/alps.json alps "Alperna"
```

Sedan hämtas liftar och platser (se nedan) och `tools/build_places.py` körs.


Nya orter läggs i en JSON-fil med ungefärliga koordinater och placeras sedan exakt utifrån liftarna:

```bash
python3 tools/refine_resorts.py data/scandinavia_approx.json data/osm/scandinavia.json
```

## Uppdatera platsdatan

```bash
python3 tools/fetch_pois_batch.py index.html data/osm/pois.json
python3 tools/fetch_lifts.py index.html data/osm/lifts.json
python3 tools/build_places.py data/osm/pois.json data/osm/lifts.json data/osm/places
python3 tools/fetch_avalanche.py data/avalanche.json
python3 tools/inject_avalanche.py index.html data/avalanche.json
```

`fetch_pois.py` hoppar över orter som redan finns i `data/osm/pois.json`. Ta bort filen för att hämta allt på nytt. Overpass-servrarna är ofta överbelastade, så räkna med att det tar en stund.

## Integritet

Appen samlar inte in några personuppgifter. Integritetspolicyn ligger i [`integritet.html`](integritet.html) och länkas från sidfoten. Uppdatera den om appen börjar använda en ny extern tjänst.

## Licens och källor

© 2026 Jacob Borre.

- **Koden** (HTML, CSS, JavaScript, `sw.js`, skripten i `tools/`, ikonerna) är licensierad under [MIT](LICENSE).
- **OpenStreetMap-data** (orter, liftar, onsen, toaletter, parkering) ligger i [`data/osm/`](data/osm/) (källfiler och en fil per ort i `places/`). Den är © OpenStreetMap-bidragsgivare och licensierad under [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/), inte MIT. Se [data/osm/README.md](data/osm/README.md).
- **Väder** från [Open-Meteo](https://open-meteo.com/) under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
- **Kartstil och kartrutor** från [OpenFreeMap](https://openfreemap.org/) (© OpenMapTiles, © OpenStreetMap-bidragsgivare).
- **Lavinprognoser** från Japan Avalanche Network, Varsom (NVE), Naturvårdsverket (lavinprognoser.se) och de europeiska lavinvarningstjänsterna i [EAWS](https://www.avalanches.org/). Texterna tillhör respektive utgivare.
- **Typsnitten** IBM Plex Sans, IBM Plex Mono och Zen Kaku Gothic New ligger i [`fonts/`](fonts/) (bara latinska tecken) och är licensierade under SIL Open Font License 1.1, se licensfilerna där. De hämtas inte från Google Fonts, så inga besökares IP-adresser skickas dit.
- **Google Maps** används bara med användarens egen API-nyckel. Kartrutor och skript från Google cachas aldrig av appen.
