// Shareable URL state, kept in the hash so the static host never sees it.
// Format (all parts optional, defaults omitted):
//   #l=<key>[~c.<field>][~x[.<field>]],<key>…   enabled layers + styling
//   &t=<themeId>  &d=1 (relief on)  &b=0 (basemap hidden)
//   &e=<exaggeration>  &v=<zoom>/<lat>/<lon>[/<pitch>[/<bearing>]]
// Layer keys and field names are [a-z0-9_]+ so `~ . , & =` are safe separators.

import type { Map as MLMap } from 'maplibre-gl';
import { DEFAULT_THEME, THEMES } from '$lib/config';
import { fitToLayer } from '$lib/map';
import { app, DEFAULT_EXAGGERATION, type LayerStyle } from './app.svelte';

export type UrlLayer = { key: string; style: LayerStyle };

export type UrlState = {
	layers: UrlLayer[];
	theme?: string;
	dem?: boolean;
	base?: boolean;
	exaggeration?: number;
	cam?: { zoom: number; lat: number; lon: number; pitch: number; bearing: number };
};

export function parseHash(hash: string): UrlState {
	const out: UrlState = { layers: [] };
	const raw = hash.replace(/^#/, '');
	if (!raw) return out;
	for (const part of raw.split('&')) {
		const eq = part.indexOf('=');
		if (eq < 0) continue;
		const k = part.slice(0, eq);
		const v = decodeURIComponent(part.slice(eq + 1));
		if (k === 'l') {
			for (const entry of v.split(',')) {
				const [key, ...mods] = entry.split('~');
				if (!key) continue;
				const style: LayerStyle = {};
				for (const mod of mods) {
					if (mod.startsWith('c.')) style.colorField = mod.slice(2);
					else if (mod === 'x') style.extrude = true;
					else if (mod.startsWith('x.')) {
						style.extrude = true;
						style.extrudeField = mod.slice(2);
					}
				}
				out.layers.push({ key, style });
			}
		} else if (k === 't') out.theme = v;
		else if (k === 'd') out.dem = v === '1';
		else if (k === 'b') out.base = v === '1';
		else if (k === 'e') {
			const n = parseFloat(v);
			if (Number.isFinite(n)) out.exaggeration = n;
		} else if (k === 'v') {
			const nums = v.split('/').map(parseFloat);
			if (nums.length >= 3 && nums.every(Number.isFinite)) {
				const [zoom, lat, lon, pitch = 0, bearing = 0] = nums;
				out.cam = { zoom, lat, lon, pitch, bearing };
			}
		}
	}
	return out;
}

/** Serialize the CURRENT app + map state. Reads `app` reactive fields, so a
 *  caller inside $effect re-runs whenever any of them change. */
export function serializeState(map: MLMap | undefined): string {
	const parts: string[] = [];
	if (app.active.length) {
		const entries = app.active.map((key) => {
			const s = app.styleByKey[key] ?? {};
			let e = key;
			if (s.colorField) e += `~c.${s.colorField}`;
			if (s.extrude) e += s.extrudeField ? `~x.${s.extrudeField}` : '~x';
			return e;
		});
		parts.push(`l=${entries.join(',')}`);
	}
	if (app.themeId !== DEFAULT_THEME.id) parts.push(`t=${app.themeId}`);
	if (app.dem) parts.push('d=1');
	if (!app.baseVisible) parts.push('b=0');
	if (app.exaggeration !== DEFAULT_EXAGGERATION) parts.push(`e=${app.exaggeration}`);
	if (map) {
		const c = map.getCenter();
		const v = [map.getZoom().toFixed(2), c.lat.toFixed(5), c.lng.toFixed(5)];
		const pitch = Math.round(map.getPitch());
		const bearing = Math.round(map.getBearing());
		if (pitch || bearing) v.push(String(pitch));
		if (bearing) v.push(String(bearing));
		parts.push(`v=${v.join('/')}`);
	}
	return parts.length ? `#${parts.join('&')}` : '';
}

/** Restore a parsed hash into the app (call once map + manifest are ready). */
export function restoreState(state: UrlState): void {
	if (!app.map) return;
	if (state.dem === true && !app.dem) app.toggleDem();
	if (state.base === false && app.baseVisible) app.toggleBase();
	if (state.exaggeration !== undefined) app.exaggeration = state.exaggeration;
	for (const { key, style } of state.layers) {
		const l = app.layer(key);
		if (l) app.enable(l, style, false);
	}
	// Theme LAST. A flavor change (Dark) restyles the basemap and rebuilds the
	// active layers via reapply(), so they must already be enabled; recolorAll
	// then re-applies the theme's ramps to them. (Light themes recolor live.)
	if (state.theme && state.theme !== app.themeId) {
		const t = THEMES.find((x) => x.id === state.theme);
		if (t) app.pickTheme(t);
	}
	if (state.cam) {
		app.map.jumpTo({
			center: [state.cam.lon, state.cam.lat],
			zoom: state.cam.zoom,
			pitch: state.cam.pitch,
			bearing: state.cam.bearing
		});
	} else if (state.layers.length) {
		// No camera in the link: at least show the shared data.
		const first = app.layer(state.layers[0].key);
		if (first) fitToLayer(app.map, first);
	}
}

let syncTimer: ReturnType<typeof setTimeout> | undefined;

/** Debounced history.replaceState with the serialized hash (or none). */
export function scheduleUrlSync(hash: string): void {
	clearTimeout(syncTimer);
	syncTimer = setTimeout(() => {
		history.replaceState(null, '', hash || location.pathname + location.search);
	}, 300);
}
