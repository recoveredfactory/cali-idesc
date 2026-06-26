<sub>**Español** · [English](README.en.md)</sub>

# Geodatos IDESC de Cali

Descarga todas las capas del GeoServer del IDESC de la Alcaldía de Cali, corrige
su proyección poco común, genera **GeoJSON + PMTiles** y explóralo todo en un
visor MapLibre bilingüe (es/en).

**[Demo en vivo →](https://cali.recoveredfactory.net)**  ·  Licencia MIT  ·  una herramienta cívica y de código abierto de [Recovered Factory](https://recoveredfactory.net)

> Publicado como código abierto **para estudio y reutilización**. Los geodatos
> **no** están en este repositorio: son grandes y totalmente reconstruibles; el
> `pipeline/` los regenera desde los servicios públicos del IDESC. Consulta
> [CONTRIBUTING](CONTRIBUTING.md) para participar.

```
cali-idesc/
├── pipeline/   # Dagster (dg / components) — descarga → reproyección → teselado → manifiesto
└── viewer/     # SvelteKit + Paraglide + MapLibre + pmtiles
```

## Los datos, en un párrafo

El servicio WFS (`https://ws-idesc.cali.gov.co/geoserver/ows`) publica **357
tipos de entidades en 23 espacios de trabajo (workspaces)** (catastro, todo el
corpus de zonificación del POT 2014, movilidad, ambiente, riesgo…). Su CRS
nativo es **EPSG:6249** (MAGNA-SIRGAS, malla urbana de Cali, PROJ `col_urban`);
lo reproyectamos a WGS84. El pipeline maneja dos rarezas: la salida en GeoJSON
funciona aunque solo se *anuncie* GML, y la paginación con `startIndex` es
rechazada en las numerosas capas de vista SQL sin clave primaria, así que
transmitimos cada capa en una sola petición y demostramos que está completa con
los propios `numberMatched`/`numberReturned` del servidor.

## Pipeline (`pipeline/`)

Requiere `uv`, GDAL ≥ 3.4 (`ogr2ogr`/`ogrinfo`) y `tippecanoe`.

```bash
cd pipeline
export DAGSTER_HOME="$PWD/.dagster"        # persiste las particiones dinámicas de capas
uv sync
uv run dg dev                              # interfaz en http://localhost:3000
```

Activos (*assets*, autocargados desde `src/cali_geo/defs/`):

| asset | particionado | qué hace |
|-------|--------------|----------|
| `wfs_catalog` | – | parsea GetCapabilities → `data/catalog.json`, registra 357 particiones `layer` |
| `layer_translations` | – | títulos y resúmenes es→en vía Anthropic, en caché (requiere `ANTHROPIC_API_KEY`) |
| `layer_geojson` | ✓ por capa | descarga en *streaming*, verifica `numberReturned == numberMatched`, reproyecta 6249→4326 |
| `layer_pmtiles` | ✓ por capa | tesela con tippecanoe cuando es grande/densa, si no conserva el GeoJSON crudo (registra `serve`) |
| `viewer_manifest` | – | inventaría fragmentos + traducciones → `dist/layers.json` y `data/layers.json` |

Verificaciones (*asset checks*) sobre `layer_geojson`: **`layer_complete`**
(completitud) y **`bounds_in_cali`** (la reproyección cae dentro del bbox de Cali).

Materializa unas pocas particiones, o reconstruye las 357:

```bash
uv run dg launch --assets wfs_catalog
uv run dg launch --assets layer_geojson,layer_pmtiles \
  --partition catastro__cat_bas_construcciones        # la capa de estrés de 703k entidades
uv run dg launch --assets viewer_manifest
```

Las salidas quedan en `pipeline/data/` (`geojson/`, `pmtiles/`, `layers.json`).
La regla de teselado vive en `defs/config.py` (`> 2000` entidades **o** `> 5 MB` → PMTiles).

## Visor (`viewer/`)

Requiere **Node ≥ 22.12** y `pnpm`.

```bash
cd viewer
pnpm install
ln -sfn ../../pipeline/data static/data    # sirve las salidas del pipeline en /data
pnpm dev                                    # http://localhost:5173
```

El visor obtiene `/data/layers.json`, lista cada capa agrupada por *workspace*
con un buscador y las activa/desactiva en el mapa: las capas `serve: "pmtiles"`
se cargan como teselas vectoriales vía el protocolo pmtiles (peticiones de rango
HTTP) y las `serve: "geojson"` se cargan directamente. Cada capa tiene un control
ⓘ que muestra su **descripción en el idioma activo**. La interfaz es primero en
español con un conmutador es/en (Paraglide). El **mapa base es la compilación
Protomaps de grupovisual** (`pmtiles://https://pmtiles.grupovisual.org/latest.pmtiles`,
tema claro vía `@protomaps/basemaps`). Apunta `VITE_DATA_BASE` a un bucket remoto
(p. ej. el CloudFront de grupovisual) para servir las teselas desde allí en lugar
del enlace simbólico local.
```bash
VITE_DATA_BASE=https://pmtiles.grupovisual.org/cali pnpm build
```

## Estado

Probado de extremo a extremo en un subconjunto: una capa de puntos de 43
entidades (→ GeoJSON) y la capa de construcciones de catastro de 703.538
entidades (→ 56 MB en PMTiles), ambas en verde a través de Dagster con las
verificaciones de completitud y límites pasando. Pendiente: definir
`ANTHROPIC_API_KEY` y ejecutar `layer_translations`, luego reconstruir las 357
completas.

## Licencia

El **código** de este repositorio se distribuye bajo la [Licencia MIT](LICENSE).

Los **geodatos** subyacentes los publica el **IDESC – Alcaldía de Santiago de
Cali** ([geoportal](https://idesc.cali.gov.co/)); consulta al IDESC por los
términos que rigen los datos en sí. Este proyecto solo los reproyecta y
reempaqueta.

Las contribuciones son bienvenidas: consulta [CONTRIBUTING](CONTRIBUTING.md) y el
[Código de conducta](CODE_OF_CONDUCT.md).
