import maplibregl from 'maplibre-gl';
import { Protocol } from 'pmtiles';
import { layers as protomapsLayers, namedFlavor } from '@protomaps/basemaps';
import {
	DATA_BASE,
	CALI_CENTER,
	CALI_ZOOM,
	HEIGHT_FIELDS,
	METERS_PER_FLOOR,
	ELEVATION_FIELD,
	ELEVATION_RAMP,
	GRADUATED_RAMP,
	CATEGORICAL_PALETTE,
	CATEGORICAL_FALLBACK,
	WMS_BASE,
	DEM_LAYER,
	type Layer,
	type DemRelief
} from './config';

let protocolRegistered = false;

// Basemap = the grupovisual Protomaps planet build (single PMTiles, range-served).
const BASEMAP_PMTILES = 'pmtiles://https://pmtiles.grupovisual.org/latest.pmtiles';

function basemapStyle(): maplibregl.StyleSpecification {
	return {
		version: 8,
		glyphs: 'https://protomaps.github.io/basemaps-assets/fonts/{fontstack}/{range}.pbf',
		sprite: 'https://protomaps.github.io/basemaps-assets/sprites/v4/light',
		sources: {
			protomaps: {
				type: 'vector',
				url: BASEMAP_PMTILES,
				attribution:
					'<a href="https://protomaps.com">Protomaps</a> © <a href="https://openstreetmap.org">OpenStreetMap</a>'
			}
		},
		layers: protomapsLayers('protomaps', namedFlavor('light'), { lang: 'es' })
	};
}

export function createMap(container: HTMLElement): maplibregl.Map {
	if (!protocolRegistered) {
		maplibregl.addProtocol('pmtiles', new Protocol().tile);
		protocolRegistered = true;
	}
	const map = new maplibregl.Map({
		container,
		style: basemapStyle(),
		center: CALI_CENTER,
		zoom: CALI_ZOOM,
		attributionControl: { compact: true }
	});
	map.on('error', (e) => console.error('maplibre error:', (e as { error?: Error })?.error?.message ?? e));
	return map;
}

/** Stable, pleasant color per workspace (HSL hue from a string hash). */
export function workspaceColor(workspace: string): string {
	let h = 0;
	for (let i = 0; i < workspace.length; i++) h = (h * 31 + workspace.charCodeAt(i)) % 360;
	return `hsl(${h}, 70%, 45%)`;
}

const srcId = (key: string) => `src:${key}`;
const lyrId = (key: string, suffix: string) => `lyr:${key}:${suffix}`;

/** Per-layer render state: 3D extrusion (whether, by which numeric field, and
 *  the global vertical-exaggeration multiplier), plus the optional field that
 *  drives data-driven coloring (`colorField`; null = flat workspace color). */
export type ExtrudeOpts = {
	extrude?: boolean;
	field?: string | null;
	exaggeration?: number;
	colorField?: string | null;
};

/** Numeric attributes a layer can extrude / scale by — the field-picker menu.
 *  Falls back to the legacy known-height fields when the pipeline hasn't yet
 *  recorded `numeric_fields` for this layer. */
export function extrudableFields(layer: Layer): string[] {
	if (layer.numeric_fields?.length) return layer.numeric_fields;
	return (layer.fields ?? []).filter((f) => f in HEIGHT_FIELDS);
}

/** Default field to drive extrusion: a recognized height field if present,
 *  otherwise the first available numeric field. */
export function defaultExtrudeField(layer: Layer): string | null {
	const numeric = extrudableFields(layer);
	return numeric.find((f) => f in HEIGHT_FIELDS) ?? numeric[0] ?? null;
}

/** How to read a field as a height: known floor-counts get multiplied to meters;
 *  everything else is treated as a raw metric value. */
function modeFor(field: string): 'floors' | 'meters' {
	return HEIGHT_FIELDS[field] ?? 'meters';
}

/** Height-in-meters expression for `field`, scaled by vertical exaggeration. */
function heightExpr(field: string, exaggeration = 1) {
	const meters = ['coalesce', ['to-number', ['get', field]], 0];
	const raw = modeFor(field) === 'floors' ? ['*', meters, METERS_PER_FLOOR] : meters;
	return exaggeration === 1 ? raw : ['*', raw, exaggeration];
}

