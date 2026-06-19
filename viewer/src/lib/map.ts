import maplibregl from 'maplibre-gl';
import { Protocol } from 'pmtiles';
import { layers as protomapsLayers, namedFlavor } from '@protomaps/basemaps';
import {
	DATA_BASE,
	CALI_CENTER,
	CALI_ZOOM,
	CALI_MIN_ZOOM,
	CALI_MAX_BOUNDS,
	HEIGHT_FIELDS,
	METERS_PER_FLOOR,
	ELEVATION_FIELD,
	ELEVATION_RAMP,
	GRADUATED_RAMP,
	CATEGORICAL_PALETTE,
	CATEGORICAL_FALLBACK,
	DEFAULT_THEME,
	WMS_BASE,
	DEM_LAYER,
	type Flavor,
	type Theme,
	type Layer,
	type DemRelief
} from './config';

let protocolRegistered = false;

// --- Active theme ramps (module-level) ---------------------------------------
// The data "color by" ramps are theme-dependent, but threading a `theme` through
// every call site (addLayer, colorByExpr, computeFieldStats, the +page legend)
// would be noisy. Instead the active ramps live here as module-level state, set
// by `setThemeRamps(theme)` whenever the theme changes (the app is client-only,
// single-map, so shared module state is fine). Defaults mirror the static config
// ramps so anything reading before the first theme is applied still works.
let activeGraduated: [number, string][] = DEFAULT_THEME.graduatedRamp ?? GRADUATED_RAMP;
let activeCategorical: string[] = DEFAULT_THEME.categoricalPalette ?? CATEGORICAL_PALETTE;
let activeCategoricalFallback: string = CATEGORICAL_FALLBACK;

/** Set the active data-color ramps from a theme. Call before the first
 *  `addLayer` and before each recolor so expressions/legends stay in sync. */
export function setThemeRamps(theme: Theme): void {
	activeGraduated = theme.graduatedRamp;
	activeCategorical = theme.categoricalPalette;
}

/** The active graduated ramp — for the legend gradient + histogram bar colors. */
export function getActiveGraduated(): [number, string][] {
	return activeGraduated;
}

// --- categorical color assignment -------------------------------------------
// Most categorical fields get the qualitative palette (one hue per value). But
// ORDINAL categoricals — values that carry an inherent order, like Level of
// Service "A".."F" or estrato "1: Bajo-bajo".."6: Alto" — read far better on the
// theme's sequential ramp (light→intense = low→high) so magnitude shows. We
// sniff ordinality from the value shape and, when found, color by rank.

// Spanish magnitude ladders (low → high), accent/case-insensitive. Many Cali
// layers classify by quality words instead of numbers — tree density
// (Baja…Muy Alta), flood hazard (Baja/Media/Alta), noise bands, etc. Recognizing
// them lets those layers land on the sequential ramp (light→intense) like the
// A–F and numeric ordinals, instead of getting arbitrary qualitative hues.
const ES_MAGNITUDE: Record<string, number> = {
	'muy baja': 0,
	'muy bajo': 0,
	baja: 1,
	bajo: 1,
	regular: 2,
	media: 3,
	medio: 3,
	moderada: 3,
	moderado: 3,
	alta: 4,
	alto: 4,
	'muy alta': 5,
	'muy alto': 5
};
const esNorm = (v: string) =>
	v.trim().toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, ''); // strip accents

/** A rank function if `values` look ordinal (single A–G letters, a leading
 *  integer like "3: Medio-bajo", or a Spanish magnitude ladder like
 *  "Baja…Muy Alta"), else null. */
function ordinalRank(values: string[]): ((v: string) => number) | null {
	const vals = values.map((v) => v.trim()).filter(Boolean);
	if (vals.length < 2) return null;
	if (vals.every((v) => /^[A-Ga-g]$/.test(v))) return (v) => v.trim().toUpperCase().charCodeAt(0);
	if (vals.every((v) => /^-?\d+/.test(v.trim()))) return (v) => parseInt(v.trim(), 10);
	if (vals.every((v) => esNorm(v) in ES_MAGNITUDE)) return (v) => ES_MAGNITUDE[esNorm(v)];
	return null;
}

