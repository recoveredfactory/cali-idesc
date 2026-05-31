# Cali IDESC — Data Quirks & Errata

Field notes on the City of Cali IDESC GeoServer dataset and the gotchas hit while
pipelining it (`pipeline/`) and building the viewer (`viewer/`). Living document —
append as new quirks surface.

- **Source:** WFS/WMS `https://ws-idesc.cali.gov.co/geoserver/ows`
- **Scope:** 357 layers across 23 workspaces (catalog proven complete by
  `catalog_reconciliation`)
- **As of:** 2026-05-31 — full backfill: 356 layers materialized, 1 discarded.

---

## 1. Access & availability

- **One layer is permission-locked (HTTP 401).** `pot_2014:amb_ari_movimientos_masa`
  ("Áreas de riesgo — movimientos en masa" / landslide risk) returns `401
  Unauthorized` on GetFeature. It is **not** a data or reprojection bug — the
  layer is restricted server-side. Discarded; **356/357** is the real ceiling
  without credentials. If landslide-risk data is needed later, it requires IDESC
  auth.
- The server is occasionally flaky under load: GetFeature can 500 or time out
  mid-stream. The pipeline retries (`max_retries=4`, exponential backoff) and
  verifies completeness (see §2).

## 2. WFS retrieval quirks

- **GeoJSON works even though only GML 3.2 is advertised.** `outputFormat=
  application/json` is accepted and far easier to consume than the advertised GML.
- **`startIndex` paging is rejected on PK-less views.** Many layers are SQL views
  with no primary key; GeoServer errors "cannot do natural order without a primary
  key" if you page with `startIndex`. So we **stream the whole layer in one
  request** to disk (chunked, never fully in memory) and prove completeness from
  the JSON tail's `numberMatched` vs `numberReturned`.
- **Trust `numberMatched`/`numberReturned`, not the byte count.** A single unpaged
  request can return a 500 MB blob that truncates silently; the tail counts are the
  only reliable completeness signal. `numberMatched: "unknown"` happens — fall back
  to `numberReturned`.

## 3. Projection

- **Native CRS is EPSG:6249** (MAGNA-SIRGAS Cali urban grid, `col_urban`) for
  almost every layer → reprojected to EPSG:4326 with `ogr2ogr -s_srs EPSG:6249`.
  Source coordinates carry **no CRS tag**, so `-s_srs` must be forced.
- A handful declare an **unknown CRS** (`urn:ogc:def:crs:EPSG::404000`). Those are
  converted on their declared CRS without a forced source SRS.
- A prior run saw "Geometry extent outside [-180,180]" after reprojecting a layer
  with bad source coordinates (`dapm:epou_pev_vallas_publicitarias`). Did **not**
  recur in the clean backfill; if it returns, add `-skipfailures` to the
  reproject/convert step.

## 4. Numeric values stored as locale strings  ⚠️ important

Several "numeric" columns are stored as **strings with Spanish decimal commas**,
so GDAL/ogrinfo types them as `String` and they never show up as numeric fields:

| Layer | Field | Stored as | Should be |
|---|---|---|---|
| `dagma:obs_arb_arboles_1000_habitantes` | `f2006` … `f2036` | `"47439,499408"` | `47439.499408` |
| `pot_2014:nur_edificabilidad_ica` | `ica`, `icb` | `"1,7"`, `"1"` | `1.7`, `1.0` |

- **The original string representation is meaningful and must be preserved**
  (it's the authoritative source value). The fix is **additive**: keep the string
  column, add a coerced numeric sibling.
- **Proven RAM-safe recipe** (streaming, no giant JSON load) — coerce while keeping
  the original:

  ```sh
  ogr2ogr -f GeoJSON -dialect SQLITE \
    -sql "SELECT *, CAST(REPLACE(f2006, ',', '.') AS REAL) AS f2006_num FROM \"<layer>\"" \
    out.geojson in.geojson
  ```

  Verified: `f2006 "47439,499408"` → `f2006_num 47439.499408`.
- **Gotcha:** the GeoJSON's internal OGR layer name is `<key>.fc` (inherited from
  the `<key>.fc.json` raw file), **not** the filename stem — SQL `FROM` needs the
  `.fc` name.

## 5. Graduated / choropleth data (not 3D)

Many polygon & point layers are **choropleths** — a numeric/ordinal value meant to
drive a graduated color ramp, *not* extrusion. Common shape: an ordinal class
field + a label + a continuous value.

