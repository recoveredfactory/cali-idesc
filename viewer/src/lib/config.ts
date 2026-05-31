// Base URL that serves the pipeline outputs: layers.json, geojson/, pmtiles/.
// Defaults to /data (symlinked to ../cali-geo/data in dev). Override with
// VITE_DATA_BASE for remote hosting (e.g. an S3/CloudFront bucket).
export const DATA_BASE = (import.meta.env.VITE_DATA_BASE ?? '/data').replace(/\/$/, '');

export const MANIFEST_URL = `${DATA_BASE}/layers.json`;

// Cali city center (lon, lat) and a sensible starting zoom.
export const CALI_CENTER: [number, number] = [-76.53, 3.42];
export const CALI_ZOOM = 11;

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