/** Mix two "#rrggbb" colors, `f` in [0,1]. */
function hexLerp(c1: string, c2: string, f: number): string {
	const p = (c: string) => [1, 3, 5].map((i) => parseInt(c.slice(i, i + 2), 16));
	const [r1, g1, b1] = p(c1);
	const [r2, g2, b2] = p(c2);
	const m = (a: number, b: number) =>
		Math.round(a + (b - a) * f)
			.toString(16)
			.padStart(2, '0');
	return `#${m(r1, r2)}${m(g1, g2)}${m(b1, b2)}`;
}

/** Sample the active graduated ramp at t∈[0,1] → "#rrggbb" (JS-side, for legends
 *  and ordinal categorical swatches; the map expression interpolates its own). */
function rampColorAt(t: number): string {
	const stops = activeGraduated;
	const x = Math.max(0, Math.min(1, t));
	let a = stops[0];
	let b = stops[stops.length - 1];
	for (let i = 0; i < stops.length - 1; i++) {
		if (x >= stops[i][0] && x <= stops[i + 1][0]) {
			a = stops[i];
			b = stops[i + 1];
			break;
		}
	}
	const span = b[0] - a[0] || 1;
	return hexLerp(a[1], b[1], (x - a[0]) / span);
}

/** A color per category value, index-aligned with `values`. Ordinal domains map
 *  onto the graduated ramp by rank; everything else cycles the qualitative
 *  palette. Shared by the map expression and the legend so they always agree. */
function categoryColors(values: string[]): string[] {
	const rank = ordinalRank(values);
	if (rank) {
		const sorted = [...new Set(values)].sort((p, q) => rank(p) - rank(q));
		const n = sorted.length;
		const byVal = new Map(sorted.map((v, i) => [v, rampColorAt(n === 1 ? 0.5 : i / (n - 1))]));
		return values.map((v) => byVal.get(v) ?? activeCategoricalFallback);
	}
	return values.map((_, i) => activeCategorical[i % activeCategorical.length]);
}

// --- Boundary render treatment ----------------------------------------------
// Administrative outlines (comunas, barrios) and historic perimeters read best
// as crisp strokes over a barely-there fill — four nested same-color rings
// otherwise turn to mud. Conservative: only low-feature polygon-ish layers whose
// name marks them as a boundary/perimeter (a real choropleth keeps its fill).
const BOUNDARY_NAME = /perimetro|perímetro|contorno|limite|límite|comuna|barrio|corregimiento|vereda/i;
const FLAT_FILL_OPACITY = 0.5; // denser than the old 0.35 — choropleths read more solidly
const BOUNDARY_FILL_OPACITY = 0.12;
const BOUNDARY_LINE_WIDTH = 2.2;

function isBoundaryLayer(layer: Layer): boolean {
	const g = (layer.geometry_type ?? '').toLowerCase();
	if (!(g.includes('polygon') || g.includes('unknown'))) return false;
	if ((layer.feature_count ?? 0) > 600) return false; // skips manzanas, predios, …
	return BOUNDARY_NAME.test(layer.key) || BOUNDARY_NAME.test(layer.typename ?? '');
}

// Basemap = the grupovisual Protomaps planet build (single PMTiles, range-served).
const BASEMAP_PMTILES = 'pmtiles://https://pmtiles.grupovisual.org/latest.pmtiles';

// Flavor currently realized in the map style — used to decide whether a theme
// switch needs a full `setStyle` (flavor change) or just live tuning.
let currentFlavor: Flavor = DEFAULT_THEME.flavor;

/** Sprite sheet matching a flavor (dark/black icons are pre-tinted for dark bg). */
function spriteUrl(flavor: Flavor): string {
	const base = 'https://protomaps.github.io/basemaps-assets/sprites/v4';
	return flavor === 'dark' || flavor === 'black' ? `${base}/dark` : `${base}/light`;
}

function basemapStyle(flavor: Flavor): maplibregl.StyleSpecification {
	return {
		version: 8,
		glyphs: 'https://protomaps.github.io/basemaps-assets/fonts/{fontstack}/{range}.pbf',
		sprite: spriteUrl(flavor),
		sources: {
			protomaps: {
				type: 'vector',
				url: BASEMAP_PMTILES,
				attribution:
					'<a href="https://protomaps.com">Protomaps</a> © <a href="https://openstreetmap.org">OpenStreetMap</a>'
			}
		},
		layers: protomapsLayers('protomaps', namedFlavor(flavor), { lang: 'es' })
	};
}

