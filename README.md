# Yuki Report

https://yukireport.com

Snöprognos, lavinläge, liftar, onsen/bastu, toaletter och parkering för skidresor med husbil i **Japan**, **Skandinavien** (Sverige, Norge, Finland) och **Alperna** (Österrike, Schweiz, Frankrike, Italien).

- **Startsidan** har ett val mellan Japan, Skandinavien och Alperna och rankar orterna efter hur mycket snö som fallit de senaste 3 dygnen, eller hur mycket som väntas de kommande 3 dygnen.
- **Flera vädermodeller** på ortsidan: snön vid toppen hämtas också från ECMWF, ICON, GFS och den bästa regionala modellen (JMA i Japan, MET Norway i Skandinavien, Météo-France i Alperna). Under den stora siffran visar en stapel modellernas spann för de kommande 3 dygnen med en markering för prognosens värde, grön med "Säker prognos" när de är överens (högst 5 cm isär, eller 40 % av mittvärdet) och orange med "Osäker prognos" annars; är de oense står det också i sammanfattningens mening. Dygnsstaplarna har prognosens siffra direkt på stapeln och ett streckat lila fält för spannet där små lila siffror visar var fältet slutar (toppen ovanför fältet, botten inne i stapeln), och varje dagkort en bricka bredvid snömängden ("✓ säker" eller "± 4–17 cm") och varje modells snö när kortet öppnas. Hämtas efter huvudprognosen, så sidan väntar aldrig på den.
- **Snötyp**: torrt puder (−7 °C eller kallare medan snön faller), puder (upp till −3 °C), torr nysnö (kall snö men under 10 cm, för puder krävs minst 10 cm), tung snö eller blöt snö (plusgrader eller regn), och "i hård vind" när medelvinden under snöfallet är minst 8 m/s. Visas i ortens sammanfattning och på dagkorten. Puderdag på ortsidan kräver torrt puder eller puder.
- **Listan följer kartan**: zoomar eller drar man kartan visar listan bara orterna i kartans vy ("Visar 7 av 33 orter i kartans vy", med *Visa alla* för att zooma ut igen). Ett klick på en ort i listan markerar den med en lila ring på kartan och zoomar in måttligt (nivå 8,5, ungefär en region; den valda ortens prick ritas ovanpå eventuella grupper); ett andra klick öppnar orten. Ett klick på en prick på kartan öppnar orten direkt.
- **Sök**: fältet ovanför listan är både sökruta och regionval. Tomt visar det regionerna (och *★ Mina favoriter*) som förut. När man skriver visas matchande regioner, som filtrerar listan, och orter i alla områden, som öppnas direkt. Sökningen bryr sig inte om stora bokstäver, accenter, mellanslag eller bindestreck och hittar även japanska namn.
- **Favoriter**: stjärnan vid en ort i listan eller knappen på ortsidan sparar orten som favorit, och valet *★ Mina favoriter* i regionlistan visar bara favoriterna i listan och på kartan. Favoriterna sparas på enheten, utan konto.
- **Inställningar** finns bakom menyknappen (☰) uppe till höger: språk, ljust eller mörkt läge, enheter för temperatur (°C/°F), snö (cm/tum), vind (m/s, km/h, mph, knop) och höjd (meter/fot), och kartan (egen Google Maps-nyckel). Datan är alltid metrisk och räknas om när den visas.
- **Varje ort** börjar med en sammanfattning (snö de kommande 3 dygnen, puderdag, regn i dalen, vind och lavinfara) och har sedan prognosen i tre flikar: **Dagar** (ett kort per dag, som fälls ut till ett meteogram timme för timme), **Tabell** (förmiddag, eftermiddag och natt med snö på tre höjder, temperatur och vind) och **Höjd** (var i backen det blir snö eller regn). Sedan kommer lavinläget och en karta med liftar, onsen, toaletter, michi-no-eki och andra ställplatser, med vägbeskrivning i Google Maps.
- **Meteogrammet** i ett utfällt dagkort visar dygnet timme för timme på samma tidsaxel: väderikon var tredje timme (från molnighet och nederbörd, måne på natten), temperaturkurva (blå under noll, orange över), snö per timme som staplar mot en skala i cm (regn i grönt), vindpilar med medelvind och byar (gult från 10 m/s, rött från 15 m/s), natten skuggad från soluppgång och solnedgång och en linje för nu på dagens kort. Tryck på en timme, eller håll musen över den, för alla värden. Snö och temperatur gäller mitten av berget, vinden toppen. Molnighet och soluppgång hämtas i samma anrop som resten av prognosen.
- **Toppturområden** (än så länge i Japan) visas på kartan som rundade fyrkanter med ▲ och i listan med märkningen *Topptur*. Ett område har toppen som `lat`/`lon` och `top`, och startplatsen (en parkering under toppen, den vanliga på vintern eller våren) som `slat`/`slon` och `base`, med `kind:"tour"`. Prognosen räknas mellan start och topp, vägbeskrivningen går till startplatsen, infokartan visar startplatsen (P) och områden inom Japan Avalanche Networks prognosområden får den officiella lavinprognosen (även Tateyama).
- **Snödjupet** högst upp på ortsidan är uppmätt när en mätstation står i själva skidområdet: högst 3 km från en lift och mellan 50 m under dalen och 100 m över toppen (den högsta sådana stationen används, och mätningen får vara högst 36 timmar gammal). Då står det till exempel "Snödjup 11 cm, uppmätt på 648 m, Hemsedal". Annars visas vädermodellens uppskattning vid toppen. Källor: JMA AMeDAS (Japan), SLF IMIS (Schweiz), GeoSphere Austria (Österrike), SMHI (Sverige, en mätning om dagen), FMI (Finland) och MET Norways Frost (Norge, kräver ett gratis klient-ID som hemligheten `FROST_CLIENT_ID` i GitHub).
- **Webbkameror** på ortsidan visar upp till fyra kameror från [Windy](https://www.windy.com/webcams) som står högst 3 km från någon av ortens liftar (från ortens punkt om liftar saknas), de högst belägna först. Bilden öppnar Windys tidsförlopp för dagen på plats. Listan hämtas en gång om dygnet (`tools/fetch_cams.py`, kräver hemligheten `WINDY_KEY` i GitHub) och publiceras som `data/cams/<område>.json`; höjden kommer från Open-Meteos höjd-API. Ortens officiella kameralänkar finns kvar i sidhuvudet.
- **Lavinläget** på ortsidan börjar med svaret: faronivå, en mening om var faran finns och vilka problem som gäller, och vad nivån betyder. Under det visas om vädret har ändrats sedan prognosen kom (nysnö, hård vind, regn eller värme), nivån i dag och i morgon när källan ger den, var på berget faran finns i förhållande till backens topp och dal, och lavinproblemen med ros, sannolikhet, storlek och råd. Sist kommer prognosens egen text, vädret sedan prognosen och närmaste dygnet, och en enda ansvarstext. Ligger orten utanför ett prognosområde visas inget grannområdes prognos, utan bara vädret. Små backar (under 350 m fallhöjd) får en kort text om liten lavinterräng.
- **Medlemskonton** (frivilliga) med [Supabase](https://supabase.com) i EU: inloggning med en e-postlänk utan lösenord, via *Logga in* i sidhuvudet eller menyn. Favoriter, nålar och spår är för medlemmar. Favoriterna följer med mellan enheter (de som fanns i telefonen innan flyttas till kontot vid första inloggningen). På infokartan sätter medlemmar nålar och spelar in *hikes* (vägen upp, streckad grön, startpunkten är hikingpointen) och *lines* (åket ner, lila) med telefonens GPS, ritar in dem för hand på kartan (höjderna längs linjen hämtas från Open-Meteos elevation-API, och spåret märks *ritad*) eller laddar upp en GPX-fil. Ett spår delas med andra medlemmar eller behålls privat, och bara linjen och höjden sparas, inga tider. En webbapp får GPS bara medan den är öppen, så inspelningen håller skärmen tänd (Screen Wake Lock), sparar spåret i telefonen medan den pågår och fortsätter om appen öppnas igen. Den som inte är inloggad ser bara hur många nålar, hikes och lines medlemmarna har delat. Tabeller och behörighetsregler finns i `supabase/schema.sql` (körs i Supabases SQL Editor). Inloggningsmejlen skickas från `noreply@yukireport.com` via Resend (SMTP i Supabase); mallarna finns i `supabase/email-magic-link.html` och länkar till den egna domänen (`?token_hash=…`), som appen bekräftar.
- **Svenska och engelska:** knappen i sidhuvudet byter språk. Svenska telefoner får svenska från början, alla andra engelska. Text i koden skrivs som `T("svenska", "English")`, och fast text i sidan som ett par med klasserna `t-sv` och `t-en`.

Appen är `index.html`, med platsdata per ort i `data/osm/places/`. Kör den med en lokal webbserver (`python3 -m http.server`) eller publicera repot med GitHub Pages. Direkt från filen fungerar inte, eftersom platsdatan hämtas med fetch.

## Adresser och sökmotorer

Varje ort har en egen adress på båda språken, till exempel `yukireport.com/sv/hemsedal/` och `/en/hemsedal/`, och startsidan finns på `/sv/` och `/en/`. Adressen bestämmer språket; `/` väljer som förut (sparat val, annars svenska på svenska telefoner). Gamla länkar som `/#hemsedal` flyttas till den nya adressen.

Sidorna byggs av `tools/build_site.py` i arbetsflödet, efter att snö, lavin, mätvärden och kameror har hämtats, och publiceras från `_site/`. Varje ortsida får egen titel och beskrivning med de senaste snösiffrorna, `canonical` och `hreflang` mellan språken, Open Graph för delning, schema.org-data (`SkiResort`) och en kort text med snö, uppmätt snödjup, kameror och länkar till orter i samma region, så att sökmotorer ser innehållet utan att köra appen. Appen startar sedan som vanligt och ersätter texten. Appens stil och skript läggs i `app.<hash>.css` och `app.<hash>.js`, som alla sidor delar. På de byggda sidorna laddas kartbiblioteken och appens skript med `defer` och kartornas stilmallar utan att blockera, så att sidans text visas direkt. Dessutom skapas `sitemap.xml`, `robots.txt` och `404.html`.

Lokalt fungerar `index.html` som förut (`python3 -m http.server`), men en ortadress laddad direkt kräver det byggda resultatet:

```bash
python3 tools/build_site.py . /tmp/yuki_site && python3 -m http.server 8766 --directory /tmp/yuki_site
```

## Installera som app

Yuki Report är en PWA och fungerar offline: prognoser, lavinläge och kartdelar som du redan har tittat på finns kvar utan täckning (med en gul banner "Offline – visar senast hämtade data").

- **iPhone:** öppna sidan i Safari → Dela → *Lägg till på hemskärmen*.
- **Android:** öppna sidan i Chrome → menyn ⋮ → *Installera app*.

Service workern ligger i `sw.js`. Höj `VERSION` där när `sw.js`, ikonerna, typsnitten, `integritet.html` eller manifestet ändras. Då visar appen "Ny version finns – ladda om". Ändringar i `index.html` kommer med automatiskt.

## Besöksstatistik

Besök räknas anonymt med [Cloudflare Web Analytics](https://www.cloudflare.com/web-analytics/), utan kakor eller lagring i webbläsaren. Skriptet laddas bara på yukireport.com, så lokala tester räknas inte, och service workern cachar det aldrig. Statistiken finns i Cloudflares konto under Analytics & Logs → Web Analytics. Integritetssidan beskriver vad som skickas.

## Datakällor

- Väder: [Open-Meteo](https://open-meteo.com/). Snön för alla orter i översikten hämtas centralt var tredje timme av GitHub Actions (`.github/workflows/pages.yml` kör `tools/fetch_snow.py`) och publiceras som `data/snow/<område>.json` tillsammans med appen, utan att committas. GitHub försenar och hoppar ibland över schemalagda körningar, så schemat körs varje timme men hämtar bara när den publicerade datan är äldre än 2,5 timmar. Misslyckas publiceringen försöker arbetsflödet igen efter en minut. Antalet anrop blir då detsamma hur många som än använder appen. Är filen äldre än 4 timmar hämtar appen direkt från Open-Meteo. Detaljsidan för en ort hämtar alltid live.
- Uppmätt snödjup: hämtas centralt var tredje timme i samma arbetsflöde (`tools/fetch_obs.py`, som läser liftarna i `data/osm/places/`) och publiceras som `data/obs/<område>.json` med ungefär en veckas värden för stationen i varje skidområde. JMA och SLF ger bara kort historik i ett anrop, så skriptet utgår från de publicerade filerna och fyller på.
- Lavinprognoser: [Japan Avalanche Network](https://data.nadare.jp/avalanche_informations?locale=en), [lavinprognoser.se](https://www.lavinprognoser.se/) (Naturvårdsverket), [Varsom](https://www.varsom.no/) (NVE) och de nationella och regionala lavintjänsterna i Alperna (bl.a. SLF, Météo-France, Euregio/avalanche.report, AINEVA-regionerna) via [EAWS](https://www.avalanches.org/), som speglas på static.avalanche.report. Alla hämtas centralt var tredje timme i samma arbetsflöde som snön (`tools/fetch_avalanche.py`) och publiceras som `data/avalanche/<område>.json`, med dagens och morgondagens prognos för Norge och Alperna och Naturvårdsverkets förväntade nivå för nästa dag. Med `AVAL_DATE=ÅÅÅÅ-MM-DD` hämtar skriptet en tidigare dag, för att testa utanför säsongen (JAN har bara säsongens senaste veckor kvar). Är filen äldre än 6 timmar frågar appen Varsom och EAWS direkt. Varje ort i Alperna är kopplad till sin prognosregion med `tools/assign_eaws.py`.

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
```

Snö- och lavinfilerna kan hämtas lokalt för att testa appen (mapparna är gitignorerade):

```bash
python3 tools/fetch_snow.py index.html data/snow
python3 tools/fetch_avalanche.py index.html data/avalanche
python3 tools/fetch_obs.py index.html data/obs
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
