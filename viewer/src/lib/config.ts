// Base URL that serves the pipeline outputs: layers.json, geojson/, pmtiles/.
// Defaults to /data (symlinked to ../cali-geo/data in dev). Override with
// VITE_DATA_BASE for remote hosting (e.g. an S3/CloudFront bucket).
export const DATA_BASE = (import.meta.env.VITE_DATA_BASE ?? '/data').replace(/\/$/, '');

export const MANIFEST_URL = `${DATA_BASE}/layers.json`;

// Cali city center (lon, lat) and a sensible starting zoom.
export const CALI_CENTER: [number, number] = [-76.53, 3.42];
export const CALI_ZOOM = 11;

// Pan/zoom leash: keep the map on Cali. The view rubber-bands back to the city +
// the Farallones + a margin instead of wandering off to the ocean, and can't zoom
// out past the regional scale. SW then NE corner (lon, lat).
export const CALI_MIN_ZOOM = 10;
export const CALI_MAX_BOUNDS: [[number, number], [number, number]] = [
	[-77.05, 3.1],
	[-76.05, 3.75]
];

export type Layer = {
	key: string;
	typename: string;
	workspace: string;
	title_es: string;
	title_en: string;
	abstract_es: string;
	abstract_en: string;
	geometry_type: string | null;
	feature_count: number;
	serve: 'pmtiles' | 'geojson' | 'empty';
	url: string | null;
	bbox: [number, number, number, number] | null;
	fields?: string[];
	numeric_fields?: string[];
	// Per-field styling stats baked by scripts/build_field_stats.py: numeric
	// [min, max] ranges (graduated ramps) and low-cardinality string value lists
	// (categorical coloring). Absent on layers with no usable fields.
	field_ranges?: Record<string, [number, number]>;
	field_categories?: Record<string, string[]>;
};

// --- 3D / elevation ----------------------------------------------------------
// Attribute fields that carry an extrudable height, and how to read them.
// 'floors' → multiply by ~3 m/floor; 'meters' → use directly. 'cota' is an
// absolute elevation (m.a.s.l.) used to *color* contours, not to extrude.
export const HEIGHT_FIELDS: Record<string, 'floors' | 'meters'> = {
	id_alturas: 'floors',
	pisos: 'floors',
	niveles: 'floors',
	num_pisos: 'floors',
	caaltura: 'meters',
	altura: 'meters',
	altura_m: 'meters',
	rcgaltura: 'meters'
};
export const METERS_PER_FLOOR = 3;
export const ELEVATION_FIELD = 'cota';

// Sequential hypsometric ramp for contour `cota` — greens (valley floor) up
// through tans to browns (high ridges). Cali spans ~950–4100 m.a.s.l. Replaces
// the old rainbow ramp, which read as categorical rather than as elevation.
// Note: contours render as lines only — MapLibre can't raise lines in true 3D,
// so elevation is conveyed by color, not height.
export const ELEVATION_RAMP: [number, string][] = [
	[950, '#1a9850'],
	[1600, '#91cf60'],
	[2300, '#d9ef8b'],
	[3000, '#fee08b'],
	[3600, '#d8a06d'],
	[4100, '#8c5109']
];

// Green relief ramp used to colorize the grayscale DEM raster client-side
// (low = pale, high = deep green) via MapLibre `raster-color`.
export const DEM_RELIEF_RAMP: [number, string][] = [
	[0, '#f7fcf5'],
	[0.35, '#c7e9c0'],
	[0.6, '#74c476'],
	[0.8, '#31a354'],
	[1, '#006d2c']
];

// --- Data-driven layer coloring ("color by field") --------------------------
// Sequential ramp (stops are 0..1 fractions of a field's [min,max]) for coloring
// a layer by a numeric field. Blue→yellow→red — a perceptual "value" ramp, kept
// deliberately distinct from the green elevation/DEM ramps above.
export const GRADUATED_RAMP: [number, string][] = [
	[0, '#2c7bb6'],
	[0.25, '#abd9e9'],
	[0.5, '#ffffbf'],
	[0.75, '#fdae61'],
	[1, '#d7191c']
];

