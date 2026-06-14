"""Per-layer download/reproject/tile assets plus the viewer manifest.

``layer_geojson`` and ``layer_pmtiles`` are partitioned by the dynamic ``layer``
set seeded by ``wfs_catalog``. Each writes a small JSON *fragment* under
``data/manifest/`` describing what it produced; the unpartitioned
``viewer_manifest`` simply inventories those fragments (plus translations) into
``dist/layers.json`` — so it stays decoupled from the partition IO.
"""

import json

import dagster as dg
from dagster import AssetExecutionContext

from .catalog import wfs_catalog
from .config import (
    CALI_BBOX,
    PMTILES_BYTES_THRESHOLD,
    PMTILES_FEATURE_THRESHOLD,
    Paths,
    SOURCE_EPSG,
    typename,
)
from .dem import dem_relief
from .partitions import layer_partitions
from .resources import WfsResource
from .shell import ShellError, convert, ogrinfo_summary, reproject, to_pmtiles
from .translations import layer_translations

_RETRY = dg.RetryPolicy(max_retries=3, delay=5.0, backoff=dg.Backoff.EXPONENTIAL)


def _load_catalog_record(key: str) -> dict:
    records = json.loads(Paths.catalog.read_text(encoding="utf-8"))
    for r in records:
        if r["key"] == key:
            return r
    raise KeyError(f"{key!r} not found in catalog.json; materialize wfs_catalog first")


def _bounds_ok(bbox: list[float] | None) -> bool:
    """True if the (lon/lat) bbox sits inside the Cali bbox, or is empty."""
    if not bbox:
        return True  # empty / non-spatial layer — nothing to verify
    min_lon, min_lat, max_lon, max_lat = bbox
    cmin_lon, cmin_lat, cmax_lon, cmax_lat = CALI_BBOX
    return (
        cmin_lon <= min_lon <= cmax_lon
        and cmin_lon <= max_lon <= cmax_lon
        and cmin_lat <= min_lat <= cmax_lat
        and cmin_lat <= max_lat <= cmax_lat
    )


def _write_fragment(key: str, data: dict) -> None:
    Paths.fragments.mkdir(parents=True, exist_ok=True)
    path = Paths.fragments / f"{key}.json"
    existing = {}
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
    existing.update(data)
    path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")


