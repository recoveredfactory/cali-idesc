// Single shared app state + the actions that keep the MapLibre map in sync
// with it. Components import the `app` singleton and call methods — no prop
// drilling, no duplicated enable/disable choreography. The map instance itself
// is NOT reactive state; it's owned here and mutated imperatively, exactly like
// the old +page.svelte did, just behind one tested surface.

import type { Map as MLMap } from 'maplibre-gl';
import {
	THEMES,
	DEFAULT_THEME,
	type Layer,
	type Manifest,
	type Theme
} from '$lib/config';
import {
	addLayer,
	removeLayer,
	fitToLayer,
	setHighlight,
	ensureHighlight,
	addDem,
	removeDem,
	setBasemapVisible,
	tuneBasemap,
	applyTheme,
	defaultExtrudeField,
	restyleExtrusion,
	setLayerColor,
	computeFieldStats,
	type ExtrudeOpts,
	type FieldStats
} from '$lib/map';
import type { Featured } from '$lib/featured';
import { autoStyle } from '$lib/autostyle';

/** Per-layer render style the user can change (all optional = defaults). */
export type LayerStyle = {
	colorField?: string;
	extrude?: boolean;
	extrudeField?: string;
};

/** The feature currently open in the inspector. */
export type Selected = {
	key: string;
	layer: Layer | null;
	workspace: string;
	geometryType: string;
	id: string | number | null;
	props: Record<string, unknown>;
	moreCount: number;
};

export const DEFAULT_EXAGGERATION = 3;

class AppState {
	/** The MapLibre map — set once by +page on mount. Not reactive. */
	map: MLMap | undefined;

	manifest = $state<Manifest | null>(null);
	/** Keys of enabled layers, in the order they were turned on. */
	active = $state<string[]>([]);
	styleByKey = $state<Record<string, LayerStyle>>({});
	fieldStats = $state<Record<string, FieldStats>>({});

	themeId = $state(DEFAULT_THEME.id);
	dem = $state(false);
	baseVisible = $state(true);
	exaggeration = $state(DEFAULT_EXAGGERATION);

	/** Key added by the last "surprise me" roll (rotates on the next roll). */
	randomKey = $state<string | null>(null);
	selected = $state<Selected | null>(null);

	// UI surfaces
	browserOpen = $state(false);
	aboutOpen = $state(false);
	infoLayer = $state<Layer | null>(null);

	readonly theme: Theme = $derived(
		THEMES.find((t) => t.id === this.themeId) ?? DEFAULT_THEME
	);
	readonly byKey = $derived(
		new Map((this.manifest?.layers ?? []).map((l) => [l.key, l]))
	);
	readonly activeLayers: Layer[] = $derived(
		this.active.map((k) => this.byKey.get(k)).filter((l): l is Layer => !!l)
	);
	readonly anyExtruded = $derived(
		this.active.some((k) => this.styleByKey[k]?.extrude)
	);

	layer(key: string): Layer | undefined {
		return this.byKey.get(key);
	}

	private optsFor(key: string): ExtrudeOpts {
		const s = this.styleByKey[key] ?? {};
		return {
			extrude: !!s.extrude,
			field: s.extrudeField ?? null,
			exaggeration: this.exaggeration,
			colorField: s.colorField ?? null
		};
	}

	// --- layer on/off -----------------------------------------------------

	/** Turn a layer on (optionally with a preset style), and usually fly to it. */
	enable(l: Layer, style?: LayerStyle, fly = true): void {
		if (!this.map || l.serve === 'empty' || !l.url) return;
		if (this.active.includes(l.key)) return;
		// Ad-hoc adds (browser tap, 🎲 surprise) arrive un-styled — pick a smart
		// default so the layer reads as data, not a flat blob. Curated featured
		// views and shared links pass their own (possibly empty) style and keep it.
		if (style === undefined) style = autoStyle(l);
		if (style && (style.colorField || style.extrude || style.extrudeField)) {
			this.styleByKey[l.key] = {
				...style,
				extrude: style.extrude ?? !!style.extrudeField
			};
			if (this.styleByKey[l.key].extrude && !this.styleByKey[l.key].extrudeField) {
				this.styleByKey[l.key].extrudeField = defaultExtrudeField(l) ?? undefined;
			}
		}
		addLayer(this.map, l, this.optsFor(l.key));
		this.active = [...this.active, l.key];
		if (this.styleByKey[l.key]?.colorField) this.refreshStats(l);
		if (fly) fitToLayer(this.map, l);
		// Only a 3D preset needs the camera pitched; a plain enable must NOT
		// touch the camera (an easeTo would cancel the fly-to above).
		if (this.styleByKey[l.key]?.extrude) this.syncPitch();
	}