// Qualitative palette for coloring a layer by a categorical field (cycled by
// value index); '#9ca3af' (slate-400) is the fallback for unlisted values.
export const CATEGORICAL_PALETTE: string[] = [
	'#4e79a7', '#f28e2b', '#e15759', '#76b7b2', '#59a14f',
	'#edc948', '#b07aa1', '#ff9da7', '#9c755f', '#bab0ac'
];
export const CATEGORICAL_FALLBACK = '#9ca3af';

// --- Themes ------------------------------------------------------------------
// A theme bundles the WHOLE look so the map moves together: the Protomaps
// basemap `flavor`, the paired baked relief `variant`, the data color ramps
// (graduated + categorical), the page `background`, and basemap tuning (road
// opacity, road-casing hiding, boundary opacity). Relief is no longer selected
// independently — each theme owns one. The 4 light themes switch live (no
// basemap reload); only entering/leaving Dark changes the flavor.

// Protomaps basemap flavors. We use `light` for the warm/green themes and
// `dark` for the Dark theme; the others are listed for completeness.
export type Flavor = 'light' | 'dark' | 'white' | 'grayscale' | 'black';

export type Theme = {
	id: string;
	label_es: string;
	label_en: string;
	flavor: Flavor;
	/** Baked relief variant id (must match a `dem.variants[].id`). */
	variant: string;
	/** Graduated ramp for numeric "color by" (stops are 0..1 fractions). */
	graduatedRamp: [number, string][];
	/** Qualitative palette for categorical "color by". */
	categoricalPalette: string[];
	/** CSS page/map backdrop — shows around the clipped relief + behind a hidden base. */
	background: string;
	/** Relief raster opacity (dark themes go lower so hills stay dark, not gray). */
	reliefOpacity: number;
	/** Opacity for basemap road lines while relief is shown (1 = untouched). */
	roadOpacity: number;
	/** Hide the wide road `*casing*` sublayers (they read fuzzy over relief). */
	hideRoadCasing: boolean;
	/** Opacity for basemap boundary lines (tames the dashed admin strokes). */
	boundaryOpacity: number;
	/** Per-theme basemap tint so the base visibly shifts with the theme (applied
	 *  live as paint overrides on the Protomaps land/water/green/label layers). */
	basemap: {
		/** Land + background fill. */
		earth: string;
		/** Water bodies + streams + rivers. */
		water: string;
		/** Parks / urban green. */
		green: string;
		/** Label halo color (lighter/wider for legibility over dark relief). */
		labelHalo: string;
		/** Label halo width. */
		labelHaloWidth: number;
	};
};

// Brightened categorical palette for the dark theme (the light palette mud-dies
// against a near-black base).
export const CATEGORICAL_PALETTE_DARK: string[] = [
	'#6ea8e0', '#ffb24d', '#ff7b7d', '#5fd6cf', '#86d873',
	'#ffe773', '#d49ed0', '#ffc2cb', '#cc9e85', '#d8d0cc'
];