@dg.asset(
    deps=[wfs_catalog],  # reads catalog.json + the dynamic partitions wfs_catalog seeds
    partitions_def=layer_partitions,
    group_name="layers",
    retry_policy=_RETRY,
    description="Download one layer fully, verify completeness, reproject 6249->4326.",
    check_specs=[
        dg.AssetCheckSpec(
            name="layer_complete",
            asset="layer_geojson",
            description="server numberReturned == numberMatched",
        ),
        dg.AssetCheckSpec(
            name="bounds_in_cali",
            asset="layer_geojson",
            description="reprojected bounds fall within the Cali bbox",
        ),
    ],
)
def layer_geojson(context: AssetExecutionContext, wfs: WfsResource):
    key = context.partition_key
    record = _load_catalog_record(key)
    tn = typename(key)

    Paths.ensure()
    raw = Paths.raw / f"{key}.fc.json"
    out = Paths.geojson / f"{key}.geojson"

    result = wfs.download_geojson(tn, raw)
    # Hard completeness guarantee — the known failure mode for this server.
    if not result.complete:
        raise dg.Failure(
            description=(
                f"Incomplete download for {tn}: server returned "
                f"{result.number_returned} of {result.number_matched} features."
            )
        )

    crs = record.get("default_crs", "")
    reprojected = crs.endswith("6249")

    if result.number_returned == 0:
        out.unlink(missing_ok=True)
        summary = {"feature_count": 0, "geometry_type": None, "bbox": None}
    else:
        try:
            if reprojected:
                reproject(raw, out, source_epsg=SOURCE_EPSG)
            else:
                # Unknown/non-6249 native CRS: rely on the declared CRS.
                convert(raw, out)
            summary = ogrinfo_summary(out)
        except ShellError as exc:
            # Non-spatial or unreprojectable geometry — keep going, mark empty.
            context.log.warning(f"{tn}: could not reproject ({exc}); marking non-spatial")
            out.unlink(missing_ok=True)
            summary = {"feature_count": 0, "geometry_type": None, "bbox": None}

    computed_bbox = summary["bbox"]
    geojson_bytes = out.stat().st_size if out.exists() else 0
    fragment = {
        "key": key,
        "typename": tn,
        "workspace": record["workspace"],
        "layer": record["layer"],
        "title_es": record.get("title_es", ""),
        "abstract_es": record.get("abstract_es", ""),
        "geometry_type": summary["geometry_type"],
        "feature_count": result.number_returned,
        "number_matched": result.number_matched,
        "geojson_bytes": geojson_bytes,
        "reprojected": reprojected,
        "bbox": computed_bbox or record.get("bbox"),
        "computed_bbox": computed_bbox,
        "fields": summary.get("fields", []),
        "numeric_fields": summary.get("numeric_fields", []),
    }
    _write_fragment(key, fragment)

    yield dg.Output(
        fragment,
        metadata={
            "feature_count": result.number_returned,
            "number_matched": result.number_matched,
            "geometry_type": summary["geometry_type"] or "none",
            "reprojected": reprojected,
            "geojson_mb": round(geojson_bytes / 1_048_576, 3),
            "computed_bbox": dg.MetadataValue.json(computed_bbox),
            "geojson_path": dg.MetadataValue.path(str(out)),
        },
    )
    yield dg.AssetCheckResult(
        check_name="layer_complete",
        passed=result.complete,
        metadata={
            "number_matched": result.number_matched,
            "number_returned": result.number_returned,
        },
    )
    yield dg.AssetCheckResult(
        check_name="bounds_in_cali",
        passed=_bounds_ok(computed_bbox),
        metadata={"computed_bbox": dg.MetadataValue.json(computed_bbox)},
    )


@dg.asset(
    partitions_def=layer_partitions,
    group_name="layers",
    description="Decide geojson-vs-pmtiles by size; tile large/dense layers.",
)
def layer_pmtiles(context: AssetExecutionContext, layer_geojson: dict) -> dict:
    key = context.partition_key
    frag = layer_geojson
    fc = frag["feature_count"]
    nbytes = frag["geojson_bytes"]

    if fc == 0 or frag["geometry_type"] is None:
        serve, url, pmtiles_bytes = "empty", None, 0
    elif fc > PMTILES_FEATURE_THRESHOLD or nbytes > PMTILES_BYTES_THRESHOLD:
        dst = Paths.pmtiles / f"{key}.pmtiles"
        fields = frag.get("fields") or []
        extra: list[str] | None = None
        densest = "drop"
        # Buildings (a layer carrying floor counts) thin too fast zoomed out, and
        # the dropped ones should be the SHORT buildings so landmarks persist.
        # Order tallest-first (densest-as-needed then keeps them) and give each
        # tile a bigger byte budget so it thins less aggressively.
        if "npisos" in fields:
            extra = ["--order-descending-by=npisos", "--maximum-tile-bytes=1000000"]
        else:
            # Strata is a dense per-property choropleth (~700k predios). Dropping
            # the densest features leaves holes across whole neighbourhoods when
            # zoomed out. Instead COALESCE the densest features into neighbours so
            # the choropleth stays continuous; ordering by the stratum makes the
            # merges join same-value lots (clean blocks at city scale), and a
            # bigger tile budget keeps more individual lots before merging. Full
            # per-lot detail returns at high zoom.
            stratum = next((f for f in ("estestrato", "erestrato") if f in fields), None)
            if stratum:
                densest = "coalesce"
                extra = [f"--order-by={stratum}", "--maximum-tile-bytes=2500000"]
        to_pmtiles(
            Paths.geojson / f"{key}.geojson",
            dst,
            layer=key,
            extra_args=extra,
            densest=densest,
        )
        serve = "pmtiles"
        url = f"pmtiles/{key}.pmtiles"
        pmtiles_bytes = dst.stat().st_size
    else:
        serve = "geojson"
        url = f"geojson/{key}.geojson"
        pmtiles_bytes = 0

    decision = {
        "serve": serve,
        "url": url,
        "pmtiles_bytes": pmtiles_bytes,
        "tile_thresholds": {
            "feature": PMTILES_FEATURE_THRESHOLD,
            "bytes": PMTILES_BYTES_THRESHOLD,
        },
    }
    _write_fragment(key, decision)

    context.add_output_metadata(
        {
            "serve": serve,
            "feature_count": fc,
            "geojson_mb": round(nbytes / 1_048_576, 3),
            "pmtiles_mb": round(pmtiles_bytes / 1_048_576, 3),
        }
    )
    return decision