function elevationColor() {
	return [
		'interpolate',
		['linear'],
		['coalesce', ['to-number', ['get', ELEVATION_FIELD]], ELEVATION_RAMP[0][0]],
		...ELEVATION_RAMP.flat()
	];
}

const circleRadiusExpr = (field: string, exaggeration: number) =>
	[
		'interpolate',
		['linear'],
		heightExpr(field, exaggeration),
		0,
		3,
		25,
		14
	] as unknown as number;

// --- Data-driven coloring ("color by field") --------------------------------

/** The fields a layer can be colored by, split by kind. Numeric fields drive a
 *  graduated ramp (from `field_ranges`); categorical fields a palette match
 *  (from `field_categories`). */
export function colorableFields(layer: Layer): { numeric: string[]; categorical: string[] } {
	return {
		numeric: Object.keys(layer.field_ranges ?? {}),
		categorical: Object.keys(layer.field_categories ?? {})
	};
}

export function hasColorableFields(layer: Layer): boolean {
	const { numeric, categorical } = colorableFields(layer);
	return numeric.length > 0 || categorical.length > 0;
}

/** A MapLibre color expression that paints features by `field`'s value:
 *  numeric → graduated interpolate across the field's [min,max]; categorical →
 *  match each known value to a palette color. Returns null when the field has no
 *  usable stats or a degenerate range — caller falls back to the flat color. */
export function colorByExpr(layer: Layer, field: string): unknown | null {
	const range = layer.field_ranges?.[field];
	if (range) {
		const [min, max] = range;
		if (!(max > min)) return null; // single value → nothing to graduate
		const stops = GRADUATED_RAMP.flatMap(([t, c]) => [min + t * (max - min), c]);
		return ['interpolate', ['linear'], ['to-number', ['get', field], min], ...stops];
	}
	const cats = layer.field_categories?.[field];
	if (cats?.length) {
		const pairs = cats.flatMap((v, i) => [v, CATEGORICAL_PALETTE[i % CATEGORICAL_PALETTE.length]]);
		return ['match', ['to-string', ['get', field]], ...pairs, CATEGORICAL_FALLBACK];
	}
	return null;
}

/** Live-recolor an already-added layer by `field` (or revert to the flat
 *  workspace color when `field` is null) without re-adding it. Sets fill/circle
 *  and the line outline; reverting restores the elevation line color on contour
 *  layers. */
export function setLayerColor(map: maplibregl.Map, layer: Layer, field: string | null): void {
	const expr = field ? colorByExpr(layer, field) : null;
	const base = workspaceColor(layer.workspace);
	const hasElevation = (layer.fields ?? []).includes(ELEVATION_FIELD);
	const fill = lyrId(layer.key, 'fill');
	const line = lyrId(layer.key, 'line');
	const circle = lyrId(layer.key, 'circle');
	if (map.getLayer(fill)) {
		const prop = map.getLayer(fill)!.type === 'fill-extrusion' ? 'fill-extrusion-color' : 'fill-color';
		map.setPaintProperty(fill, prop, (expr ?? base) as never);
	}
	if (map.getLayer(circle)) map.setPaintProperty(circle, 'circle-color', (expr ?? base) as never);
	if (map.getLayer(line)) {
		map.setPaintProperty(line, 'line-color', (expr ?? (hasElevation ? elevationColor() : base)) as never);
	}
}

/** Numeric histogram or category breakdown for a colored layer, computed from
 *  the features currently loaded in the source. For pmtiles layers that's only
 *  the loaded tiles, so `total` is a sample — surface that to the user. */
export type FieldStats =
	| { kind: 'numeric'; field: string; min: number; max: number; bins: number[]; total: number }
	| { kind: 'categorical'; field: string; items: { value: string; color: string; count: number }[]; total: number }
	| null;

const BINS = 24;

