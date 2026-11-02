# OpenStreetMap-data

Filerna i den här mappen kommer från [OpenStreetMap](https://www.openstreetmap.org/), hämtade via Overpass API och Nominatim:

- `pois.json`: onsen, bastur, toaletter, parkeringar och ställplatser runt varje ort
- `lifts.json`: liftarnas sträckning
- `scandinavia.json`: orterna i Sverige, Norge och Finland (läge och län från OSM; topp- och dalhöjd från Open-Meteos höjddata)
- `scandinavia_found.json`: skidområden som hittats i OSM, indata till `scandinavia.json`

- `places/`: samma data uppdelad i en fil per ort (byggs med `tools/build_places.py`), som appen läser

**Licens:** © OpenStreetMap-bidragsgivare. Datan är tillgänglig under [Open Database License (ODbL) 1.0](https://opendatacommons.org/licenses/odbl/1-0/), **inte** under MIT-licensen som gäller för koden i repot. Se även <https://www.openstreetmap.org/copyright>.
