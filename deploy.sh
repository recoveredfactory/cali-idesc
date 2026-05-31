#!/usr/bin/env bash
# Deploy the Cali viewer + its baked data to the shared basemap S3/CloudFront,
# under the /cali-idesc prefix — same origin as pmtiles.grupovisual.org, so the
# app, its layer tiles, and the basemap PMTiles are all one origin (no CORS).
#
#   ./deploy.sh
#
# Requires AWS credentials with access to the basemap bucket + distribution
# (same account/region as ~/projects/basemap: acct 647111127395, us-east-1).
# The clean URL (pmtiles.grupovisual.org/cali-idesc/) also needs the one-line
# CloudFront rewrite in ~/projects/basemap/sst.config.ts to be deployed.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VIEWER="$ROOT/viewer"
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

echo "Bucket=$BUCKET  Dist=$DIST  Prefix=/$PREFIX  Region=$AWS_REGION"
aws sts get-caller-identity >/dev/null || { echo "ERROR: no AWS credentials"; exit 1; }

# 1. Build the viewer under the subpath, pointing data at /cali-idesc/data.
#    The dev symlink viewer/static/data -> ../../pipeline/data must NOT be baked
#    into the static build (adapter-static dereferences it and copies ~14GB).
#    Move it aside for the build, then restore it.
echo "==> building viewer"
# Move the dev symlink (viewer/static/data -> ../../pipeline/data) OUT of static/
# during the build: adapter-static would otherwise dereference it and copy ~14GB
# into build/. (Tailwind is already scoped to src/ so it won't scan it either.)
DATA_LINK="$VIEWER/static/data"
DATA_BAK="$VIEWER/.data-symlink.deploybak" # outside static/
restore_link() { [[ -e "$DATA_BAK" ]] && mv "$DATA_BAK" "$DATA_LINK"; }
trap restore_link EXIT
[[ -L "$DATA_LINK" ]] && mv "$DATA_LINK" "$DATA_BAK"
( cd "$VIEWER" && BASE_PATH="/$PREFIX" VITE_DATA_BASE="/$PREFIX/data" pnpm build )
restore_link; trap - EXIT

# 2. Upload the app. Hashed _app/ assets cache forever; index.html must revalidate.
echo "==> uploading app"
aws s3 sync "$VIEWER/build/" "s3://$BUCKET/$PREFIX/" \
  --delete --exclude "data/*" \
  --cache-control "public, max-age=31536000, immutable"
aws s3 cp "$VIEWER/build/index.html" "s3://$BUCKET/$PREFIX/index.html" \
  --content-type "text/html" --cache-control "no-cache"

# 3. Upload the served data subset with correct content-types (raw/ is NOT served).
echo "==> uploading data (~7GB; first run is the slow one)"
DST="s3://$BUCKET/$PREFIX/data"
aws s3 cp "$DATA/layers.json" "$DST/layers.json" \
  --content-type "application/json" --cache-control "no-cache"
aws s3 sync "$DATA/pmtiles/" "$DST/pmtiles/" \
  --content-type "application/octet-stream" --cache-control "public, max-age=86400"
aws s3 sync "$DATA/geojson/" "$DST/geojson/" \
  --content-type "application/json" --cache-control "public, max-age=86400"
aws s3 sync "$DATA/dem/" "$DST/dem/" --exclude "*" --include "*.png" \
  --content-type "image/png" --cache-control "public, max-age=86400"

# 4. Invalidate so the new app + layers.json serve immediately.
echo "==> invalidating CloudFront"
aws cloudfront create-invalidation --distribution-id "$DIST" --paths "/$PREFIX/*" >/dev/null

echo "Done -> https://pmtiles.grupovisual.org/$PREFIX/"