export function computeFieldStats(map: maplibregl.Map, layer: Layer, field: string): FieldStats {
	const params = layer.serve === 'pmtiles' ? { sourceLayer: layer.key } : {};
	let feats: ReturnType<maplibregl.Map['querySourceFeatures']> = [];
	try {
		feats = map.querySourceFeatures(srcId(layer.key), params);
	} catch {
		return null;
	}
	const range = layer.field_ranges?.[field];
	if (range) {
		const [min, max] = range;
		const span = max - min || 1;
		const bins = new Array(BINS).fill(0);
		let total = 0;
		for (const f of feats) {
			const raw = f.properties?.[field];
			const v = typeof raw === 'number' ? raw : parseFloat(String(raw).replace(',', '.'));
			if (!Number.isFinite(v)) continue;
			let b = Math.floor(((v - min) / span) * BINS);
			if (b < 0) b = 0;
			if (b >= BINS) b = BINS - 1;
			bins[b]++;
			total++;
		}
		return { kind: 'numeric', field, min, max, bins, total };
	}
	const cats = layer.field_categories?.[field];
	if (cats?.length) {
		const counts = new Map<string, number>();
		let total = 0;
		for (const f of feats) {
			const raw = f.properties?.[field];
			if (raw == null) continue;
			const v = String(raw);
			counts.set(v, (counts.get(v) ?? 0) + 1);
			total++;
		}
		const items = cats.map((value, i) => ({
			value,
			color: CATEGORICAL_PALETTE[i % CATEGORICAL_PALETTE.length],
			count: counts.get(value) ?? 0
		}));
		return { kind: 'categorical', field, items, total };
	}
	return null;
}

/** Add a layer's source + render layers. A layer extrudes (polygons) / scales
 *  (points) only when `opts.extrude` is set with a chosen `field` — this is now
 *  per-layer, not a global mode. Contour lines always color by `cota` elevation
 *  (lines can't be raised in true 3D in MapLibre). */
export function addLayer(map: maplibregl.Map, layer: Layer, opts: ExtrudeOpts = {}): void {
	if (!layer.url || map.getSource(srcId(layer.key))) return;
	const url = `${DATA_BASE}/${layer.url}`;
	const color = workspaceColor(layer.workspace);

	if (layer.serve === 'pmtiles') {
		map.addSource(srcId(layer.key), { type: 'vector', url: `pmtiles://${url}` });
	} else {
		map.addSource(srcId(layer.key), { type: 'geojson', data: url });
	}
	// source-layer only applies to the vector (pmtiles) source; tippecanoe named it `key`.
	const sourceLayer = layer.serve === 'pmtiles' ? { 'source-layer': layer.key } : {};
	const hasElevation = (layer.fields ?? []).includes(ELEVATION_FIELD);
	const exaggeration = opts.exaggeration ?? 1;
	const extrudeField = opts.extrude ? opts.field || defaultExtrudeField(layer) : null;
	// Data-driven color expression (null = flat workspace color). Applied to
	// fill/circle and the line outline so it survives extrude-driven re-adds.
	const colorExpr = opts.colorField ? colorByExpr(layer, opts.colorField) : null;
	const fillColor = (colorExpr ?? color) as never;

	// Polygons: flat fill, or extruded when this layer is in 3D with a chosen field.
	if (extrudeField) {
		map.addLayer({
			id: lyrId(layer.key, 'fill'),
			type: 'fill-extrusion',
			source: srcId(layer.key),
			...sourceLayer,
			filter: ['==', ['geometry-type'], 'Polygon'],
			paint: {
				'fill-extrusion-color': fillColor,
				'fill-extrusion-opacity': 0.85,
				'fill-extrusion-base': 0,
				'fill-extrusion-height': heightExpr(extrudeField, exaggeration) as unknown as number
			}
		});
	} else {
		map.addLayer({
			id: lyrId(layer.key, 'fill'),
			type: 'fill',
			source: srcId(layer.key),
			...sourceLayer,
			filter: ['==', ['geometry-type'], 'Polygon'],
			paint: { 'fill-color': fillColor, 'fill-opacity': 0.35 }
		});
	}

	// Lines (and polygon outlines): color by elevation whenever `cota` exists.
	map.addLayer({
		id: lyrId(layer.key, 'line'),
		type: 'line',
		source: srcId(layer.key),
		...sourceLayer,
		filter: ['in', ['geometry-type'], ['literal', ['LineString', 'Polygon']]],
		paint: colorExpr
			? { 'line-color': colorExpr as unknown as string, 'line-width': 1.4 }
			: hasElevation
				? { 'line-color': elevationColor() as unknown as string, 'line-width': 1.3 }
				: { 'line-color': color, 'line-width': 1.4 }
	});

	// Points: fixed dots, or value-scaled when this layer is in 3D with a chosen field.
	map.addLayer({
		id: lyrId(layer.key, 'circle'),
		type: 'circle',
		source: srcId(layer.key),
		...sourceLayer,
		filter: ['==', ['geometry-type'], 'Point'],
		paint: {
			'circle-radius': extrudeField ? circleRadiusExpr(extrudeField, exaggeration) : 4,
			'circle-color': fillColor,
			'circle-stroke-color': '#fff',
			'circle-stroke-width': 1
		}
	});
}

