<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { fly, fade } from 'svelte/transition';
	import 'maplibre-gl/dist/maplibre-gl.css';
	import type { Map as MLMap, MapMouseEvent } from 'maplibre-gl';
	import { MANIFEST_URL, THEMES, DEFAULT_THEME, type Layer, type Manifest, type Theme } from '$lib/config';
	import {
		createMap,
		addLayer,
		removeLayer,
		fitToLayer,
		workspaceColor,
		setHighlight,
		ensureHighlight,
		inspectableLayerIds,
		addDem,
		removeDem,
		setBasemapVisible,
		tuneBasemap,
		tintBasemap,
		setThemeRamps,
		applyTheme,
		extrudableFields,
		defaultExtrudeField,
		restyleExtrusion,
		colorableFields,
		hasColorableFields,
		setLayerColor,
		computeFieldStats,
		type ExtrudeOpts,
		type FieldStats
	} from '$lib/map';
	import { fieldDef, fieldLabel, fieldTitle } from '$lib/fields';
	import { m } from '$lib/paraglide/messages';
	import { getLocale, setLocale, locales } from '$lib/paraglide/runtime';
	import rfLogo from '$lib/assets/recovered-factory.png';

	const locale = getLocale();

	let mapEl: HTMLDivElement;
	let map: MLMap | undefined;
	let manifest = $state<Manifest | null>(null);
	let enabled = $state<Record<string, boolean>>({});
	let infoLayer = $state<Layer | null>(null); // layer whose details popup is open
	let search = $state('');
	let searchEl: HTMLInputElement | undefined;
	let dem = $state(false);
	let baseVisible = $state(true); // Protomaps basemap shown?
	// The active theme bundles the basemap flavor, the paired relief variant, the
	// data color ramps, the page background, and road/boundary tuning.
	let activeTheme = $state<Theme>(DEFAULT_THEME);
	// Per-layer 3D: which enabled layers extrude, and by which numeric field.
	let extrude = $state<Record<string, boolean>>({});
	let extrudeField = $state<Record<string, string>>({});
	// Global vertical exaggeration applied to every extruded layer's height.
	let exaggeration = $state(3);
	// Per-layer "color by field" selection, and the client-side stats (histogram /
	// category counts) backing the contextual legend for each colored layer.
	let colorField = $state<Record<string, string>>({});
	let fieldStats = $state<Record<string, FieldStats>>({});
	// The catalog has 350+ layers; this is the key of the layer the "Surprise me"
	// button last revealed, so pressing it again rotates that one slot.
	let randomKey = $state<string | null>(null);
	let aboutOpen = $state(false); // the About popover

	const anyExtruded = $derived(Object.values(extrude).some(Boolean));

	// Currently-enabled layers, for the always-visible "active layers" chip row —
	// otherwise (esp. after a Surprise-me roll) there's no at-a-glance signal of
	// what's on the map among the 350+ catalog rows.
	const enabledLayers = $derived((manifest?.layers ?? []).filter((l) => enabled[l.key]));

	function optsFor(l: Layer): ExtrudeOpts {
		return {
			extrude: !!extrude[l.key],
			field: extrudeField[l.key] ?? null,
			exaggeration,
			colorField: colorField[l.key] ?? null
		};
	}

	/** Pick (or clear) the field a layer is colored by; recolor live + refresh its
	 *  contextual stats. Empty string clears back to the flat workspace color. */
	function setColorField(l: Layer, field: string) {
		if (field) colorField[l.key] = field;
		else delete colorField[l.key];
		if (map && enabled[l.key]) {
			setLayerColor(map, l, field || null);
			refreshStats(l);
		}
	}

	/** Recompute the histogram / category counts for one colored layer from the
	 *  features currently loaded in its source. */
	function refreshStats(l: Layer) {
		const field = colorField[l.key];
		if (map && field) fieldStats[l.key] = computeFieldStats(map, l, field);
		else delete fieldStats[l.key];
	}

	/** Refresh every colored layer's stats (e.g. after the map settles, when more
	 *  tiles/features have loaded). */
	function refreshAllStats() {
		const byKey = new Map((manifest?.layers ?? []).map((l) => [l.key, l]));
		for (const key of Object.keys(colorField)) {
			const l = byKey.get(key);
			if (l) refreshStats(l);
		}
	}

	/** CSS gradient mirroring the active theme's numeric ramp, for the legend bar. */
	const rampGradient = $derived(
		`linear-gradient(to right, ${activeTheme.graduatedRamp
			.map(([t, c]) => `${c} ${Math.round(t * 100)}%`)
			.join(', ')})`
	);

	const themeLabel = (t: Theme) => (locale === 'en' ? t.label_en : t.label_es);

	// Friendly attribute-field labels (see $lib/fields): show wherever a raw field
	// name would, falling back to the raw name when a field isn't in the glossary.
	const fLabel = (ws: string | undefined, f: string) => fieldLabel(ws, f, locale);
	const fTitle = (ws: string | undefined, f: string) => fieldTitle(ws, f, locale);
	const fHasDef = (ws: string | undefined, f: string) => !!fieldDef(ws, f);
	const fDesc = (ws: string | undefined, f: string) => {
		const d = fieldDef(ws, f);
		return d ? ((locale === 'en' ? d.desc_en : d.desc_es) ?? '') : '';
	};

	/** Compact number formatting for the histogram min/max labels. */
	function fmt(n: number): string {
		const a = Math.abs(n);
		if (a !== 0 && (a >= 100000 || a < 0.01)) return n.toExponential(1);
		return (Math.round(n * 100) / 100).toLocaleString(locale);
	}

	// --- bottom sheet (fly-up) ----------------------------------------------
	// The layer browser lives in a draggable bottom sheet. `sheetH` is its live
	// height in px; it snaps between a peek, a half, and a near-full state.
	const PEEK = 150;
	let innerH = $state(800);
	let innerW = $state(1024);
	let sheetH = $state(PEEK);
	let dragging = $state(false);
	let dragStartY = 0;
	let dragStartH = 0;
	let dragMoved = false;
	const halfH = $derived(Math.round(innerH * 0.5));
	const fullH = $derived(Math.round(innerH * 0.92));
	const expanded = $derived(sheetH > PEEK + 24);

	function snapNearest(h: number): number {
		return [PEEK, halfH, fullH].reduce((a, b) => (Math.abs(b - h) < Math.abs(a - h) ? b : a));
	}
	function onHandleDown(e: PointerEvent) {
		dragging = true;
		dragStartY = e.clientY;
		dragStartH = sheetH;
		dragMoved = false;
		(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
	}
	function onHandleMove(e: PointerEvent) {
		if (!dragging) return;
		const dy = dragStartY - e.clientY;
		if (Math.abs(dy) > 4) dragMoved = true;
		sheetH = Math.min(fullH, Math.max(PEEK, dragStartH + dy));
	}
	function onHandleUp() {
		if (!dragging) return;
		dragging = false;
		// A tap (no real drag) toggles between peek and half.
		sheetH = dragMoved ? snapNearest(sheetH) : sheetH <= PEEK + 8 ? halfH : PEEK;
	}
	function expandForSearch() {
		if (sheetH < halfH) sheetH = fullH;
	}

	function clearSearch() {
		search = '';
		searchEl?.focus();
	}

	type Selected = {
		key: string;
		workspace: string;
		title: string;
		geometryType: string;
		id: string | number | null;
		props: Record<string, unknown>;
		fields: string[]; // all fields the layer is known to have (from the manifest)
		numericFields: string[];
		moreCount: number;
	};
	let selected = $state<Selected | null>(null);
	let copied = $state(false);

	function closeInspector() {
		selected = null;
		if (map) setHighlight(map, null);
	}

	async function copyProps() {
		if (!selected) return;
		await navigator.clipboard.writeText(JSON.stringify(selected.props, null, 2));
		copied = true;
		setTimeout(() => (copied = false), 1500);
	}

	const titleOf = (l: Layer) =>
		locale === 'en' ? l.title_en || l.title_es : l.title_es || l.title_en;
	const abstractOf = (l: Layer) =>
		(locale === 'en' ? l.abstract_en || l.abstract_es : l.abstract_es || l.abstract_en) ?? '';

	/** The identifying tail of a title. Titles read "Area - Category - Sub:
	 *  Specific name"; the part after the last ':' is what actually distinguishes
	 *  the layer (front-truncating loses it). Falls back to the full title. */
	const leafTitle = (l: Layer) => {
		const t = titleOf(l);
		const i = t.lastIndexOf(':');
		return i >= 0 && t.slice(i + 1).trim() ? t.slice(i + 1).trim() : t;
	};

	// Layers grouped by workspace, filtered by the search box.
	const groups = $derived.by(() => {
		if (!manifest) return [] as { workspace: string; layers: Layer[] }[];
		const q = search.trim().toLowerCase();
		const byWs = new Map<string, Layer[]>();
		for (const l of manifest.layers) {
			if (q) {
				const hay = `${l.title_es} ${l.title_en} ${l.typename}`.toLowerCase();
				if (!hay.includes(q)) continue;
			}
			(byWs.get(l.workspace) ?? byWs.set(l.workspace, []).get(l.workspace)!).push(l);
		}
		return [...byWs.entries()]
			.sort((a, b) => a[0].localeCompare(b[0]))
			.map(([workspace, layers]) => ({ workspace, layers }));
	});

	function toggle(l: Layer) {
		if (!map || l.serve === 'empty' || !l.url) return;
		if (enabled[l.key]) {
			removeLayer(map, l.key);
			enabled[l.key] = false;
			extrude[l.key] = false;
			delete colorField[l.key];
			delete fieldStats[l.key];
			if (l.key === randomKey) randomKey = null;
			syncPitch();
		} else {
			addLayer(map, l, optsFor(l));
			fitToLayer(map, l);
			enabled[l.key] = true;
		}
	}

	function clearAll() {
		if (!map) return;
		for (const key of Object.keys(enabled)) {
			if (enabled[key]) removeLayer(map, key);
		}
		enabled = {};
		extrude = {};
		colorField = {};
		fieldStats = {};
		randomKey = null;
		syncPitch();
		closeInspector();
	}

	/** Reveal a random serveable layer and fly to it — a one-tap way to explore the
	 *  350+ layer catalog. Each press drops the previous random pick (only the one
	 *  we added) and rotates to a fresh, not-currently-enabled layer. */
	async function surpriseMe() {
		if (!map || !manifest) return;
		const eligible = manifest.layers.filter(
			(l) => l.serve !== 'empty' && l.url && l.key !== randomKey && !enabled[l.key]
		);
		if (!eligible.length) return;
		// Workspace-balanced: pick a random workspace first, then a layer within it,
		// so a 1-layer workspace gets the same shot as the 105-layer pot_2014 (which
		// would otherwise win ~30% of uniform rolls).
		const byWs = new Map<string, typeof eligible>();
		for (const l of eligible) {
			(byWs.get(l.workspace) ?? byWs.set(l.workspace, []).get(l.workspace)!).push(l);
		}
		const workspaces = [...byWs.keys()];
		const group = byWs.get(workspaces[Math.floor(Math.random() * workspaces.length)])!;
		const pick = group[Math.floor(Math.random() * group.length)];
		// Drop the previous random pick if it's still the one we added.
		if (randomKey && enabled[randomKey]) {
			removeLayer(map, randomKey);
			enabled[randomKey] = false;
			extrude[randomKey] = false;
			delete colorField[randomKey];
			delete fieldStats[randomKey];
		}
		randomKey = pick.key;
		addLayer(map, pick, optsFor(pick));
		enabled[pick.key] = true;
		fitToLayer(map, pick);
		syncPitch();
		// Surface it in the list too: clear any filter, expand the sheet, open the
		// pick's workspace group, and scroll its row into view so it's not lost in
		// the 350+ catalog.
		search = '';
		if (sheetH < halfH) sheetH = halfH;
		await tick();
		const det = document.getElementById(`ws-${pick.workspace}`) as HTMLDetailsElement | null;
		if (det) det.open = true;
		await tick();
		document.getElementById(`row-${pick.key}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
	}

	/** Pitch the camera while anything is extruded, flatten when nothing is. */
	function syncPitch() {
		if (!map) return;
		map.easeTo({ pitch: anyExtruded ? 55 : 0, duration: 600 });
	}

	/** Toggle 3D extrusion for a single enabled layer (changes the fill layer
	 *  type, so the layer is re-added). */
	function toggleExtrude(l: Layer) {
		if (!map || !enabled[l.key]) return;
		const on = !extrude[l.key];
		extrude[l.key] = on;
		if (on && !extrudeField[l.key]) extrudeField[l.key] = defaultExtrudeField(l) ?? '';
		removeLayer(map, l.key);
		addLayer(map, l, optsFor(l));
		syncPitch();
	}

	/** Change which numeric field drives a layer's extrusion (live paint update). */
	function setExtrudeField(l: Layer, field: string) {
		extrudeField[l.key] = field;
		if (map && enabled[l.key] && extrude[l.key]) restyleExtrusion(map, l, field, exaggeration);
	}

	/** Live-apply the global exaggeration slider to every extruded layer. */
	function applyExaggeration() {
		if (!map) return;
		const byKey = new Map((manifest?.layers ?? []).map((l) => [l.key, l]));
		for (const key of Object.keys(extrude)) {
			if (!extrude[key]) continue;
			const l = byKey.get(key);
			if (l) restyleExtrusion(map, l, extrudeField[key] ?? null, exaggeration);
		}
	}

	function toggleDem() {
		if (!map) return;
		dem = !dem;
		if (dem) addDem(map, manifest?.dem, activeTheme.variant, activeTheme.reliefOpacity);
		else removeDem(map);
		// Roads-over-relief read too strong, so tune them while relief is shown.
		tuneBasemap(map, activeTheme, dem && baseVisible);
	}

	/** Show/hide the entire Protomaps basemap (data + relief stay). */
	function toggleBase() {
		if (!map) return;
		baseVisible = !baseVisible;
		setBasemapVisible(map, baseVisible);
		tuneBasemap(map, activeTheme, dem && baseVisible);
	}

	/** Switch the whole map to another theme (basemap flavor, relief variant, data
	 *  ramps, page bg, road/boundary tuning). Light themes switch live; only the
	 *  Dark theme flips the flavor, which restyles the basemap and triggers
	 *  `reapply()`. */
	function pickTheme(t: Theme) {
		if (!map || t.id === activeTheme.id) return;
		activeTheme = t;
		applyTheme(map, t, {
			reapply,
			demOn: dem,
			baseVisible,
			dem: manifest?.dem,
			recolorAll
		});
	}

	/** Rebuild every app-owned layer after a basemap restyle (Dark toggle): relief
	 *  → enabled data layers → highlight → pitch. `applyTheme` re-tunes + recolors
	 *  right after. Reads the already-updated `activeTheme`. */
	function reapply() {
		if (!map) return;
		if (dem) addDem(map, manifest?.dem, activeTheme.variant, activeTheme.reliefOpacity);
		const byKey = new Map((manifest?.layers ?? []).map((l) => [l.key, l]));
		for (const key of Object.keys(enabled)) {
			if (!enabled[key]) continue;
			const l = byKey.get(key);
			if (l) addLayer(map, l, optsFor(l));
		}
		ensureHighlight(map);
		syncPitch();
	}

	/** Re-apply every colored layer's color expression with the new theme ramps. */
	function recolorAll() {
		if (!map) return;
		const byKey = new Map((manifest?.layers ?? []).map((l) => [l.key, l]));
		for (const key of Object.keys(colorField)) {
			const l = byKey.get(key);
			if (l && enabled[l.key]) setLayerColor(map, l, colorField[key] || null);
		}
		refreshAllStats();
	}

	function onMapClick(e: MapMouseEvent) {
		if (!map) return;
		const ids = inspectableLayerIds(map);
		const feats = ids.length ? map.queryRenderedFeatures(e.point, { layers: ids }) : [];
		if (!feats.length) {
			closeInspector();
			return;
		}
		const f = feats[0];
		const key = f.layer.id.split(':')[1];
		const layer = manifest?.layers.find((l) => l.key === key);
		selected = {
			key,
			workspace: layer?.workspace ?? key.split('__')[0],
			title: layer ? titleOf(layer) : key,
			geometryType: f.geometry?.type ?? '',
			id: f.id ?? (f.properties?.id as string | undefined) ?? null,
			props: f.properties ?? {},
			fields: layer?.fields ?? Object.keys(f.properties ?? {}),
			numericFields: layer?.numeric_fields ?? [],
			moreCount: feats.length - 1
		};
		setHighlight(map, f as unknown as GeoJSON.Feature);
		// On phones the inspector covers the screen, so duck the layer sheet out of
		// the way. On desktop the inspector is a separate docked card — leave it.
		if (innerW < 768) sheetH = PEEK;
	}

	function onMapMove(e: MapMouseEvent) {
		if (!map) return;
		const ids = inspectableLayerIds(map);
		const hit = ids.length > 0 && map.queryRenderedFeatures(e.point, { layers: ids }).length > 0;
		map.getCanvas().style.cursor = hit ? 'pointer' : '';
	}

	onMount(() => {
		// Desktop: open the layer sheet expanded by default (it only closes when the
		// user drags it down). Phones keep the compact peek so the map stays visible.
		if (window.innerWidth >= 768) sheetH = Math.round(window.innerHeight * 0.72);
		setThemeRamps(activeTheme); // active data ramps in sync with the default theme
		map = createMap(mapEl);
		if (import.meta.env.DEV) (window as unknown as { __map: MLMap }).__map = map;
		// Tint the base to the default theme once its layers exist (the raw light
		// flavor doesn't match arena's tint).
		map.on('load', () => map && tintBasemap(map, activeTheme));
		map.on('click', onMapClick);
		map.on('mousemove', onMapMove);
		// Once panning/zooming/tiling settles, refresh colored-layer stats so the
		// histograms reflect whatever features are now loaded.
		map.on('idle', refreshAllStats);
		fetch(MANIFEST_URL)
			.then((res) => res.json())
			.then((data) => {
				manifest = data;
			})
			.catch((err) => console.error('failed to load manifest', err));
		return () => map?.remove();
	});
</script>

<svelte:window
	bind:innerHeight={innerH}
	bind:innerWidth={innerW}
	onkeydown={(e) => {
		if (e.key !== 'Escape') return;
		if (infoLayer) infoLayer = null;
		else if (aboutOpen) aboutOpen = false;
	}}
/>

<div class="shell" style="--page-bg:{activeTheme.background}">
	<div bind:this={mapEl} class="map"></div>

	<!-- floating top overlay: title + language -->
	<div class="pointer-events-none absolute inset-x-0 top-0 z-20 flex items-start justify-between gap-2 p-3">
		<button
			type="button"
			class="pointer-events-auto flex items-center gap-4 rounded-xl bg-white/90 px-3 py-1.5 text-left shadow-lg backdrop-blur hover:bg-white"
			title={m.about()}
			aria-label={m.about()}
			onclick={() => (aboutOpen = true)}
		>
			<span class="min-w-0">
				<span class="flex items-center gap-1 text-sm leading-tight font-semibold text-slate-800">
					{m.app_title()}
					<span class="text-[13px] text-slate-400" aria-hidden="true">&#9432;</span>
				</span>
				<span class="block text-[11px] leading-tight text-slate-500">{m.app_subtitle()}</span>
			</span>
			<img src={rfLogo} alt="Recovered Factory" class="h-7 w-auto shrink-0 opacity-90" />
		</button>
		<div
			class="pointer-events-auto flex gap-0.5 rounded-xl bg-white/90 p-1 shadow-lg backdrop-blur"
			aria-label={m.language()}
		>
			{#each locales as loc (loc)}
				<button
					class="rounded-lg px-2 py-1 text-xs font-medium uppercase
					       {loc === locale ? 'bg-slate-800 text-white' : 'text-slate-600 hover:bg-slate-100'}"
					onclick={() => setLocale(loc)}>{loc}</button>
			{/each}
		</div>
	</div>

	<!-- layer browser bottom sheet -->
	<section class="sheet z-10 flex flex-col bg-white/95 shadow-2xl backdrop-blur" class:dragging style="height:{sheetH}px">
		<!-- peek: drag handle + search + one-line desc + RF logo -->
		<button
			type="button"
			class="block w-full shrink-0 cursor-grab touch-none px-4 pt-2"
			aria-label="Resize panel"
			aria-expanded={expanded}
			onpointerdown={onHandleDown}
			onpointermove={onHandleMove}
			onpointerup={onHandleUp}
			onpointercancel={onHandleUp}
		>
			<div class="mx-auto mb-2 h-1.5 w-10 rounded-full bg-slate-300"></div>
		</button>
		<div class="shrink-0 px-4">
			<div class="relative">
				<input
					bind:this={searchEl}
					class="w-full rounded-lg border border-slate-200 py-2 pr-9 pl-3 text-sm focus:border-slate-400 focus:outline-none"
					placeholder={m.search_placeholder()}
					bind:value={search}
					onfocus={expandForSearch}
				/>
				{#if search}
					<button
						type="button"
						class="absolute top-1/2 right-1.5 flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-full text-slate-400 hover:bg-slate-100 hover:text-slate-700"
						title={m.search_clear()}
						aria-label={m.search_clear()}
						onclick={clearSearch}>✕</button>
				{/if}
			</div>
			<p class="mt-2 min-w-0 truncate text-[11px] text-slate-500">
				{m.layers_count({ count: manifest?.generated_layers ?? 0 })}
			</p>
			<!-- active layers: at the top, visible even at peek, so you can see +
			     manage what's on the map without scrolling the full catalog -->
			{#if enabledLayers.length}
				<div class="mt-1.5 mb-1 flex items-start gap-1.5">
					<span class="mt-1 shrink-0 text-[10px] font-medium tracking-wide text-slate-400 uppercase"
						>{m.active_layers()} ({enabledLayers.length})</span
					>
					<!-- wrap to ~two rows, scroll if more; show the layer's identifying
					     leaf name (full title on hover) since titles are front-loaded -->
					<div class="flex max-h-14 min-w-0 flex-1 flex-wrap gap-1 overflow-y-auto pr-1 pb-0.5">
						{#each enabledLayers as l (l.key)}
							<span
								class="flex shrink-0 items-center gap-1 rounded-full bg-slate-100 py-0.5 pr-1 pl-1.5 text-[11px] text-slate-700
								       {l.key === randomKey ? 'ring-1 ring-violet-300' : ''}"
							>
								<span
									class="h-2 w-2 shrink-0 rounded-full"
									style="background:{workspaceColor(l.workspace)}"
								></span>
								<button
									type="button"
									class="max-w-[13rem] truncate"
									title="{titleOf(l)} — {m.zoom_to_layer()}"
									onclick={() => map && fitToLayer(map, l)}>{leafTitle(l)}</button>
								<button
									type="button"
									class="flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-slate-400 hover:bg-slate-200 hover:text-slate-700"
									title={m.remove_layer()}
									aria-label={m.remove_layer()}
									onclick={() => toggle(l)}>✕</button>
							</span>
						{/each}
					</div>
				</div>
			{/if}
		</div>

		<!-- expanded body: controls + grouped layer list -->
		<div class="flex min-h-0 flex-1 flex-col">
			<div class="shrink-0 border-t border-black/5 px-4 py-2">
				<div class="flex items-center gap-2">
					<button
						class="rounded-lg border px-2.5 py-1 text-xs font-medium
						       {dem
							? 'border-emerald-600 bg-emerald-600 text-white'
							: 'border-slate-200 text-slate-600 hover:bg-slate-50'}"
						title={m.dem_hint()}
						aria-pressed={dem}
						onclick={toggleDem}>{m.dem()}</button>
					<button
						class="rounded-lg border px-2.5 py-1 text-xs font-medium
						       {baseVisible
							? 'border-slate-600 bg-slate-600 text-white'
							: 'border-slate-200 text-slate-600 hover:bg-slate-50'}"
						title={m.base_hint()}
						aria-pressed={baseVisible}
						onclick={toggleBase}>{m.base()}</button>
					<button
						class="rounded-lg border border-violet-300 px-2.5 py-1 text-xs font-medium text-violet-700 hover:bg-violet-50"
						title={m.surprise_hint()}
						onclick={surpriseMe}>{randomKey ? `↻ ${m.surprise_again()}` : `🎲 ${m.surprise()}`}</button>
					<button
						class="ml-auto text-xs text-slate-500 underline hover:text-slate-700"
						onclick={clearAll}>{m.clear_all()}</button>
				</div>
				{#if anyExtruded}
					<label class="mt-2 flex items-center gap-2 text-xs text-slate-500">
						<span class="shrink-0">{m.exaggeration()}</span>
						<input
							type="range"
							class="min-w-0 flex-1 accent-amber-500"
							min="1"
							max="12"
							step="0.5"
							bind:value={exaggeration}
							oninput={applyExaggeration}
							title={m.exaggeration_hint()}
						/>
						<span class="w-7 shrink-0 text-right tabular-nums text-slate-600">{exaggeration}×</span>
					</label>
				{/if}
			</div>

			<div class="min-h-0 flex-1 overflow-y-auto px-2 pb-2 text-sm">
				{#if !manifest}
					<p class="px-2 py-4 text-slate-400">{m.loading()}</p>
				{:else if groups.length === 0}
					<p class="px-2 py-4 text-slate-400">{m.empty_results()}</p>
				{:else}
					{#each groups as group (group.workspace)}
						<details id="ws-{group.workspace}" class="mb-1" open={!!search}>
							<summary
								class="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 hover:bg-slate-50"
							>
								<span
									class="inline-block h-2.5 w-2.5 shrink-0 rounded-full"
									style="background:{workspaceColor(group.workspace)}"
								></span>
								<span class="font-medium text-slate-700">{group.workspace}</span>
								<span class="ml-auto text-xs text-slate-400">{group.layers.length}</span>
							</summary>
							<ul class="mt-0.5 mb-1 ml-4 border-l border-slate-100 pl-2">
								{#each group.layers as l (l.key)}
									<li id="row-{l.key}">
										<div class="flex items-start gap-1">
											<label
												class="flex min-w-0 flex-1 cursor-pointer items-start gap-2 rounded px-1.5 py-1 hover:bg-slate-50
												       {l.serve === 'empty' ? 'opacity-40' : ''}"
											>
												<input
													type="checkbox"
													class="mt-0.5"
													checked={!!enabled[l.key]}
													disabled={l.serve === 'empty'}
													onchange={() => toggle(l)}
												/>
												<span class="min-w-0">
													<span class="block leading-snug text-slate-700">{titleOf(l)}</span>
													<span class="block text-[11px] text-slate-400">
														{#if l.serve === 'empty'}
															{m.no_geometry()}
														{:else}
															{m.feature_count({ count: l.feature_count })} · {l.serve}
														{/if}
													</span>
												</span>
											</label>
											<button
												class="mt-1 shrink-0 rounded px-1.5 py-0.5 text-xs text-slate-400 hover:bg-slate-100 hover:text-slate-700"
												title={m.details()}
												aria-label={m.details()}
												aria-haspopup="dialog"
												onclick={() => (infoLayer = l)}>&#9432;</button>
										</div>
										{#if enabled[l.key] && extrudableFields(l).length}
											<div class="mt-0.5 mb-1 ml-7 flex items-center gap-1.5 pr-2">
												<button
													class="rounded border px-1.5 py-0.5 text-[11px] font-medium
													       {extrude[l.key]
														? 'border-amber-500 bg-amber-500 text-white'
														: 'border-slate-200 text-slate-500 hover:bg-slate-50'}"
													title={m.extrude_hint()}
													aria-pressed={!!extrude[l.key]}
													onclick={() => toggleExtrude(l)}>{m.extrude_3d()}</button>
												{#if extrude[l.key] && extrudableFields(l).length > 1}
													<select
														class="min-w-0 flex-1 rounded border border-slate-200 bg-white px-1 py-0.5 text-[11px] text-slate-600"
														title={m.extrude_field()}
														value={extrudeField[l.key] ?? defaultExtrudeField(l) ?? ''}
														onchange={(e) => setExtrudeField(l, e.currentTarget.value)}
													>
														{#each extrudableFields(l) as f (f)}
															<option value={f}>{fLabel(l.workspace, f)}</option>
														{/each}
													</select>
												{/if}
											</div>
										{/if}
										{#if enabled[l.key] && hasColorableFields(l)}
											{@const cf = colorableFields(l)}
											<div class="mt-0.5 mb-1 ml-7 pr-2">
												<div class="flex items-center gap-1.5">
													<span class="shrink-0 text-[11px] text-slate-500">{m.color_by()}</span>
													<select
														class="min-w-0 flex-1 rounded border border-slate-200 bg-white px-1 py-0.5 text-[11px] text-slate-600"
														title={m.color_by_hint()}
														value={colorField[l.key] ?? ''}
														onchange={(e) => setColorField(l, e.currentTarget.value)}
													>
														<option value="">{m.color_flat()}</option>
														{#if cf.numeric.length}
															<optgroup label={m.color_numeric()}>
																{#each cf.numeric as f (f)}<option value={f}>{fLabel(l.workspace, f)}</option>{/each}
															</optgroup>
														{/if}
														{#if cf.categorical.length}
															<optgroup label={m.color_categories()}>
																{#each cf.categorical as f (f)}<option value={f}>{fLabel(l.workspace, f)}</option>{/each}
															</optgroup>
														{/if}
													</select>
												</div>
												{#if colorField[l.key]}
													{@const s = fieldStats[l.key]}
													{#if s?.kind === 'numeric'}
														{@const peak = Math.max(1, ...s.bins)}
														<div class="mt-1.5 flex h-8 items-end gap-px" aria-hidden="true">
															{#each s.bins as c, i (i)}
																<div
																	class="min-w-0 flex-1 rounded-sm"
																	style="height:{Math.max(2, Math.round((c / peak) * 100))}%;background:{activeTheme.graduatedRamp[
																		Math.min(
																			activeTheme.graduatedRamp.length - 1,
																			Math.floor((i / s.bins.length) * activeTheme.graduatedRamp.length)
																		)
																	][1]}"
																></div>
															{/each}
														</div>
														<div class="mt-1 h-1.5 rounded" style="background:{rampGradient}"></div>
														<div class="mt-0.5 flex justify-between text-[10px] tabular-nums text-slate-400">
															<span>{fmt(s.min)}</span>
															<span>n={s.total}{#if l.serve === 'pmtiles'} ({m.sample_note()}){/if}</span>
															<span>{fmt(s.max)}</span>
														</div>
													{:else if s?.kind === 'categorical'}
														{@const peak = Math.max(1, ...s.items.map((it) => it.count))}
														<ul class="mt-1.5 space-y-0.5">
															{#each s.items.slice(0, 8) as it (it.value)}
																<li class="flex items-center gap-1.5 text-[10px] text-slate-500">
																	<span
																		class="inline-block h-2.5 w-2.5 shrink-0 rounded-sm"
																		style="background:{it.color}"
																	></span>
																	<span class="min-w-0 flex-1 truncate" title={it.value}>{it.value}</span>
																	<span
																		class="h-1.5 shrink-0 rounded-sm bg-slate-300"
																		style="width:{Math.round((it.count / peak) * 36) + 2}px"
																	></span>
																	<span class="w-8 shrink-0 text-right tabular-nums text-slate-400">{it.count}</span>
																</li>
															{/each}
															{#if s.items.length > 8}
																<li class="text-[10px] text-slate-400">+{s.items.length - 8} …</li>
															{/if}
														</ul>
													{/if}
												{/if}
											</div>
										{/if}
									</li>
								{/each}
							</ul>
						</details>
					{/each}
				{/if}
			</div>

			<!-- bottom bar: theme picker (pinned below the list) -->
			<div class="shrink-0 border-t border-black/5 px-4 py-2">
				<div class="flex flex-wrap items-center gap-1">
					<span class="mr-0.5 shrink-0 text-[10px] font-medium tracking-wide text-slate-400 uppercase"
						title={m.theme_hint()}>{m.theme()}</span
					>
					{#each THEMES as t (t.id)}
						<button
							class="rounded-full border px-2 py-0.5 text-[11px]
							       {activeTheme.id === t.id
								? 'border-emerald-600 bg-emerald-600 text-white'
								: 'border-slate-200 text-slate-600 hover:bg-slate-50'}"
							title={m.theme_hint()}
							aria-pressed={activeTheme.id === t.id}
							onclick={() => pickTheme(t)}>{themeLabel(t)}</button>
					{/each}
				</div>
			</div>

			<footer
				class="shrink-0 border-t border-black/5 px-4 py-2 text-[11px] text-slate-400"
				style="padding-bottom: calc(0.5rem + env(safe-area-inset-bottom, 0px))"
			>
				{m.attribution()}
			</footer>
		</div>
	</section>

	<!-- feature inspector bottom sheet -->
	{#if selected}
		{@const fieldKeys = [...new Set([...selected.fields, ...Object.keys(selected.props)])]}
		<section
			class="inspector z-30 flex flex-col bg-white/95 shadow-2xl backdrop-blur"
			transition:fly={{ y: 320, duration: 250 }}
		>
			<header class="flex items-start gap-2 border-b border-black/10 px-4 pt-3 pb-3">
				<span
					class="mt-1 inline-block h-2.5 w-2.5 shrink-0 rounded-full"
					style="background:{workspaceColor(selected.workspace)}"
				></span>
				<div class="min-w-0 flex-1">
					<h2 class="leading-tight font-semibold text-slate-800">{selected.title}</h2>
					<p class="truncate text-xs text-slate-500">
						{selected.workspace} · {selected.geometryType}
						{#if selected.id !== null}· {m.feature_id()} {selected.id}{/if}
					</p>
				</div>
				<button
					class="shrink-0 rounded px-1.5 py-0.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
					title={m.close()}
					aria-label={m.close()}
					onclick={closeInspector}>&times;</button>
			</header>

			<div class="min-h-0 flex-1 overflow-y-auto px-4 py-3">
				{#if selected.moreCount > 0}
					<p class="mb-2 text-[11px] text-slate-400">{m.more_here({ count: selected.moreCount })}</p>
				{/if}
				<h3 class="mb-1 text-xs font-medium tracking-wide text-slate-500 uppercase">
					{m.attributes()} <span class="text-slate-400 normal-case">({fieldKeys.length})</span>
				</h3>
				<dl class="divide-y divide-slate-100">
					{#each fieldKeys as k (k)}
						{@const v = selected.props[k]}
						<div class="grid grid-cols-[40%_60%] gap-2 py-1 text-sm">
							<dt
								class="flex min-w-0 items-center gap-1 text-[11px] text-slate-500"
								title={fTitle(selected.workspace, k)}
							>
								<span class="truncate">{fLabel(selected.workspace, k)}</span>
								{#if selected.numericFields.includes(k)}
									<span
										class="shrink-0 rounded bg-amber-100 px-1 text-[9px] font-semibold text-amber-700"
										title={m.numeric_field()}>#</span>
								{/if}
							</dt>
							<dd class="break-words {v === null || v === undefined || v === '' ? 'text-slate-300' : 'text-slate-800'}">
								{v === null || v === undefined || v === '' ? '—' : String(v)}
							</dd>
						</div>
					{/each}
				</dl>
			</div>

			<footer class="border-t border-black/10 px-4 py-2">
				<button
					class="rounded bg-slate-100 px-2 py-1 text-xs text-slate-600 hover:bg-slate-200"
					onclick={copyProps}>{copied ? m.copied() : m.copy_json()}</button>
			</footer>
		</section>
	{/if}

	<!-- About popover -->
	{#if aboutOpen}
		<div
			class="absolute inset-0 z-40 flex items-center justify-center p-4"
			transition:fade={{ duration: 150 }}
		>
			<button
				type="button"
				class="absolute inset-0 cursor-default bg-black/40"
				aria-label={m.close()}
				onclick={() => (aboutOpen = false)}
			></button>
			<div
				class="relative w-full max-w-sm rounded-2xl bg-white p-5 shadow-2xl"
				role="dialog"
				aria-modal="true"
				aria-label={m.about()}
			>
				<div class="flex items-start gap-3">
					<img src={rfLogo} alt="Recovered Factory" class="h-10 w-auto shrink-0" />
					<div class="min-w-0 flex-1">
						<h2 class="leading-tight font-semibold text-slate-800">{m.app_title()}</h2>
						<p class="text-xs text-slate-500">{m.app_subtitle()}</p>
					</div>
					<button
						class="shrink-0 rounded px-1.5 py-0.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
						title={m.close()}
						aria-label={m.close()}
						onclick={() => (aboutOpen = false)}>&times;</button>
				</div>
				<!-- about_body is our own static i18n string (not user input), so {@html}
				     is safe and lets the copy carry <a> links + line breaks. -->
				<p class="about-prose mt-3 text-sm leading-relaxed whitespace-pre-line text-slate-600">
					{@html m.about_body()}
				</p>
				<p class="mt-3 text-[11px] text-slate-400">{m.attribution()}</p>
			</div>
		</div>
	{/if}

	<!-- Layer details popup (locks the map until dismissed) -->
	{#if infoLayer}
		<div
			class="absolute inset-0 z-40 flex items-center justify-center p-4"
			transition:fade={{ duration: 150 }}
		>
			<button
				type="button"
				class="absolute inset-0 cursor-default bg-black/40"
				aria-label={m.close()}
				onclick={() => (infoLayer = null)}
			></button>
			<div
				class="relative flex max-h-[86dvh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl"
				role="dialog"
				aria-modal="true"
				aria-label={m.details()}
			>
				<!-- page header -->
				<div class="flex items-start gap-2 border-b border-black/10 px-6 pt-5 pb-4">
					<span
						class="mt-1.5 inline-block h-2.5 w-2.5 shrink-0 rounded-full"
						style="background:{workspaceColor(infoLayer.workspace)}"
					></span>
					<div class="min-w-0 flex-1">
						<h2 class="text-lg leading-tight font-semibold text-slate-800">{titleOf(infoLayer)}</h2>
						<p class="mt-0.5 text-xs text-slate-500">
							{infoLayer.workspace}{#if infoLayer.geometry_type}
								· {infoLayer.geometry_type}{/if}{#if infoLayer.serve !== 'empty'}
								· {m.feature_count({ count: infoLayer.feature_count })}{/if}
						</p>
					</div>
					<button
						class="shrink-0 rounded px-1.5 py-0.5 text-xl leading-none text-slate-400 hover:bg-slate-100 hover:text-slate-700"
						title={m.close()}
						aria-label={m.close()}
						onclick={() => (infoLayer = null)}>&times;</button>
				</div>

				<!-- page body -->
				<div class="min-h-0 flex-1 overflow-y-auto px-6 py-4">
					<p class="text-sm leading-relaxed text-slate-600">
						{abstractOf(infoLayer) || m.no_description()}
					</p>

					{#if infoLayer.fields?.length}
						<h3 class="mt-5 mb-1 text-xs font-medium tracking-wide text-slate-500 uppercase">
							{m.attributes()}
							<span class="text-slate-400 normal-case">({infoLayer.fields.length})</span>
						</h3>
						<dl class="divide-y divide-slate-100">
							{#each infoLayer.fields as f (f)}
								{@const hasDef = fHasDef(infoLayer.workspace, f)}
								{@const desc = fDesc(infoLayer.workspace, f)}
								<div class="py-2">
									<dt class="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
										<span class="font-medium text-slate-800">{fLabel(infoLayer.workspace, f)}</span>
										{#if hasDef}
											<code class="font-mono text-[10px] text-slate-400">{f}</code>
										{/if}
										{#if infoLayer.numeric_fields?.includes(f)}
											<span
												class="rounded bg-amber-100 px-1 text-[9px] font-semibold text-amber-700"
												title={m.numeric_field()}>#</span>
										{/if}
									</dt>
									{#if desc}
										<dd class="mt-0.5 text-[12px] leading-snug text-slate-500">{desc}</dd>
									{/if}
								</div>
							{/each}
						</dl>
					{/if}
				</div>
			</div>
		</div>
	{/if}
</div>

<style>
	/* Explicit, framework-independent full-viewport sizing — utility classes were
	   collapsing the map container to 0 height. */
	:global(html),
	:global(body) {
		margin: 0;
		height: 100%;
	}
	/* Links inside the About popover body (rendered from the i18n string via
	   {@html}, so they can't carry utility classes). */
	:global(.about-prose a) {
		color: #047857; /* emerald-700 */
		text-decoration: underline;
		text-underline-offset: 2px;
	}
	:global(.about-prose a:hover) {
		color: #065f46; /* emerald-800 */
	}

	.shell {
		position: fixed;
		inset: 0;
		overflow: hidden;
		/* Theme backdrop — shows behind a hidden basemap and around the clipped
		   relief edge so the map reads as one coherent surface. */
		background: var(--page-bg, #efe9dd);
	}
	.map {
		position: absolute;
		inset: 0;
		background: var(--page-bg, #efe9dd);
	}

	/* Bottom sheets (mobile-first). Full-width fly-up on phones; a docked,
	   rounded card on ≥ md. */
	.sheet {
		position: absolute;
		bottom: 0;
		left: 0;
		right: 0;
		/* dvh (not vh) so the sheet respects the *visible* viewport — vh includes
		   the area behind the mobile address bar, which clipped the list bottom. */
		max-height: 92dvh;
		border-top-left-radius: 1rem;
		border-top-right-radius: 1rem;
		overflow: hidden;
		transition: height 0.28s cubic-bezier(0.4, 0, 0.2, 1);
	}
	.sheet.dragging {
		transition: none;
	}
	.inspector {
		position: absolute;
		bottom: 0;
		left: 0;
		right: 0;
		max-height: 62dvh;
		border-top-left-radius: 1rem;
		border-top-right-radius: 1rem;
		overflow: hidden;
	}
	@media (min-width: 768px) {
		.sheet {
			left: 1rem;
			right: auto;
			bottom: 1rem;
			width: 380px;
			border-radius: 1rem;
		}
		.inspector {
			left: auto;
			right: 1rem;
			bottom: 1rem;
			width: 380px;
			max-height: 70dvh;
			border-radius: 1rem;
		}
	}
</style>
