# Deploy

Two origins, deployed separately:

| Piece | Lives at | Owned by |
|-------|----------|----------|
| **Frontend** (SvelteKit/MapLibre viewer) | `https://cali.recoveredfactory.net/` (alias `https://lo-demas-es-loma.recoveredfactory.net/`) | `~/projects/cali-viewer-deploy` (SST: S3 + CloudFront + ACM + Route 53) |
| **Data** (`layers.json`, `pmtiles/`, `geojson/`, `dem/`) | `https://pmtiles.grupovisual.org/cali-idesc/data/` | the shared **basemap** bucket (`~/projects/basemap`); uploaded by `./deploy.sh` here |

The viewer is a pure client-side SPA. Its data is a **different origin** (the
basemap CloudFront), baked in at build time via `VITE_DATA_BASE`. That basemap
distribution's CloudFront Function already CORS-allows `*.recoveredfactory.net`,
so the cross-origin PMTiles byte-range + GeoJSON requests work without changes.

## Prerequisites
- AWS credentials for account **647111127395**, region **us-east-1** (same creds
  as `~/projects/basemap`; `recoveredfactory.net` is a Route 53 zone in this account).
- `pnpm` deps installed in `viewer/` (frontend) and in `../cali-viewer-deploy/` (SST).
- Baked data present in `pipeline/data/` (`layers.json`, `pmtiles/`, `geojson/`, `dem/`).

## Deploy the data → pmtiles.grupovisual.org/cali-idesc/data
```bash
./deploy.sh
```
Syncs the ~7 GB served subset (pmtiles, geojson, dem, layers.json) to the basemap
bucket with correct content-types, and invalidates `/cali-idesc/data/*`.
Bucket/distribution are read from `~/projects/basemap/.sst/outputs.json` (override
with `BUCKET=` / `DIST=`). Run this whenever the baked data changes.

## Deploy the frontend → cali.recoveredfactory.net
```bash
cd ../cali-viewer-deploy && pnpm run deploy
```
`build-viewer.sh` builds `viewer/` for the domain root with the remote data origin
baked in (`BASE_PATH=""`, `VITE_DATA_BASE=https://pmtiles.grupovisual.org/cali-idesc/data`),
moving the `static/data` dev symlink aside so adapter-static doesn't dereference
the 6.6 GB tree. Then `sst deploy --stage=production` mirrors `viewer/build/` to S3
and invalidates CloudFront. First deploy provisions the cert + the two Route 53
alias records and waits on DNS validation (~2 min).

> **Build OOM, solved:** the prod build once ballooned to ~6.5 GB and OOM-killed —
> Tailwind v4 auto content-detection was following `static/data` (→ 6.6 GB geojson)
> and parsing it for class names. Fixed by scoping Tailwind to `src/` in
> `viewer/src/routes/layout.css` (`@import 'tailwindcss' source(none); @source "..";`).
> Build now runs ~330 MB / ~5 s. `build-viewer.sh` also moves the symlink aside as
> belt-and-braces (adapter-static would otherwise copy ~14 GB into `build/`).

## Verify
```bash
curl -sI https://cali.recoveredfactory.net/                                  # 200 text/html
curl -sI https://pmtiles.grupovisual.org/cali-idesc/data/layers.json         # 200 application/json
# CORS preflight from the frontend origin returns the allow-origin header:
curl -sI -H 'Origin: https://cali.recoveredfactory.net' \
  https://pmtiles.grupovisual.org/cali-idesc/data/layers.json | grep -i access-control
```
Then open the URL: basemap + relief render, themes switch, feature click →
inspector, layer ⓘ → glossary popup. A PMTiles range probe returns `206`.
