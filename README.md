# Cali IDESC geodata

Download every layer from the City of Cali's IDESC GeoServer, fix the exotic
projection, emit **GeoJSON + PMTiles**, and browse it all in a bilingual
(es/en) MapLibre viewer.

**[Live demo →](https://cali.recoveredfactory.net)**  ·  MIT-licensed  ·  a civic, open-source tool by [Recovered Factory](https://recoveredfactory.net)

> Released as open source **for study and reuse**. The geodata itself is **not**
> in this repo — it's large and fully rebuildable; the `pipeline/` regenerates it
> from the public IDESC services. See [CONTRIBUTING](CONTRIBUTING.md) to get involved.

```
cali-idesc/
├── pipeline/   # Dagster (dg / components) — download → reproject → tile → manifest
└── viewer/     # SvelteKit + Paraglide + MapLibre + pmtiles
```

## The data, in one paragraph

The WFS endpoint (`https://ws-idesc.cali.gov.co/geoserver/ows`) publishes **357
feature types across 23 workspaces** (cadastre, the full POT 2014 zoning corpus,
mobility, environment, risk…). Its native CRS is **EPSG:6249** (MAGNA-SIRGAS
Cali urban grid, PROJ `col_urban`); we reproject to WGS84. Two quirks the
pipeline handles: GeoJSON output works even though only GML is *advertised*, and
`startIndex` paging is rejected on the many PK-less SQL-view layers — so we
stream each layer in one request and prove completeness from the server's own
`numberMatched`/`numberReturned`.

## Pipeline (`pipeline/`)

Requires `uv`, GDAL ≥ 3.4 (`ogr2ogr`/`ogrinfo`), and `tippecanoe`.

```bash
cd pipeline
export DAGSTER_HOME="$PWD/.dagster"        # persists the dynamic layer partitions
uv sync
uv run dg dev                              # UI at http://localhost:3000
```

Assets (autoloaded from `src/cali_geo/defs/`):

| asset | partitioned | what it does |
|-------|-------------|--------------|
| `wfs_catalog` | – | parse GetCapabilities → `data/catalog.json`, register 357 `layer` partitions |
| `layer_translations` | – | es→en titles+abstracts via Anthropic, cached (`ANTHROPIC_API_KEY` required) |
| `layer_geojson` | ✓ per layer | stream-download, assert `numberReturned == numberMatched`, reproject 6249→4326 |
| `layer_pmtiles` | ✓ per layer | tile with tippecanoe when large/dense, else keep raw GeoJSON (`serve` recorded) |
| `viewer_manifest` | – | inventory fragments + translations → `dist/layers.json` and `data/layers.json` |

Asset checks on `layer_geojson`: **`layer_complete`** (completeness) and
**`bounds_in_cali`** (reprojection lands in the Cali bbox).

Materialize a few partitions, or backfill all 357:

```bash
uv run dg launch --assets wfs_catalog
uv run dg launch --assets layer_geojson,layer_pmtiles \
  --partition catastro__cat_bas_construcciones        # the 703k-feature stress layer
uv run dg launch --assets viewer_manifest
```

Outputs land under `pipeline/data/` (`geojson/`, `pmtiles/`, `layers.json`).
Tiling rule lives in `defs/config.py` (`> 2000` features **or** `> 5 MB` → PMTiles).

## Viewer (`viewer/`)

Requires **Node ≥ 22.12** and `pnpm`.

```bash
cd viewer
pnpm install
ln -sfn ../../pipeline/data static/data    # serve the pipeline outputs at /data
pnpm dev                                    # http://localhost:5173
```

The viewer fetches `/data/layers.json`, lists every layer grouped by workspace
with a search box, and toggles each on the map — `serve: "pmtiles"` layers load
as vector tiles via the pmtiles protocol (HTTP range requests), `serve:
"geojson"` layers load directly. Each layer has an ⓘ disclosure that shows its
**description in the active language**. UI is Spanish-first with an es/en switch
(Paraglide). The **basemap is the grupovisual Protomaps build**
(`pmtiles://https://pmtiles.grupovisual.org/latest.pmtiles`, light theme via
`@protomaps/basemaps`). Point `VITE_DATA_BASE` at a remote bucket (e.g. the grupovisual
CloudFront) to serve tiles from there instead of the local symlink.
```bash
VITE_DATA_BASE=https://pmtiles.grupovisual.org/cali pnpm build
```

## Status

Proven end-to-end on a subset: a 43-feature point layer (→ GeoJSON) and the
703,538-feature `catastro` building layer (→ 56 MB PMTiles), both green through
Dagster with completeness + bounds checks passing. Remaining: set
`ANTHROPIC_API_KEY` and run `layer_translations`, then backfill the full 357.

## License

The **code** in this repository is licensed under the [MIT License](LICENSE).

The underlying **geodata** is published by **IDESC – Alcaldía de Santiago de
Cali** ([geoportal](https://idesc.cali.gov.co/)); consult IDESC for the terms
that govern the data itself. This project only reprojects and re-packages it.

Contributions are welcome — see [CONTRIBUTING](CONTRIBUTING.md) and the
[Code of Conduct](CODE_OF_CONDUCT.md).
