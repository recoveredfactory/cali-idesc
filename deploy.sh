#!/usr/bin/env bash
# Upload the Cali viewer's baked DATA (~7GB) to the shared basemap S3/CloudFront,
# under the /cali-idesc/data prefix. Served from pmtiles.grupovisual.org.
#
#   ./deploy.sh
#
# The FRONTEND is deployed separately — it lives on its own origin
# (cali.recoveredfactory.net) via the sibling SST app ../cali-viewer-deploy.
# See DEPLOY.md. The basemap CloudFront Function already CORS-allows
# *.recoveredfactory.net, so the cross-origin range requests just work.
#
# Requires AWS credentials for the basemap account (647111127395, us-east-1).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA="$ROOT/pipeline/data"
PREFIX="cali-idesc"
export AWS_REGION="${AWS_REGION:-us-east-1}"

# Resolve bucket + distribution from the basemap SST outputs (override via env).
SST_OUTPUTS="${SST_OUTPUTS:-$HOME/projects/basemap/.sst/outputs.json}"
BUCKET="${BUCKET:-}"; DIST="${DIST:-}"
if [[ -f "$SST_OUTPUTS" ]]; then
  BUCKET="${BUCKET:-$(grep -oE 'basemap-prod-pmtilesbucketbucket-[a-z0-9]+' "$SST_OUTPUTS" | head -1)}"
  DIST="${DIST:-$(grep -oE '"[A-Z0-9]{13,14}"' "$SST_OUTPUTS" | tr -d '"' | head -1)}"
fi
BUCKET="${BUCKET:-basemap-prod-pmtilesbucketbucket-zxcemmvo}"
DIST="${DIST:-EIT2ALX4WU5RE}"

echo "Bucket=$BUCKET  Dist=$DIST  Prefix=/$PREFIX/data  Region=$AWS_REGION"
aws sts get-caller-identity >/dev/null || { echo "ERROR: no AWS credentials"; exit 1; }

# Upload the served data subset with correct content-types (raw/ is NOT served).
echo "==> uploading data (~7GB; first run is the slow one)"
DST="s3://$BUCKET/$PREFIX/data"
aws s3 cp "$DATA/layers.json" "$DST/layers.json" \
  --content-type "application/json" --cache-control "no-cache"
aws s3 sync "$DATA/pmtiles/" "$DST/pmtiles/" \
  --content-type "application/octet-stream" --cache-control "public, max-age=86400"
aws s3 sync "$DATA/geojson/" "$DST/geojson/" \
  --content-type "application/json" --cache-control "public, max-age=86400"
# Relief is raster PMTiles (one per theme), range-served like the basemap.
aws s3 sync "$DATA/dem/" "$DST/dem/" --exclude "*" --include "*.pmtiles" \
  --content-type "application/octet-stream" --cache-control "public, max-age=86400"
# dem.json (relief placement + variants) — small metadata, keep it fresh.
aws s3 cp "$DATA/dem/dem.json" "$DST/dem/dem.json" \
  --content-type "application/json" --cache-control "no-cache"

# Invalidate so a refreshed layers.json / data serves immediately.
echo "==> invalidating CloudFront"
aws cloudfront create-invalidation --distribution-id "$DIST" --paths "/$PREFIX/data/*" >/dev/null

echo "Done -> https://pmtiles.grupovisual.org/$PREFIX/data/layers.json"