| Layer | Geom | Value fields |
|---|---|---|
| `dagma:obs_arb_densidad_arborea` (tree density) | 242 polygons | `gridcode` 1–4, `texto` "Baja…Alta", `valor` |
| `dagma:obs_arb_arboles_1000_habitantes` | 325 polygons | `arb_hab`, yearly `f20xx` (see §4) |
| `dapm:…_estrato_urbano…` (socio-economic stratum) | polygons | `estrato` 1–6 (classic choropleth) |
| `dagma:obs_agua_ica` (water quality) | 287 **points** | `ica_ideam` → graduated dot color |
| `pot_2014:nur_edificabilidad_ica` | 14,595 polygons | `id_ica`/`id_icb` class codes |

Design decision: a numeric field drives **height (extrude)** for true height
layers (buildings `id_alturas`, trees `caaltura`) and **color (graduated ramp)**
for everything else. Mode is picked by layer shape, not a global toggle.

## 6. Geometry & 3D

- **All geometry is 2D.** Elevation/height live in *attributes*: `id_alturas`
  (building floors), `caaltura` (tree height m), `cota` (contour elevation m.a.s.l.),
  `rcgaltura` (geodetic). True 3D line-raising isn't native in MapLibre, so contour
  elevation is conveyed by **color** (hypsometric ramp on `cota`), not height.
- Some layers report geometry type **`Unknown (any)`** (mixed/declared-any) — e.g.
  `dagma:cus_acs_psa_zonificacion`, `pot_2014:nur_edificabilidad_ica`. Render by
  filtering on `geometry-type` per sublayer (fill/line/circle) rather than assuming.
- Empty / non-spatial layers exist (0 features or no geometry) and are marked
  `serve: empty` in the manifest.

## 7. Big layers (→ PMTiles)

Tiling rule: **> 2000 features or > 5 MB → PMTiles**, else raw GeoJSON. The heavy
hitters (reprojected GeoJSON on disk):

| Layer | GeoJSON size |
|---|---|
| `catastro:cat_bas_terrenos` (cadastral parcels) | ~1.6 GB |
| `dapm:…_estrato_urbano_expansion` | ~1.15 GB |
| `dagma:cus_vin_censo_arboreo` (382,998 trees) | ~922 MB |
| `seguridad_justicia:ps_os_comparendos` | ~670 MB |

Consequences: never `json.load` these in Python (RAM) — use streaming GDAL. For
choropleth ranges on PMTiles-served layers, the value domain must come from a
streaming scan (or fixed ordinal classes), not a client-side pass.

## 8. DEM / relief

- **Only a *styled grayscale* product is exposed.** WMS `image/png` returns a
  hillshaded grayscale render; **WCS is disabled**, so raw elevation values aren't
  available. Gray value is pseudo-elevation, not true metres.
- **`format=image/geotiff` returns an all-white image** (the relief style isn't
  applied to that format) — must use `image/png`.
- **MapLibre GL JS has no `raster-color`** (that's Mapbox-only), and hue/saturation
  can't tint a grayscale raster. Green relief therefore can't be done client-side.
- Solution: bake it once in the pipeline (`dem_relief` asset) — WMS GetMap →
  `gdaldem color-relief` (green ramp) → re-apply the WMS alpha as a coverage mask →
  one self-hosted RGBA PNG placed with a MapLibre `image` source. Removes the
  runtime WMS dependency. True-metre relief would need the raw elevation GeoTIFF
  (blocked by the disabled WCS).

## 9. Tooling gotchas (so they don't bite twice)

- **GDAL CLI mis-parses negative coordinates** after multi-arg options like
  `-a_ullr` ("Unknown option name '-a_ullr'"). Workaround: assign a **pixel-space**
  north-up geotransform (`-a_ullr 0 H W 0`, positive args only) when you just need
  `gdalbuildvrt -separate` to accept the stack; supply real-world corners elsewhere.
- **`gdalbuildvrt -separate` takes only the first band per input** — split an RGB
  raster into 3 single-band inputs before stacking with an alpha band.
- **Dagster asset modules must NOT use `from __future__ import annotations`** — it
  stringizes the `context` type hint and Dagster rejects it
  ("Cannot annotate `context` parameter…"). Modern `list[…]`/`X | None` generics
  work without it on Python 3.12 anyway.

## 10. Backfill semantics

- The backfill (`scripts/backfill.py`) is **resumable**: it skips any layer whose
  manifest fragment already records a `serve` decision. "Skipped" in the run summary
  means *already complete*, **not** omitted.
- Clean run 2026-05-31: 254 materialized + 102 already-done (skipped) + 1 discarded
  (401) = 357.