	disable(key: string): void {
		if (!this.map) return;
		if (this.active.includes(key)) removeLayer(this.map, key);
		this.active = this.active.filter((k) => k !== key);
		delete this.styleByKey[key];
		delete this.fieldStats[key];
		if (this.randomKey === key) this.randomKey = null;
		if (this.selected?.key === key) this.closeInspector();
		this.syncPitch();
	}

	toggle(l: Layer): void {
		if (this.active.includes(l.key)) this.disable(l.key);
		else this.enable(l);
	}

	clearAll(): void {
		if (!this.map) return;
		for (const key of this.active) removeLayer(this.map, key);
		this.active = [];
		this.styleByKey = {};
		this.fieldStats = {};
		this.randomKey = null;
		this.closeInspector();
		this.syncPitch();
	}

	/** Reveal a random serveable layer and fly to it. Each roll drops the
	 *  previous random pick (only the one we added) and rotates to a fresh one.
	 *  Workspace-balanced so 105-layer pot_2014 doesn't win ~30% of rolls. */
	surprise(): void {
		if (!this.map || !this.manifest) return;
		const eligible = this.manifest.layers.filter(
			(l) =>
				l.serve !== 'empty' && l.url && l.key !== this.randomKey && !this.active.includes(l.key)
		);
		if (!eligible.length) return;
		const byWs = new Map<string, Layer[]>();
		for (const l of eligible) {
			(byWs.get(l.workspace) ?? byWs.set(l.workspace, []).get(l.workspace)!).push(l);
		}
		const workspaces = [...byWs.keys()];
		const group = byWs.get(workspaces[Math.floor(Math.random() * workspaces.length)])!;
		const pick = group[Math.floor(Math.random() * group.length)];
		if (this.randomKey && this.active.includes(this.randomKey)) this.disable(this.randomKey);
		this.enable(pick);
		this.randomKey = pick.key;
	}

	/** Apply a curated featured view: replaces whatever is on the map with the
	 *  preset layers + styling, optional relief, and its camera. */
	applyFeatured(f: Featured): void {
		if (!this.map || !this.manifest) return;
		this.clearAll();
		if (f.relief && !this.dem) this.toggleDem();
		let first = true;
		for (const ref of f.layers) {
			const l = this.byKey.get(ref.key);
			if (!l) continue;
			this.enable(
				l,
				{ colorField: ref.colorField, extrudeField: ref.extrudeField },
				// Without a camera override, fly to the FIRST layer's bbox only.
				!f.camera && first
			);
			first = false;
		}
		if (f.camera) {
			this.map.easeTo({
				center: f.camera.center,
				zoom: f.camera.zoom,
				pitch: f.camera.pitch ?? (this.anyExtruded ? 55 : 0),
				duration: 900
			});
		}
	}

	// --- per-layer styling --------------------------------------------------

	/** Pick (or clear, with '') the field a layer is colored by. */
	setColorField(l: Layer, field: string): void {
		const s = { ...(this.styleByKey[l.key] ?? {}) };
		if (field) s.colorField = field;
		else delete s.colorField;
		this.styleByKey[l.key] = s;
		if (this.map && this.active.includes(l.key)) {
			setLayerColor(this.map, l, field || null);
			this.refreshStats(l);
		}
	}

	/** Toggle 3D extrusion (changes the fill layer type → re-add the layer). */
	toggleExtrude(l: Layer): void {
		if (!this.map || !this.active.includes(l.key)) return;
		const s = { ...(this.styleByKey[l.key] ?? {}) };
		s.extrude = !s.extrude;
		if (s.extrude && !s.extrudeField) s.extrudeField = defaultExtrudeField(l) ?? undefined;
		this.styleByKey[l.key] = s;
		removeLayer(this.map, l.key);
		addLayer(this.map, l, this.optsFor(l.key));
		this.syncPitch();
	}

