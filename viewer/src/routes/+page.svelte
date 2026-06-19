<script lang="ts">
	// Thin shell: owns the MapLibre lifecycle + URL state sync, and composes
	// the UI surfaces. All shared state + actions live in $lib/state/app.svelte.
	import { onMount } from 'svelte';
	import 'maplibre-gl/dist/maplibre-gl.css';
	import type { Map as MLMap, MapMouseEvent } from 'maplibre-gl';
	import { MANIFEST_URL } from '$lib/config';
	import { createMap, tintBasemap, setThemeRamps, pickFeatures, setUiPadding } from '$lib/map';
	import { m } from '$lib/paraglide/messages';
	import { app } from '$lib/state/app.svelte';
	import { parseHash, restoreState, serializeState, scheduleUrlSync } from '$lib/state/url';
	import { setAnalyticsEnabled } from '$lib/analytics';
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
	// ...and the hash stays empty until the user's FIRST real interaction (a manual
	// map pan/zoom, or any layer/style/theme change). A fresh visit keeps a clean
	// `/` instead of immediately growing a `#v=…` nobody asked to share. Every write
	// then uses history.replaceState (see scheduleUrlSync), so it never piles up
	// back-button entries. `baseline` is the restored/initial state we must NOT write
	// back; `interacted` latches true on the first genuine change. Plain (non-$state)
	// so the write $effect doesn't subscribe to them.
	let interacted = false;
	let baseline: string | null = null;

	// Viewport size → map padding so framing + the pan leash clear the dock (a left
	// panel on desktop, a bottom sheet on phones). Without this the city frames
	// half-under the dock and the maxBounds leash can pin it there.
	let innerW = $state(typeof window !== 'undefined' ? window.innerWidth : 1024);
	let innerH = $state(typeof window !== 'undefined' ? window.innerHeight : 800);
	const dockPadding = (w: number, h: number) =>
		w >= 768
			? { top: 24, right: 24, bottom: 24, left: 432 } // left dock ≈ 400 + 16 margin + gap
			: { top: 64, right: 16, bottom: Math.min(Math.round(h * 0.42), 320), left: 16 }; // bottom sheet

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
		// Reserve the dock footprint before the first fit (incl. shared-link restore).
		if (map) setUiPadding(map, dockPadding(innerW, innerH));

		map?.on('click', onMapClick);
		map?.on('mousemove', (e) => {
			map.getCanvas().style.cursor = pickFeatures(map, e.point).length ? 'pointer' : '';
		});
		// Once panning/zooming/tiling settles, refresh colored-layer stats so the
		// legends reflect whatever features are now loaded.
		map?.on('idle', () => app.refreshAllStats());
		map?.on('moveend', (e) => {
			if (!booted) return;
			// originalEvent present = a user gesture (drag/zoom/wheel); a programmatic
			// fly/jump has none, so the initial framing can't dirty a clean URL.
			if (e.originalEvent) interacted = true;
			if (interacted) scheduleUrlSync(serializeState(map));
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
			if (map) tintBasemap(map, app.theme);
			// Replaying a shared link drives the same enable/theme/dem methods a user
			// would — suppress analytics across the (synchronous) restore so it doesn't
			// log a burst of fake actions (and so `first-action` stays the user's first).
			setAnalyticsEnabled(false);
			restoreState(st);
			setAnalyticsEnabled(true);
			booted = true;
		});

		return () => map?.remove();
	});

	// Any state change (layers, styling, theme, modes) refreshes the share URL.
	$effect(() => {
		const hash = serializeState(app.map);
		if (!booted) return;
		// First post-boot run records the restored/initial state without writing it,
		// so a fresh visit stays at `/` and a shared link isn't rewritten.
		if (baseline === null) {
			baseline = hash;
			return;
		}
		if (hash !== baseline) interacted = true;
		if (interacted) scheduleUrlSync(hash);
	});

	// Re-apply dock-aware padding on viewport resize (and once the map is ready).
	$effect(() => {
		void booted;
		if (app.map) setUiPadding(app.map, dockPadding(innerW, innerH));
	});
</script>

<svelte:head>
	<!-- Live, localized tab title. The canonical SEO/OG description lives in
	     app.html (crawler-visible; this SPA isn't prerendered). -->
	<title>Mapas Cali — {m.brand_tagline()}</title>
</svelte:head>

<svelte:window
	bind:innerWidth={innerW}
	bind:innerHeight={innerH}
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
