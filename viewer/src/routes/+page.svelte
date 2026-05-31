<script lang="ts">
	import { onMount } from 'svelte';
	import { fly } from 'svelte/transition';
	import 'maplibre-gl/dist/maplibre-gl.css';
	import type { Map as MLMap, MapMouseEvent } from 'maplibre-gl';
	import { MANIFEST_URL, type Layer, type Manifest } from '$lib/config';
	import {
		createMap,
		addLayer,
		removeLayer,
		fitToLayer,
		workspaceColor,
		setHighlight,
		inspectableLayerIds,
		addDem,
		removeDem,
		setDemVariant,
		extrudableFields,
		defaultExtrudeField,
		restyleExtrusion,
		type ExtrudeOpts
	} from '$lib/map';
	import { m } from '$lib/paraglide/messages';
	import { getLocale, setLocale, locales } from '$lib/paraglide/runtime';
	import rfLogo from '$lib/assets/recovered-factory.png';

	const locale = getLocale();

	let mapEl: HTMLDivElement;
	let map: MLMap | undefined;
	let manifest = $state<Manifest | null>(null);
	let enabled = $state<Record<string, boolean>>({});
	let info = $state<Record<string, boolean>>({});
	let search = $state('');
	let dem = $state(false);
	let demVariant = $state(''); // chosen relief color ramp id
	// Per-layer 3D: which enabled layers extrude, and by which numeric field.
	let extrude = $state<Record<string, boolean>>({});
	let extrudeField = $state<Record<string, string>>({});
	// Global vertical exaggeration applied to every extruded layer's height.
	let exaggeration = $state(3);

	const anyExtruded = $derived(Object.values(extrude).some(Boolean));

	function optsFor(l: Layer): ExtrudeOpts {
		return { extrude: !!extrude[l.key], field: extrudeField[l.key] ?? null, exaggeration };
	}

	// --- bottom sheet (fly-up) ----------------------------------------------
	// The layer browser lives in a draggable bottom sheet. `sheetH` is its live
	// height in px; it snaps between a peek, a half, and a near-full state.
	const PEEK = 150;
	let innerH = $state(800);
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
		syncPitch();
		closeInspector();
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
		if (dem) addDem(map, manifest?.dem, demVariant);
		else removeDem(map);
	}

	/** Switch the relief color ramp live (no re-add). */
	function pickDemVariant(id: string) {
		demVariant = id;
		if (map && dem && manifest?.dem) setDemVariant(map, manifest.dem, id);
	}

	const demLabel = (v: { label_es: string; label_en: string }) =>
		locale === 'en' ? v.label_en : v.label_es;

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
		sheetH = PEEK; // get the layer sheet out of the way for the inspector
	}

	function onMapMove(e: MapMouseEvent) {
		if (!map) return;
		const ids = inspectableLayerIds(map);
		const hit = ids.length > 0 && map.queryRenderedFeatures(e.point, { layers: ids }).length > 0;
		map.getCanvas().style.cursor = hit ? 'pointer' : '';
	}

	onMount(() => {
		map = createMap(mapEl);
		if (import.meta.env.DEV) (window as unknown as { __map: MLMap }).__map = map;
		map.on('click', onMapClick);
		map.on('mousemove', onMapMove);
		fetch(MANIFEST_URL)
			.then((res) => res.json())
			.then((data) => {
				manifest = data;
				demVariant = data.dem?.default ?? data.dem?.variants?.[0]?.id ?? '';
			})
			.catch((err) => console.error('failed to load manifest', err));
		return () => map?.remove();
	});
</script>

<svelte:window bind:innerHeight={innerH} />

<div class="shell">
	<div bind:this={mapEl} class="map"></div>

	<!-- floating top overlay: title + language -->
	<div class="pointer-events-none absolute inset-x-0 top-0 z-20 flex items-start justify-between gap-2 p-3">
		<div class="pointer-events-auto rounded-xl bg-white/90 px-3 py-1.5 shadow-lg backdrop-blur">
			<h1 class="text-sm leading-tight font-semibold text-slate-800">{m.app_title()}</h1>
			<p class="text-[11px] leading-tight text-slate-500">{m.app_subtitle()}</p>
		</div>
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
			<input
				class="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-slate-400 focus:outline-none"
				placeholder={m.search_placeholder()}
				bind:value={search}
				onfocus={expandForSearch}
			/>
			<div class="mt-2 mb-2 flex items-center justify-between gap-3">
				<p class="min-w-0 truncate text-[11px] text-slate-500">
					{m.layers_count({ count: manifest?.generated_layers ?? 0 })} · {m.app_subtitle()}
				</p>
				<img src={rfLogo} alt="Recovered Factory" class="h-4 w-auto shrink-0 opacity-80" />
			</div>
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
						class="ml-auto text-xs text-slate-500 underline hover:text-slate-700"
						onclick={clearAll}>{m.clear_all()}</button>
				</div>
				{#if dem && manifest?.dem?.variants?.length}
					<div class="mt-2 flex flex-wrap items-center gap-1">
						{#each manifest.dem.variants as v (v.id)}
							<button
								class="rounded-full border px-2 py-0.5 text-[11px]
								       {demVariant === v.id
									? 'border-emerald-600 bg-emerald-600 text-white'
									: 'border-slate-200 text-slate-600 hover:bg-slate-50'}"
								onclick={() => pickDemVariant(v.id)}>{demLabel(v)}</button>
						{/each}
					</div>
				{/if}
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
						<details class="mb-1" open={!!search}>
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
									<li>
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
											{#if abstractOf(l)}
												<button
													class="mt-1 shrink-0 rounded px-1.5 py-0.5 text-xs text-slate-400 hover:bg-slate-100 hover:text-slate-700
													       {info[l.key] ? 'bg-slate-100 text-slate-700' : ''}"
													title={m.details()}
													aria-label={m.details()}
													aria-expanded={!!info[l.key]}
													onclick={() => (info[l.key] = !info[l.key])}>&#9432;</button>
											{/if}
										</div>
										{#if info[l.key]}
											<p class="mt-0.5 mb-1 ml-7 pr-2 text-[11px] leading-snug text-slate-500">
												{abstractOf(l) || m.no_description()}
											</p>
										{/if}
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
															<option value={f}>{f}</option>
														{/each}
													</select>
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

			<footer class="shrink-0 border-t border-black/5 px-4 py-2 text-[11px] text-slate-400">
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
							<dt class="flex min-w-0 items-center gap-1 font-mono text-[11px] text-slate-500" title={k}>
								<span class="truncate">{k}</span>
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
</div>

<style>
	/* Explicit, framework-independent full-viewport sizing — utility classes were
	   collapsing the map container to 0 height. */
	:global(html),
	:global(body) {
		margin: 0;
		height: 100%;
	}
	.shell {
		position: fixed;
		inset: 0;
		overflow: hidden;
	}
	.map {
		position: absolute;
		inset: 0;
	}

	/* Bottom sheets (mobile-first). Full-width fly-up on phones; a docked,
	   rounded card on ≥ md. */
	.sheet {
		position: absolute;
		bottom: 0;
		left: 0;
		right: 0;
		max-height: 92vh;
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
		max-height: 62vh;
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
			max-height: 70vh;
			border-radius: 1rem;
		}
	}
</style>
