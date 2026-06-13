<script lang="ts">
	// Thin shell: owns the MapLibre lifecycle + URL state sync, and composes
	// the UI surfaces. All shared state + actions live in $lib/state/app.svelte.
	import { onMount } from 'svelte';
	import 'maplibre-gl/dist/maplibre-gl.css';
	import type { Map as MLMap, MapMouseEvent } from 'maplibre-gl';
	import { MANIFEST_URL } from '$lib/config';
	import { createMap, tintBasemap, addCaliMask, setThemeRamps, pickFeatures } from '$lib/map';
	import { m } from '$lib/paraglide/messages';
	import { app } from '$lib/state/app.svelte';
	import { parseHash, restoreState, serializeState, scheduleUrlSync } from '$lib/state/url';
	import TopBar from '$lib/components/TopBar.svelte';
	import Dock from '$lib/components/Dock.svelte';
	import LayerBrowser from '$lib/components/LayerBrowser.svelte';
	import Inspector from '$lib/components/Inspector.svelte';
	import AboutSheet from '$lib/components/AboutSheet.svelte';
	import LayerInfoModal from '$lib/components/LayerInfoModal.svelte';

	let mapEl: HTMLDivElement;
	// URL writes start only after the initial hash has been restored, so the
	// boot sequence can't clobber a shared link.
	let booted = $state(false);

	function onMapClick(e: MapMouseEvent) {
		const map = app.map;
		if (!map) return;
		const feats = pickFeatures(map, e.point);
		if (!feats.length) {
			app.closeInspector();
			return;
		}
		const f = feats[0];
		const key = f.layer.id.split(':')[1];
		const layer = app.layer(key) ?? null;
		app.select(
			{
				key,
				layer,
				workspace: layer?.workspace ?? key.split('__')[0],
				geometryType: f.geometry?.type ?? '',
				id: f.id ?? (f.properties?.id as string | undefined) ?? null,
				props: f.properties ?? {},
				moreCount: feats.length - 1
			},
			f as unknown as GeoJSON.Feature
		);
	}

	onMount(() => {
		setThemeRamps(app.theme);
		// A failed map init (e.g. WebGL unavailable) shouldn't take the catalog
		// down with it — the browser/list UI still works without the canvas.
		let map: MLMap | undefined;
		try {
			map = createMap(mapEl);
		} catch (err) {
			console.error('map init failed (WebGL unavailable?)', err);
		}
		app.map = map;
		if (import.meta.env.DEV) (window as unknown as { __map: MLMap | undefined }).__map = map;

		map?.on('click', onMapClick);
		map?.on('mousemove', (e) => {
			map.getCanvas().style.cursor = pickFeatures(map, e.point).length ? 'pointer' : '';
		});
		// Once panning/zooming/tiling settles, refresh colored-layer stats so the
		// legends reflect whatever features are now loaded.
		map?.on('idle', () => app.refreshAllStats());
		map?.on('moveend', () => {
			if (booted) scheduleUrlSync(serializeState(map));
		});

		const mapReady = new Promise<void>((resolve) =>
			map ? map.on('load', () => resolve()) : resolve()
		);
		const manifestReady = fetch(MANIFEST_URL)
			.then((res) => res.json())
			.then((data) => {
				app.manifest = data;
			})
			.catch((err) => console.error('failed to load manifest', err));

		Promise.all([mapReady, manifestReady]).then(() => {
			const st = parseHash(location.hash);
			// The mask defaults ON; honor a shared link that turned it off before
			// the first add (toggle semantics would otherwise double-flip).
			if (st.mask === false) app.maskOn = false;
			if (map) {
				tintBasemap(map, app.theme);
				if (app.maskOn) addCaliMask(map, app.theme.background);
			}
			restoreState(st);
			booted = true;
		});

		return () => map?.remove();
	});

	// Any state change (layers, styling, theme, modes) refreshes the share URL.
	$effect(() => {
		const hash = serializeState(app.map);
		if (booted) scheduleUrlSync(hash);
	});
</script>

<svelte:head>
	<title>Mapas Cali — {m.brand_tagline()}</title>
	<meta name="description" content={m.about_riff()} />
</svelte:head>

<svelte:window
	onkeydown={(e) => {
		if (e.key !== 'Escape') return;
		if (app.infoLayer) app.infoLayer = null;
		else if (app.aboutOpen) app.aboutOpen = false;
		else if (app.browserOpen) app.browserOpen = false;
		else if (app.selected) app.closeInspector();
	}}
/>

<div class="shell" style="--page-bg:{app.theme.background}">
	<div bind:this={mapEl} class="map"></div>

	<TopBar />
	<Dock />
	<Inspector />
	<LayerBrowser />
	<AboutSheet />
	<LayerInfoModal />
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
		/* Theme backdrop — shows behind a hidden basemap and around the clipped
		   relief edge so the map reads as one coherent surface. */
		background: var(--page-bg, #efe9dd);
	}
	.map {
		position: absolute;
		inset: 0;
		background: var(--page-bg, #efe9dd);
	}
</style>