export const THEMES: Theme[] = [
	{
		id: 'original',
		label_es: 'Original',
		label_en: 'Original',
		flavor: 'light',
		variant: 'original',
		// Warm "Cali heat" sequential — saturated amber → deep wine, monotonic
		// in lightness so mid-values separate. Pops on cream and over the green
		// loma where the old green→tan ramp read as green-on-green.
		graduatedRamp: [
			[0, '#ffd24a'], [0.25, '#f7a23b'], [0.5, '#ea5f33'], [0.75, '#c0392b'], [1, '#7c1f3d']
		],
		categoricalPalette: CATEGORICAL_PALETTE,
		background: '#f0ebda',
		reliefOpacity: 0.82,
		roadOpacity: 0.35,
		hideRoadCasing: true,
		boundaryOpacity: 0.5,
		basemap: {
			earth: '#f0ebda',
			water: '#a7c9d4',
			green: '#c8d79c',
			labelHalo: '#ffffff',
			labelHaloWidth: 1.8
		}
	},
	{
		id: 'topo',
		label_es: 'Topográfico',
		label_en: 'Topo',
		flavor: 'light',
		variant: 'topo',
		// Cool counterpoint to the warm sepia base + brown relief — teal → deep
		// indigo. Cool data separates cleanly from the warm terrain.
		graduatedRamp: [
			[0, '#86e0d0'], [0.25, '#37b0bd'], [0.5, '#2a82b8'], [0.75, '#2b53a0'], [1, '#27286b']
		],
		categoricalPalette: CATEGORICAL_PALETTE,
		background: '#efe7d6',
		reliefOpacity: 0.85,
		roadOpacity: 0.35,
		hideRoadCasing: true,
		boundaryOpacity: 0.5,
		basemap: {
			earth: '#efe7d6',
			water: '#b6cdd2',
			green: '#d9cfa6',
			labelHalo: '#ffffff',
			labelHaloWidth: 1.8
		}
	},
	{
		id: 'slate',
		label_es: 'Pizarra',
		label_en: 'Slate',
		flavor: 'light',
		variant: 'slate',
		// Viridis (truncated short of pale yellow so the high end stays legible
		// on the light slate base): perceptually uniform, colorblind-safe, and
		// reads as "data" — the cleanest, most civic of the four.
		graduatedRamp: [
			[0, '#46327e'], [0.25, '#365c8d'], [0.5, '#21908d'], [0.75, '#36a86e'], [1, '#8fd744']
		],
		categoricalPalette: CATEGORICAL_PALETTE,
		background: '#eef2f6',
		reliefOpacity: 0.85,
		roadOpacity: 0.35,
		hideRoadCasing: true,
		boundaryOpacity: 0.5,
		basemap: {
			earth: '#eef2f6',
			water: '#bcd2e6',
			green: '#cdd9cf',
			labelHalo: '#ffffff',
			labelHaloWidth: 1.8
		}
	},
	{
		id: 'dark',
		label_es: 'Oscuro',
		label_en: 'Dark',
		flavor: 'dark',
		variant: 'oscuro',
		// Bright, glowing turbo on black — low values stay luminous enough to see
		// as thin lines, high values pop hot. Monotonic-ish so magnitude reads.
		graduatedRamp: [
			[0, '#39a0ff'], [0.25, '#2fd6c2'], [0.5, '#9be84f'], [0.75, '#ffc23a'], [1, '#ff5d5d']
		],
		categoricalPalette: CATEGORICAL_PALETTE_DARK,
		background: '#000000',
		// Relief sits over a true-black base: shadows (near-black ramp) read black,
		// ridges lift to bright slate. A touch higher opacity so the loma actually
		// reads instead of the map feeling uniformly too dark.
		reliefOpacity: 0.82,
		roadOpacity: 0.4,
		hideRoadCasing: true,
		boundaryOpacity: 0.3,
		basemap: {
			earth: '#000000',
			water: '#06121e',
			green: '#0a1610',
			labelHalo: '#000000',
			labelHaloWidth: 1.4
		}
	}
];

export const DEFAULT_THEME: Theme = THEMES[0];

// --- WMS DEM overlay (raster workspace; WCS is disabled) ---------------------
export const WMS_BASE = 'https://ws-idesc.cali.gov.co/geoserver/ows';
export const DEM_LAYER = 'raster:dem_modelo_elevacion_digital';

// Self-hosted DEM relief: several baked color ramps, each placed by the same
// bbox corners (TL, TR, BR, BL as [lon, lat]). Baked by the `dem_relief` asset.
export type DemVariant = { id: string; label_es: string; label_en: string; url: string };
export type DemRelief = {
	coordinates: [[number, number], [number, number], [number, number], [number, number]];
	width: number;
	height: number;
	default: string;
	variants: DemVariant[];
};

export type Manifest = {
	generated_layers: number;
	workspaces: string[];
	layers: Layer[];
	dem?: DemRelief;
};