/** Live-update an already-extruded layer's height to a new exaggeration (and/or
 *  field) without removing it — used by the global exaggeration slider. No-op if
 *  the layer isn't currently extruded (its fill is a flat `fill`, not
 *  `fill-extrusion`). */
export function restyleExtrusion(
	map: maplibregl.Map,
	layer: Layer,
	field: string | null,
	exaggeration: number
): void {
	const f = field || defaultExtrudeField(layer);
	if (!f) return;
	const fill = lyrId(layer.key, 'fill');
	if (map.getLayer(fill) && map.getLayer(fill)!.type === 'fill-extrusion') {
		map.setPaintProperty(fill, 'fill-extrusion-height', heightExpr(f, exaggeration) as unknown as number);
	}
	const circle = lyrId(layer.key, 'circle');
	if (map.getLayer(circle)) {
		map.setPaintProperty(circle, 'circle-radius', circleRadiusExpr(f, exaggeration));
	}
}

export function removeLayer(map: maplibregl.Map, key: string): void {
	for (const suffix of ['fill', 'line', 'circle']) {
		if (map.getLayer(lyrId(key, suffix))) map.removeLayer(lyrId(key, suffix));
	}
	if (map.getSource(srcId(key))) map.removeSource(srcId(key));
}

export function fitToLayer(map: maplibregl.Map, layer: Layer): void {
	if (!layer.bbox) return;
	const [minLon, minLat, maxLon, maxLat] = layer.bbox;
	map.fitBounds(
		[
			[minLon, minLat],
			[maxLon, maxLat]
		],
		{ padding: 60, maxZoom: 16, duration: 600 }
	);
}

// --- feature inspection ------------------------------------------------------

const HIGHLIGHT_SRC = '__highlight';
const HIGHLIGHT_LAYERS = ['__hl-fill', '__hl-line', '__hl-circle'];

/** Ensure the highlight source + layers exist (idempotent). */
export function ensureHighlight(map: maplibregl.Map): void {
	if (map.getSource(HIGHLIGHT_SRC)) return;
	map.addSource(HIGHLIGHT_SRC, {
		type: 'geojson',
		data: { type: 'FeatureCollection', features: [] }
	});
	map.addLayer({
		id: '__hl-fill',
		type: 'fill',
		source: HIGHLIGHT_SRC,
		filter: ['==', ['geometry-type'], 'Polygon'],
		paint: { 'fill-color': '#f59e0b', 'fill-opacity': 0.25 }
	});
	map.addLayer({
		id: '__hl-line',
		type: 'line',
		source: HIGHLIGHT_SRC,
		paint: { 'line-color': '#d97706', 'line-width': 3 }
	});
	map.addLayer({
		id: '__hl-circle',
		type: 'circle',
		source: HIGHLIGHT_SRC,
		filter: ['==', ['geometry-type'], 'Point'],
		paint: {
			'circle-radius': 8,
			'circle-color': '#f59e0b',
			'circle-opacity': 0.4,
			'circle-stroke-color': '#d97706',
			'circle-stroke-width': 2.5
		}
	});
}