def _heal_fields(frag: dict) -> bool:
    """Backfill `fields`/`numeric_fields` onto a fragment that predates them by
    reading the layer's on-disk GeoJSON via ogrinfo. Returns True if it mutated
    the fragment (so the caller can persist the cache). Fragments written by the
    current `layer_geojson` already carry both keys, so this is a no-op for them;
    it only fires for older fragments — which is why `scripts/patch_fields.py` is
    no longer needed.
    """
    if "fields" in frag and "numeric_fields" in frag:
        return False
    geo = Paths.geojson / f"{frag['key']}.geojson"
    summary = ogrinfo_summary(geo) if geo.exists() else {}
    frag.setdefault("fields", summary.get("fields", []))
    frag.setdefault("numeric_fields", summary.get("numeric_fields", []))
    return True


@dg.asset(
    deps=[layer_pmtiles, dem_relief, layer_translations],  # reads translations.json
    group_name="manifest",
    description="Inventory per-layer fragments + translations into dist/layers.json.",
)
def viewer_manifest(context: AssetExecutionContext) -> dg.MaterializeResult:
    Paths.ensure()
    translations = {}
    if Paths.translations.exists():
        translations = json.loads(Paths.translations.read_text(encoding="utf-8"))

    layers = []
    healed = 0
    for path in sorted(Paths.fragments.glob("*.json")):
        frag = json.loads(path.read_text(encoding="utf-8"))
        if _heal_fields(frag):
            path.write_text(
                json.dumps(frag, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            healed += 1
        tr = translations.get(frag["key"], {})
        layers.append(
            {
                "key": frag["key"],
                "typename": frag.get("typename"),
                "workspace": frag.get("workspace"),
                "title_es": frag.get("title_es", ""),
                "title_en": tr.get("title_en", ""),
                "abstract_es": frag.get("abstract_es", ""),
                "abstract_en": tr.get("abstract_en", ""),
                "geometry_type": frag.get("geometry_type"),
                "feature_count": frag.get("feature_count", 0),
                "serve": frag.get("serve", "empty"),
                "url": frag.get("url"),
                "bbox": frag.get("bbox"),
                "fields": frag.get("fields", []),
                "numeric_fields": frag.get("numeric_fields", []),
                "field_ranges": frag.get("field_ranges", {}),
                "field_categories": frag.get("field_categories", {}),
            }
        )

    manifest = {
        "generated_layers": len(layers),
        "workspaces": sorted({lyr["workspace"] for lyr in layers if lyr["workspace"]}),
        "layers": layers,
    }
    # Self-hosted green DEM relief (built by the `dem_relief` asset). When absent,
    # the viewer falls back to the live IDESC WMS.
    if Paths.dem_meta.exists():
        manifest["dem"] = json.loads(Paths.dem_meta.read_text(encoding="utf-8"))
    payload = json.dumps(manifest, ensure_ascii=False, indent=2)
    Paths.manifest.write_text(payload, encoding="utf-8")  # published artifact
    Paths.manifest_served.write_text(payload, encoding="utf-8")  # served with data/

    serve_counts: dict[str, int] = {}
    for lyr in layers:
        serve_counts[lyr["serve"]] = serve_counts.get(lyr["serve"], 0) + 1
    return dg.MaterializeResult(
        metadata={
            "generated_layers": len(layers),
            "fragments_healed": healed,
            "serve_breakdown": dg.MetadataValue.json(serve_counts),
            "manifest_path": dg.MetadataValue.path(str(Paths.manifest)),
        }
    )
