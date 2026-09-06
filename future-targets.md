# Future Targets

Ideas and features considered for morning-coffee but not yet built. Each heading
captures enough context to pick the work up later.

## Weather radar map

Add a radar / precipitation map to the Weather panel (or as its own panel).

**Why it's not done yet:** our weather provider, [Open-Meteo](https://open-meteo.com),
is a JSON numeric-data API only — it has **no radar imagery, map tiles, or WMS**. (It
does expose model-derived `minutely_15` precipitation *data* that could drive a numeric
nowcast, but nothing renderable as a radar picture.)

**Proposed approach — RainViewer tiles over an OpenStreetMap base (no API key):**

- **Radar tiles:** [RainViewer](https://www.rainviewer.com/) offers a free, key-less
  public API.
  - Frame index: `https://api.rainviewer.com/public/weather-maps.json` returns a `host`
    plus past and forecast radar frames (each with a `path`) — read these dynamically,
    don't hardcode.
  - Tile URL: `{host}{path}/{size}/{z}/{x}/{y}/{color}/{options}.png` (size 256/512, max
    zoom 7, `{options}` = `{smooth}_{snow}`, e.g. `1_0`).
  - **Terms:** attribution requested (link to rainviewer.com); usage is
    **personal/educational only** — revisit the provider if the app ever goes commercial.
- **Base map:** OpenStreetMap raster XYZ tiles
  (`https://tile.openstreetmap.org/{z}/{x}/{y}.png`) as a base layer, radar as a
  semi-transparent overlay. Requires "© OpenStreetMap contributors" attribution, a valid
  User-Agent, and adherence to the OSM tile usage policy (no bulk use).
- **Rendering in Kivy:** Kivy has no built-in map widget. The realistic path is the
  community [`kivy_garden.mapview`](https://github.com/kivy-garden/mapview) widget (a
  slippy map supporting XYZ base tiles + overlay layers). This adds a dependency and
  should be validated for the transparent radar overlay + animated frame stepping.

**Alternatives considered:**

- **OpenWeatherMap** weather map tiles (`tile.openweathermap.org/map/{layer}/{z}/{x}/{y}.png`,
  e.g. `precipitation_new`) — simple XYZ tiles, but requires a free API key.
- **NOAA/NWS** (US-only, public domain) — authoritative MRMS/NEXRAD radar via OGC WMS at
  `opengeo.ncep.noaa.gov`, but it's WMS (needs a WMS-capable renderer, not plain XYZ) and
  US-coverage only.

**Open questions to resolve before building:** acceptable to add the `mapview`
dependency? RainViewer's personal-use terms acceptable, or pick a keyed/authoritative
provider? Animate radar frames over time or show a single latest frame?
