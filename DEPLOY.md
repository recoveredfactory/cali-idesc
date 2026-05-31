# Deploy

The viewer and its baked data are served from the **shared basemap CloudFront**
(`pmtiles.grupovisual.org`, managed by `~/projects/basemap`, SST) under a
**`/cali-idesc`** prefix:

- App  → `https://pmtiles.grupovisual.org/cali-idesc/`
- Data → `https://pmtiles.grupovisual.org/cali-idesc/data/` (`layers.json`, `pmtiles/`, `geojson/`, `dem/`)

Because the app, its layer tiles, and the basemap PMTiles are all the **same
origin**, there are no CORS concerns.

## Prerequisites
- AWS credentials for the basemap account (**647111127395**, region **us-east-1**) —
  the same creds used for `~/projects/basemap` SST deploys.
- `pnpm` deps installed in `viewer/`.
- Baked data present in `pipeline/data/` (`layers.json`, `pmtiles/`, `geojson/`, `dem/`).
  Rebuild with `cd pipeline && uv run python scripts/build_dem.py` and
  `DAGSTER_HOME="$PWD/.dagster" uv run python scripts/build_manifest.py`.

## One-time: clean-URL rewrite
`pmtiles.grupovisual.org/cali-idesc/` needs a directory-index rewrite (the OAI→S3
origin has none). It's a one-line addition to the **viewer-request** CloudFront
Function in `~/projects/basemap/sst.config.ts`:

```js
if (request.uri === "/cali-idesc" || request.uri === "/cali-idesc/") {
  request.uri = "/cali-idesc/index.html";
}
```

Apply with `cd ~/projects/basemap && pnpm run deploy`.

## Deploy
```bash
./deploy.sh
```
It builds the viewer with `BASE_PATH=/cali-idesc` + `VITE_DATA_BASE=/cali-idesc/data`,
syncs the app and the ~7 GB served data subset to S3 with the right content-types,
and invalidates `/cali-idesc/*`. Bucket/distribution are read from
`~/projects/basemap/.sst/outputs.json` (override with `BUCKET=` / `DIST=` env vars).

## Verify
```bash
curl -sI https://pmtiles.grupovisual.org/cali-idesc/                       # 200 text/html
curl -sI https://pmtiles.grupovisual.org/cali-idesc/data/layers.json       # 200 application/json
```
Then open the URL: basemap + relief render, themes switch, feature click → inspector,
layer ⓘ → glossary popup.