	setExtrudeField(l: Layer, field: string): void {
		this.styleByKey[l.key] = { ...(this.styleByKey[l.key] ?? {}), extrudeField: field };
		if (this.map && this.active.includes(l.key) && this.styleByKey[l.key].extrude) {
			restyleExtrusion(this.map, l, field, this.exaggeration);
		}
	}

	/** Live-apply the global exaggeration slider to every extruded layer. */
	applyExaggeration(): void {
		if (!this.map) return;
		for (const key of this.active) {
			const s = this.styleByKey[key];
			if (!s?.extrude) continue;
			const l = this.byKey.get(key);
			if (l) restyleExtrusion(this.map, l, s.extrudeField ?? null, this.exaggeration);
		}
	}

	/** Pitch the camera while anything is extruded, flatten when nothing is.
	 *  No-op when the pitch is already right, so it never cancels an in-flight
	 *  camera animation it doesn't need to. */
	private syncPitch(): void {
		if (!this.map) return;
		const want = this.anyExtruded ? 55 : 0;
		if (Math.round(this.map.getPitch()) === want) return;
		this.map.easeTo({ pitch: want, duration: 600 });
	}

	// --- field stats (contextual legends) ------------------------------------

	refreshStats(l: Layer): void {
		const field = this.styleByKey[l.key]?.colorField;
		if (this.map && field) this.fieldStats[l.key] = computeFieldStats(this.map, l, field);
		else delete this.fieldStats[l.key];
	}

	/** Refresh every colored layer's stats (e.g. when the map settles). */
	refreshAllStats(): void {
		for (const key of this.active) {
			if (!this.styleByKey[key]?.colorField) continue;
			const l = this.byKey.get(key);
			if (l) this.refreshStats(l);
		}
	}

	// --- map modes ------------------------------------------------------------

	toggleDem(): void {
		if (!this.map) return;
		this.dem = !this.dem;
		if (this.dem) addDem(this.map, this.manifest?.dem, this.theme.variant, this.theme.reliefOpacity);
		else removeDem(this.map);
		tuneBasemap(this.map, this.theme, this.dem && this.baseVisible);
	}

	/** Show/hide the entire Protomaps basemap (data + relief stay). */
	toggleBase(): void {
		if (!this.map) return;
		this.baseVisible = !this.baseVisible;
		setBasemapVisible(this.map, this.baseVisible);
		tuneBasemap(this.map, this.theme, this.dem && this.baseVisible);
	}

	pickTheme(t: Theme): void {
		if (!this.map || t.id === this.themeId) return;
		this.themeId = t.id;
		applyTheme(this.map, t, {
			reapply: () => this.reapply(),
			demOn: this.dem,
			baseVisible: this.baseVisible,
			dem: this.manifest?.dem,
			recolorAll: () => this.recolorAll()
		});
	}

	/** Rebuild every app-owned layer after a basemap restyle (Dark toggle). */
	reapply(): void {
		if (!this.map) return;
		if (this.dem) addDem(this.map, this.manifest?.dem, this.theme.variant, this.theme.reliefOpacity);
		for (const key of this.active) {
			const l = this.byKey.get(key);
			if (l) addLayer(this.map, l, this.optsFor(key));
		}
		ensureHighlight(this.map);
		this.syncPitch();
	}

	/** Re-apply every colored layer's color expression (new theme ramps). */
	recolorAll(): void {
		if (!this.map) return;
		for (const key of this.active) {
			const field = this.styleByKey[key]?.colorField;
			if (!field) continue;
			const l = this.byKey.get(key);
			if (l) setLayerColor(this.map, l, field);
		}
		this.refreshAllStats();
	}

	// --- inspector --------------------------------------------------------------

	select(sel: Selected, feature: GeoJSON.Feature | null): void {
		this.selected = sel;
		if (this.map) setHighlight(this.map, feature);
	}

	closeInspector(): void {
		this.selected = null;
		if (this.map) setHighlight(this.map, null);
	}
}

export const app = new AppState();
