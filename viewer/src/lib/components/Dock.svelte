<script lang="ts">
	// The main control surface. On phones it's a draggable bottom sheet that
	// snaps between three discrete stops (peek / half / full); on ≥md it's a
	// docked left panel (auto height). Empty state = the curated front door
	// (featured strip on phones, a grid on desktop); otherwise the active-layer
	// manager. The catalog button + map settings stay pinned below the scrolling
	// list so they never require a scroll to reach on desktop.
	import { m } from '$lib/paraglide/messages';
	import { app } from '$lib/state/app.svelte';
	import ActiveLayerCard from './ActiveLayerCard.svelte';
	import FeaturedStrip from './FeaturedStrip.svelte';
	import MapSettings from './MapSettings.svelte';

	let innerH = $state(typeof window !== 'undefined' ? window.innerHeight : 800);
	let innerW = $state(typeof window !== 'undefined' ? window.innerWidth : 1024);
	const isDesktop = $derived(innerW >= 768);

	// Discrete snap stops drive the sheet height; `dragH` holds the live pixel
	// height only while a drag is in flight. Keeping a discrete `snap` (rather
	// than a raw height) means a content-driven peek change — e.g. adding the
	// first layer — just re-resolves cleanly instead of fighting the user.
	type Snap = 'peek' | 'half' | 'full';
	let snap = $state<Snap>('peek');
	let dragH = $state<number | null>(null);

	// Peek shows the featured strip when empty (taller), the active header +
	// a card or two when not.
	const peek = $derived(app.activeLayers.length ? 188 : 236);
	const halfH = $derived(Math.round(innerH * 0.52));
	const fullH = $derived(Math.round(innerH * 0.9));
	const snapH = $derived(snap === 'peek' ? peek : snap === 'half' ? halfH : fullH);
	const sheetH = $derived(dragH ?? snapH);
	const expanded = $derived(snap !== 'peek');

	let dragStartY = 0;
	let dragStartH = 0;
	let dragMoved = false;

	function nearestSnap(h: number): Snap {
		const opts: [Snap, number][] = [
			['peek', peek],
			['half', halfH],
			['full', fullH]
		];
		return opts.reduce((a, b) => (Math.abs(b[1] - h) < Math.abs(a[1] - h) ? b : a))[0];
	}
	function onHandleDown(e: PointerEvent) {
		dragStartY = e.clientY;
		dragStartH = sheetH;
		dragMoved = false;
		dragH = sheetH;
		(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
	}
	function onHandleMove(e: PointerEvent) {
		if (dragH === null) return;
		const dy = dragStartY - e.clientY;
		if (Math.abs(dy) > 4) dragMoved = true;
		dragH = Math.min(fullH, Math.max(peek, dragStartH + dy));
	}
	function onHandleUp() {
		if (dragH === null) return;
		// A tap (no real drag) toggles peek ↔ half; a drag snaps to the nearest.
		snap = dragMoved ? nearestSnap(dragH) : snap === 'peek' ? 'half' : 'peek';
		dragH = null;
	}

	/** A layer card opened its style panel by hand — lift the sheet so the
	 *  controls are actually visible (only from the collapsed peek). */
	function onStyleOpen() {
		if (!isDesktop && snap === 'peek') snap = 'half';
	}

	// When the inspector opens on a phone it covers the screen — duck the dock.
	$effect(() => {
		if (app.selected && !isDesktop) {
			snap = 'peek';
			dragH = null;
		}
	});
</script>

<svelte:window bind:innerHeight={innerH} bind:innerWidth={innerW} />

<section
	class="dock z-10 flex flex-col bg-white/95 shadow-2xl backdrop-blur"
	class:dragging={dragH !== null}
	style={isDesktop ? '' : `height:${sheetH}px`}
>
	<!-- drag handle (phones only) -->
	<button
		type="button"
		class="block w-full shrink-0 cursor-grab touch-none px-4 pt-2.5 pb-1 md:hidden"
		aria-label="Resize panel"
		aria-expanded={expanded}
		onpointerdown={onHandleDown}
		onpointermove={onHandleMove}
		onpointerup={onHandleUp}
		onpointercancel={onHandleUp}
	>
		<div class="mx-auto h-1.5 w-10 rounded-full bg-slate-300"></div>
	</button>

	<div class="flex min-h-0 flex-1 flex-col overflow-y-auto pt-1 md:overflow-hidden md:pt-4">
		<!-- The list scrolls; on desktop it's the ONLY scroll region, so the catalog
		     button + settings pinned below it never need a scroll to reach. -->
		<div class="flex min-h-0 flex-col md:flex-1 md:overflow-y-auto">
			{#if !app.manifest}
				<p class="px-4 py-4 text-sm text-slate-400">{m.loading()}</p>
			{:else if !app.activeLayers.length}
				<!-- front door: nothing on the map yet -->
				<p class="shrink-0 px-4 pb-2 text-[11px] font-semibold tracking-wide text-slate-400 uppercase">
					{m.featured()}
				</p>
				<FeaturedStrip />
			{:else}
				<!-- active layer manager -->
				<div class="flex shrink-0 items-center gap-2 px-4 pb-2">
					<span class="text-[11px] font-semibold tracking-wide text-slate-500 uppercase">
						{m.active_layers()} · {app.activeLayers.length}
					</span>
					<button
						type="button"
						class="ml-auto shrink-0 rounded-lg px-2 py-1 text-xs font-medium text-slate-500 transition hover:bg-rose-50 hover:text-rose-600"
						onclick={() => app.clearAll()}>{m.clear_all()}</button>
				</div>
				<div class="shrink-0 space-y-2 px-3">
					{#each app.activeLayers as l (l.key)}
						<ActiveLayerCard layer={l} {onStyleOpen} />
					{/each}
				</div>
			{/if}
		</div>

		<!-- Pinned bottom: one contextual catalog button, the map settings, and the
		     footer. No mt-auto (it trapped a gap of whitespace on the mobile sheet). -->
		{#if app.manifest}
			<div class="shrink-0">
				<button
					type="button"
					class="mx-3 mt-2.5 mb-1 flex h-11 items-center justify-center gap-2 rounded-xl border-2 border-dashed border-slate-300 text-sm font-semibold text-slate-600 transition hover:border-emerald-400 hover:bg-emerald-50 hover:text-emerald-700"
					onclick={() => (app.browserOpen = true)}
				>
					<span class="text-lg leading-none" aria-hidden="true">+</span>{app.activeLayers.length
						? m.add_layers()
						: m.browse_catalog()}
				</button>
				<div class="border-t border-black/5 px-4 py-3">
					<MapSettings />
				</div>
				<footer
					class="border-t border-black/5 px-4 py-2 text-[11px] text-slate-400"
					style="padding-bottom: calc(0.5rem + env(safe-area-inset-bottom, 0px))"
				>
					{m.attribution()}
				</footer>
			</div>
		{/if}
	</div>
</section>

<style>
	/* Mobile-first: full-width fly-up sheet; docked rounded card on ≥md. */
	.dock {
		position: absolute;
		bottom: 0;
		left: 0;
		right: 0;
		/* dvh (not vh) so the sheet respects the *visible* viewport. */
		max-height: 92dvh;
		border-top-left-radius: 1rem;
		border-top-right-radius: 1rem;
		overflow: hidden;
		transition: height 0.28s cubic-bezier(0.4, 0, 0.2, 1);
	}
	.dock.dragging {
		transition: none;
	}
	@media (min-width: 768px) {
		.dock {
			left: 1rem;
			right: auto;
			top: 5rem;
			bottom: 1rem;
			width: 400px;
			height: auto !important;
			max-height: none;
			border-radius: 1rem;
			transition: none;
		}
	}
</style>