export function createMap(container: HTMLElement): maplibregl.Map {
	if (!protocolRegistered) {
		maplibregl.addProtocol('pmtiles', new Protocol().tile);
		protocolRegistered = true;
	}
	currentFlavor = DEFAULT_THEME.flavor;
	const map = new maplibregl.Map({
		container,
		style: basemapStyle(currentFlavor),
		center: CALI_CENTER,
		zoom: CALI_ZOOM,
		minZoom: CALI_MIN_ZOOM,
		maxBounds: CALI_MAX_BOUNDS,
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
	/** Override the computed line/outline width (e.g. a subtler boundary stroke). */
	lineWidth?: number;
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

// Tallest generic-field feature, in metres, at exaggeration 1. Bounds the
// extrusion so a large-magnitude attribute (counts, areas, IDs) can't produce
// absurd skyscrapers — the field's whole [min,max] maps into [0, this·exag].
const NORM_MAX_HEIGHT = 120;

/** Height-in-metres expression for `field`, scaled by vertical exaggeration.
 *  - Known height fields (floors/metres): real-world height (exaggeration is a
 *    plain multiplier).
 *  - Any other numeric field: its `range` [min,max] is mapped onto a bounded
 *    height so the 3D doesn't blow up; `interpolate` clamps out-of-range values.
 *  - No range available: falls back to the raw value × exaggeration. */
function heightExpr(field: string, exaggeration = 1, range?: [number, number]) {
	const val = ['coalesce', ['to-number', ['get', field]], 0];
	if (field in HEIGHT_FIELDS) {
		const meters = modeFor(field) === 'floors' ? ['*', val, METERS_PER_FLOOR] : val;
		return exaggeration === 1 ? meters : ['*', meters, exaggeration];
	}
	if (range && range[1] > range[0]) {
		const [min, max] = range;
		return [
			'interpolate', ['linear'], ['to-number', ['get', field], min],
			min, 0, max, NORM_MAX_HEIGHT * exaggeration
		];
	}
	return exaggeration === 1 ? val : ['*', val, exaggeration];
}

function elevationColor() {
	return [
		'interpolate',
		['linear'],
		['coalesce', ['to-number', ['get', ELEVATION_FIELD]], ELEVATION_RAMP[0][0]],
		...ELEVATION_RAMP.flat()
	];
}

/** Circle radius (px) for value-scaled points. Generic numeric fields map their
 *  [min,max] onto a bounded [3,16] px so points can't balloon; known height
 *  fields scale by their (bounded) height expression. */
const circleRadiusExpr = (field: string, exaggeration: number, range?: [number, number]) => {
	if (!(field in HEIGHT_FIELDS) && range && range[1] > range[0]) {
		const [min, max] = range;
		return [
			'interpolate', ['linear'], ['to-number', ['get', field], min],
			min, 3, max, 16
		] as unknown as number;
	}
	return [
		'interpolate', ['linear'], heightExpr(field, exaggeration, range), 0, 3, 25, 14
	] as unknown as number;
};

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
		const stops = activeGraduated.flatMap(([t, c]) => [min + t * (max - min), c]);
		return ['interpolate', ['linear'], ['to-number', ['get', field], min], ...stops];
	}
	const cats = layer.field_categories?.[field];
	if (cats?.length) {
		const colors = categoryColors(cats);
		const pairs = cats.flatMap((v, i) => [v, colors[i]]);
		return ['match', ['to-string', ['get', field]], ...pairs, activeCategoricalFallback];
	}
	return null;
}

// Line width when a line layer is colored by a NUMERIC field: gently widen with
// the value so magnitude reads twice (hue + weight) and big segments are easier
// to see/hit. Kept subtle — [min,max] maps onto [DATA_LINE_MIN, DATA_LINE_MAX]px.
// Returns null for categorical / no-range fields (caller keeps the flat width).
const DATA_LINE_MIN = 0.8;
const DATA_LINE_MAX = 3.4;
function lineWidthExpr(layer: Layer, field: string): unknown | null {
	const range = layer.field_ranges?.[field];
	if (!range) return null;
	const [min, max] = range;
	if (!(max > min)) return null;
	return ['interpolate', ['linear'], ['to-number', ['get', field], min], min, DATA_LINE_MIN, max, DATA_LINE_MAX];
}

/** Live-recolor an already-added layer by `field` (or revert to the flat
 *  workspace color when `field` is null) without re-adding it. Sets fill/circle
 *  and the line outline; reverting restores the elevation line color on contour
 *  layers. A numeric color field also gently scales line width (see
 *  `lineWidthExpr`); reverting restores the flat width. */
export function setLayerColor(
	map: maplibregl.Map,
	layer: Layer,
	field: string | null,
	widthOverride?: number
): void {
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
		// A user width override wins; otherwise boundary > data-driven > default.
		const lw =
			widthOverride ??
			(isBoundaryLayer(layer)
				? BOUNDARY_LINE_WIDTH
				: (field ? lineWidthExpr(layer, field) : null) ?? 1.4);
		map.setPaintProperty(line, 'line-width', lw as never);
	}
}