/** Highlight a single feature's geometry, or clear when feature is null. */
export function setHighlight(map: maplibregl.Map, feature: GeoJSON.Feature | null): void {
	ensureHighlight(map);
	const src = map.getSource(HIGHLIGHT_SRC) as maplibregl.GeoJSONSource;
	src.setData({
		type: 'FeatureCollection',
		features: feature?.geometry
			? [{ type: 'Feature', geometry: feature.geometry, properties: {} }]
			: []
	});
	// Keep the highlight above any data layers added after it.
	for (const id of HIGHLIGHT_LAYERS) if (map.getLayer(id)) map.moveLayer(id);
}

/** Ids of our data layers currently on the map (only enabled layers are added). */
export function inspectableLayerIds(map: maplibregl.Map): string[] {
	return (map.getStyle().layers ?? [])
		.map((l) => l.id)
		.filter((id) => id.startsWith('lyr:'));
}

// --- DEM overlay (WMS raster) ------------------------------------------------

const DEM_SRC = '__dem-src';
const DEM_LYR = '__dem';

/** Resolve a relief variant's served URL: the requested id, else the default. */
function demVariantUrl(dem: DemRelief, variantId?: string): string | undefined {
	const v = dem.variants.find((x) => x.id === variantId) ?? dem.variants.find((x) => x.id === dem.default);
	return (v ?? dem.variants[0])?.url;
}

/** Swap the relief image in place (no remove/re-add) when the selector changes. */
export function setDemVariant(map: maplibregl.Map, dem: DemRelief, variantId: string): void {
	const src = map.getSource(DEM_SRC) as maplibregl.ImageSource | undefined;
	const url = demVariantUrl(dem, variantId);
	if (src && url && 'updateImage' in src) src.updateImage({ url: `${DATA_BASE}/${url}` });
}

export function addDem(map: maplibregl.Map, dem?: DemRelief, variantId?: string): void {
	if (map.getSource(DEM_SRC)) return;
	// Lift the basemap's roads + boundaries + labels ABOVE the relief (insert it
	// just under the first such layer) so the city stays legible, while land/water
	// still read through the relief's transparency. Fall back to sitting just below
	// our own data layers.
	const ids = (map.getStyle().layers ?? []).map((l) => l.id);
	const before =
		ids.find(
			(id) =>
				id.startsWith('roads') ||
				id.startsWith('boundaries') ||
				id.startsWith('places') ||
				id.startsWith('pois')
		) ?? ids.find((id) => id.startsWith('lyr:') || id.startsWith('__hl'));

	const url = dem ? demVariantUrl(dem, variantId) : undefined;
	if (dem && url) {
		// Self-hosted relief: one pre-tinted image placed by its bbox corners.
		// No runtime dependency on the IDESC WMS, and already colored (MapLibre
		// can't colorize a grayscale raster — see the pipeline `dem_relief` asset).
		map.addSource(DEM_SRC, {
			type: 'image',
			url: `${DATA_BASE}/${url}`,
			coordinates: dem.coordinates
		});
		map.addLayer(
			{ id: DEM_LYR, type: 'raster', source: DEM_SRC, paint: { 'raster-opacity': 0.85 } },
			before
		);
		return;
	}

	// Fallback: live IDESC WMS (grayscale). Used only if the baked image is absent.
	const tiles =
		`${WMS_BASE}?service=WMS&version=1.1.1&request=GetMap&layers=${encodeURIComponent(DEM_LAYER)}` +
		`&styles=&format=image/png&transparent=true&srs=EPSG:3857&width=256&height=256&bbox={bbox-epsg-3857}`;
	map.addSource(DEM_SRC, {
		type: 'raster',
		tiles: [tiles],
		tileSize: 256,
		attribution: 'DEM: IDESC – Alcaldía de Cali'
	});
	map.addLayer(
		{ id: DEM_LYR, type: 'raster', source: DEM_SRC, paint: { 'raster-opacity': 0.7 } },
		before
	);
}

export function removeDem(map: maplibregl.Map): void {
	if (map.getLayer(DEM_LYR)) map.removeLayer(DEM_LYR);
	if (map.getSource(DEM_SRC)) map.removeSource(DEM_SRC);
}