/** The line/outline width a layer renders at with no user override (mirrors the
 *  scalar defaults in `addLayer`) — used to seed the width slider. */
export function defaultLineWidth(layer: Layer): number {
	return isBoundaryLayer(layer) ? BOUNDARY_LINE_WIDTH : 1.4;
}

/** Live-set a layer's line / polygon-outline width (px). Overrides the boundary,
 *  data-driven, and default widths until cleared by a re-add. */
export function setLineWidth(map: maplibregl.Map, layer: Layer, width: number): void {
	const line = lyrId(layer.key, 'line');
	if (map.getLayer(line)) map.setPaintProperty(line, 'line-width', width as never);
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
		const colors = categoryColors(cats);
		const items = cats.map((value, i) => ({
			value,
			color: colors[i],
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
	// Boundaries (admin outlines, historic perimeters) render as stroke-forward
	// outlines with a faint fill, never the flat translucent wash.
	const boundary = isBoundaryLayer(layer);

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
				// Opaque: 3D buildings/volumes shouldn't let the ground + other data
				// layers show through their walls.
				'fill-extrusion-opacity': 1,
				'fill-extrusion-base': 0,
				'fill-extrusion-height': heightExpr(
					extrudeField,
					exaggeration,
					layer.field_ranges?.[extrudeField]
				) as unknown as number
			}
		});
	} else {
		map.addLayer({
			id: lyrId(layer.key, 'fill'),
			type: 'fill',
			source: srcId(layer.key),
			...sourceLayer,
			filter: ['==', ['geometry-type'], 'Polygon'],
			paint: {
				'fill-color': fillColor,
				'fill-opacity': boundary ? BOUNDARY_FILL_OPACITY : FLAT_FILL_OPACITY
			}
		});
	}

	// Lines (and polygon outlines): color by elevation whenever `cota` exists.
	// Boundaries get a heavy flat stroke; otherwise a numeric color field gently
	// scales the width so magnitude reads as weight too.
	const lineWidth =
		opts.lineWidth ??
		(boundary
			? BOUNDARY_LINE_WIDTH
			: opts.colorField
				? lineWidthExpr(layer, opts.colorField) ?? 1.4
				: hasElevation
					? 1.3
					: 1.4);
	const lineColor = colorExpr ?? (hasElevation ? elevationColor() : color);
	map.addLayer({
		id: lyrId(layer.key, 'line'),
		type: 'line',
		source: srcId(layer.key),
		...sourceLayer,
		filter: ['in', ['geometry-type'], ['literal', ['LineString', 'Polygon']]],
		paint: {
			'line-color': lineColor as unknown as string,
			'line-width': lineWidth as unknown as number,
			'line-opacity': boundary ? 0.95 : 1
		}
	});

	// Points: fixed dots, or value-scaled when this layer is in 3D with a chosen field.
	map.addLayer({
		id: lyrId(layer.key, 'circle'),
		type: 'circle',
		source: srcId(layer.key),
		...sourceLayer,
		filter: ['==', ['geometry-type'], 'Point'],
		paint: {
			'circle-radius': extrudeField
				? circleRadiusExpr(extrudeField, exaggeration, layer.field_ranges?.[extrudeField])
				: 4,
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
	const range = layer.field_ranges?.[f];
	const fill = lyrId(layer.key, 'fill');
	if (map.getLayer(fill) && map.getLayer(fill)!.type === 'fill-extrusion') {
		map.setPaintProperty(fill, 'fill-extrusion-height', heightExpr(f, exaggeration, range) as unknown as number);
	}
	const circle = lyrId(layer.key, 'circle');
	if (map.getLayer(circle)) {
		map.setPaintProperty(circle, 'circle-radius', circleRadiusExpr(f, exaggeration, range));
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

/** Frame the full baked-relief extent. The DEM image runs past the pan leash, so
 *  clamp to it — that's the reachable region, and it's entirely under hillshade.
 *  (On a portrait phone the leash + minZoom floor this at the most-zoomed-out
 *  view; on a wide screen it shows the whole valley-to-Farallones extent.) */
export function fitToDem(map: maplibregl.Map, dem: DemRelief): void {
	const lons = dem.coordinates.map((c) => c[0]);
	const lats = dem.coordinates.map((c) => c[1]);
	const [[west, south], [east, north]] = CALI_MAX_BOUNDS;
	map.fitBounds(
		[
			[Math.max(Math.min(...lons), west), Math.max(Math.min(...lats), south)],
			[Math.min(Math.max(...lons), east), Math.min(Math.max(...lats), north)]
		],
		{ padding: 12, duration: 900 }
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

/** Re-stack the app's data layers to match `keys` (in bottom→top draw order),
 *  keeping the highlight layers on top. Each app layer is up to three MapLibre
 *  sublayers (fill/line/circle); `moveLayer(id)` with no `before` sends a layer
 *  to the very top, so iterating `keys` in order leaves the last key on top. The
 *  basemap + relief sit below all `lyr:` layers and aren't touched. */
export function restackLayers(map: maplibregl.Map, keys: string[]): void {
	for (const key of keys) {
		for (const suffix of ['fill', 'line', 'circle']) {
			const id = lyrId(key, suffix);
			if (map.getLayer(id)) map.moveLayer(id);
		}
	}
	for (const id of HIGHLIGHT_LAYERS) if (map.getLayer(id)) map.moveLayer(id);
}

/** Ids of our data layers currently on the map (only enabled layers are added). */
export function inspectableLayerIds(map: maplibregl.Map): string[] {
	return (map.getStyle().layers ?? [])
		.map((l) => l.id)
		.filter((id) => id.startsWith('lyr:'));
}

// Thin lines (and small points) are hard to tap dead-on, so query a small box
// around the cursor when an exact hit misses. Exact hits still win, keeping the
// topmost feature under the pointer; the tolerance only rescues near-misses.
const HIT_TOL = 6; // px

export function pickFeatures(
	map: maplibregl.Map,
	point: { x: number; y: number }
): maplibregl.MapGeoJSONFeature[] {
	const ids = inspectableLayerIds(map);
	if (!ids.length) return [];
	const exact = map.queryRenderedFeatures(point as maplibregl.PointLike, { layers: ids });
	if (exact.length) return exact;
	return map.queryRenderedFeatures(
		[
			[point.x - HIT_TOL, point.y - HIT_TOL],
			[point.x + HIT_TOL, point.y + HIT_TOL]
		],
		{ layers: ids }
	);
}

// --- Layer ordering helpers --------------------------------------------------

/** First app-owned overlay (data `lyr:` or highlight `__hl`). Relief sits just
 *  below this so data and the highlight always stay on top. */
function appTopBeforeId(map: maplibregl.Map): string | undefined {
	return (map.getStyle().layers ?? [])
		.map((l) => l.id)
		.find((id) => id.startsWith('lyr:') || id.startsWith('__hl'));
}

/** Where relief sits in the UNMASKED stack: just under the basemap's roads /
 *  boundaries / labels so the city stays legible over it; else under data. */
function reliefBeforeId(map: maplibregl.Map): string | undefined {
	const ids = (map.getStyle().layers ?? []).map((l) => l.id);
	return (
		ids.find(
			(id) =>
				id.startsWith('roads') ||
				id.startsWith('boundaries') ||
				id.startsWith('places') ||
				id.startsWith('pois')
		) ?? appTopBeforeId(map)
	);
}

// --- DEM overlay (WMS raster) ------------------------------------------------

const DEM_SRC = '__dem-src';
const DEM_LYR = '__dem';

/** Resolve a relief variant's served URL: the requested id, else the default. */
function demVariantUrl(dem: DemRelief, variantId?: string): string | undefined {
	const exact = dem.variants.find((x) => x.id === variantId);
	if (!exact && variantId && import.meta.env.DEV) {
		console.warn(`[dem] no baked relief variant "${variantId}"; falling back to "${dem.default}"`);
	}
	const v = exact ?? dem.variants.find((x) => x.id === dem.default);
	return (v ?? dem.variants[0])?.url;
}

/** Swap the relief image in place (no remove/re-add) when the selector changes. */
export function setDemVariant(map: maplibregl.Map, dem: DemRelief, variantId: string): void {
	const src = map.getSource(DEM_SRC) as maplibregl.ImageSource | undefined;
	const url = demVariantUrl(dem, variantId);
	if (src && url && 'updateImage' in src) src.updateImage({ url: `${DATA_BASE}/${url}` });
}

export function addDem(
	map: maplibregl.Map,
	dem?: DemRelief,
	variantId?: string,
	opacity = 0.85
): void {
	if (map.getSource(DEM_SRC)) return;
	// Lift the basemap's roads + boundaries + labels ABOVE the relief (insert it
	// just under the first such layer) so the city stays legible, while land/water
	// still read through the relief's transparency. Fall back to sitting just below
	// our own data layers.
	const before = reliefBeforeId(map);

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
			{ id: DEM_LYR, type: 'raster', source: DEM_SRC, paint: { 'raster-opacity': opacity } },
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

/** Set the relief raster opacity in place (themes use different values). */
export function setReliefOpacity(map: maplibregl.Map, opacity: number): void {
	if (map.getLayer(DEM_LYR)) map.setPaintProperty(DEM_LYR, 'raster-opacity', opacity);
}

// --- Basemap (Protomaps) visibility + road prominence -----------------------

/** A basemap layer is any style layer that isn't one of ours (data `lyr:`,
 *  highlight `__hl`, or the relief `__dem`). */
const isBasemapLayer = (id: string) =>
	!id.startsWith('lyr:') && !id.startsWith('__hl') && id !== DEM_LYR;

/** Show or hide the entire Protomaps basemap, leaving relief + data layers. */
export function setBasemapVisible(map: maplibregl.Map, visible: boolean): void {
	const v = visible ? 'visible' : 'none';
	for (const l of map.getStyle().layers ?? []) {
		if (isBasemapLayer(l.id)) map.setLayoutProperty(l.id, 'visibility', v);
	}
}

/** Tune the basemap road + boundary lines for a theme while relief is shown so
 *  they don't overpower it. When `subdued`: hide the wide road `*casing*`
 *  sublayers (if `theme.hideRoadCasing`), dim the remaining `roads*` lines to
 *  `theme.roadOpacity`, and dim `boundaries*` (the dashed admin strokes) to
 *  `theme.boundaryOpacity`. When not subdued, restore the flavor defaults
 *  (clears each override with `undefined`). `startsWith('roads')` already covers
 *  `roads_bridges_*`.
 *
 *  Casings are dimmed via `line-opacity` (0), NOT `visibility`: visibility is
 *  owned by `setBasemapVisible` (the master Base on/off), and toggling it here
 *  too would fight it — casings re-appeared as ghostly outlines when the whole
 *  basemap was hidden. Opacity and visibility compose cleanly. */
export function tuneBasemap(map: maplibregl.Map, theme: Theme, subdued: boolean): void {
	for (const l of map.getStyle().layers ?? []) {
		if (l.type !== 'line') continue;
		const id = l.id;
		if (id.startsWith('roads')) {
			if (theme.hideRoadCasing && id.includes('casing')) {
				map.setPaintProperty(id, 'line-opacity', subdued ? 0 : undefined);
			} else {
				map.setPaintProperty(id, 'line-opacity', subdued ? theme.roadOpacity : undefined);
			}
		} else if (id.startsWith('boundaries')) {
			map.setPaintProperty(id, 'line-opacity', subdued ? theme.boundaryOpacity : undefined);
		}
	}
}

// Protomaps basemap layer ids tinted per theme (so switching theme visibly moves
// the base, not just the relief). Verified against @protomaps/basemaps layers().
const TINT_WATER_FILL = ['water'];
const TINT_WATER_LINE = ['water_stream', 'water_river']; // waterways are line layers
const TINT_GREEN = ['landuse_park', 'landuse_urban_green'];
const TINT_LABELS = [
	'places_locality', 'places_subplace', 'places_region',
	'roads_labels_major', 'roads_labels_minor', 'address_label'
];

/** Apply a theme's basemap tint as live paint overrides: land/background, water,
 *  green, and a stronger label halo (so dark labels stay legible over relief).
 *  Idempotent and safe to call whenever the relevant layers exist. */
export function tintBasemap(map: maplibregl.Map, theme: Theme): void {
	const bm = theme.basemap;
	const set = (id: string, prop: string, val: unknown) => {
		if (map.getLayer(id)) map.setPaintProperty(id, prop, val as never);
	};
	set('background', 'background-color', bm.earth);
	set('earth', 'fill-color', bm.earth);
	for (const id of TINT_WATER_FILL) set(id, 'fill-color', bm.water);
	for (const id of TINT_WATER_LINE) set(id, 'line-color', bm.water);
	for (const id of TINT_GREEN) set(id, 'fill-color', bm.green);
	for (const id of TINT_LABELS) {
		set(id, 'text-halo-color', bm.labelHalo);
		set(id, 'text-halo-width', bm.labelHaloWidth);
	}
}

// --- Theme application -------------------------------------------------------

/** Callbacks the component supplies so `applyTheme` can drive Svelte-owned state
 *  without `map.ts` importing Svelte. The component must set its `activeTheme`
 *  state (and anything derived from it — page background, `demVariant`) BEFORE
 *  calling `applyTheme`, so `reapply` reads the new theme. */
export type ThemeApplyCtx = {
	/** Rebuild all app-owned layers from scratch: relief (if `demOn`) → enabled
	 *  data layers → highlight → pitch. Called only after a flavor `setStyle`. */
	reapply: () => void;
	/** Is the relief currently shown? */
	demOn: boolean;
	/** Is the Protomaps basemap currently visible? */
	baseVisible: boolean;
	/** Relief metadata (for a live variant swap when the flavor is unchanged). */
	dem?: DemRelief;
	/** Re-apply every colored layer's color expression with the new ramps. */
	recolorAll: () => void;
};

/** Move the whole map to a new theme. The 4 light themes switch live (no basemap
 *  reload); only entering/leaving Dark changes the Protomaps flavor, which needs
 *  a `setStyle` (wiping app layers) followed by a `reapply()` rebuild. */
export function applyTheme(map: maplibregl.Map, theme: Theme, ctx: ThemeApplyCtx): void {
	setThemeRamps(theme);

	if (theme.flavor === currentFlavor) {
		// Same flavor: keep the basemap. Swap the relief image + opacity, re-tint
		// the base, re-tune roads/boundaries, and recolor data to the new ramps. No flash.
		if (ctx.demOn && ctx.dem) {
			setDemVariant(map, ctx.dem, theme.variant);
			setReliefOpacity(map, theme.reliefOpacity);
		}
		tintBasemap(map, theme);
		tuneBasemap(map, theme, ctx.demOn && ctx.baseVisible);
		ctx.recolorAll();
		return;
	}

	// Flavor change (Dark ↔ light): full restyle wipes every app-owned layer +
	// tuning, so rebuild on the next `styledata`. Use {diff:false} + once() (not a
	// persistent listener, not 'style.load').
	currentFlavor = theme.flavor;
	map.setStyle(basemapStyle(theme.flavor), { diff: false });
	map.once('styledata', () => {
		ctx.reapply();
		setBasemapVisible(map, ctx.baseVisible);
		tintBasemap(map, theme);
		tuneBasemap(map, theme, ctx.demOn && ctx.baseVisible);
		ctx.recolorAll();
	});
}
