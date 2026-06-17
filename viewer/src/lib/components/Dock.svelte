<script lang="ts">
	// The main control surface. On phones it's a bottom sheet with two states:
	// `closed` (the grab handle + a one-line summary — the map is a pure navigation
	// surface showing your selected layers) and `open`. Open is sized to show the
	// "primary" block — the front door / active-layer list + the catalog button —
	// and nothing more; the display options (map settings + footer) sit just below
	// the fold, reachable by scrolling (or by dragging the sheet taller). So tapping
	// a curated view drops you on your layers + Add, not a wall of config. Capped at
	// 90% so a long active-layer list scrolls in place. On ≥md it's a docked panel.
	import { m } from '$lib/paraglide/messages';
	import { app } from '$lib/state/app.svelte';
	import ActiveLayerCard from './ActiveLayerCard.svelte';
	import FeaturedStrip from './FeaturedStrip.svelte';
	import MapSettings from './MapSettings.svelte';

	let innerH = $state(typeof window !== 'undefined' ? window.innerHeight : 800);
	let innerW = $state(typeof window !== 'undefined' ? window.innerWidth : 1024);
	const isDesktop = $derived(innerW >= 768);

	type Snap = 'closed' | 'open';
	let snap = $state<Snap>('open'); // open to the front door on first load
	let dragH = $state<number | null>(null);

	const CLOSED_H = 60; // grab handle + the summary line, nothing more

	// Measure the PRIMARY block (content + catalog button) so `open` hugs it: you
	// land on the layers + Add, with the settings one scroll below — never a dead
	// gap, and never the whole config in your face. Caps at 90% (then it scrolls).
	let primaryEl: HTMLElement | undefined = $state();
	let scrollEl: HTMLElement | undefined = $state();
	let natH = $state(420);
	// A ResizeObserver, not reactive deps: the active-layer legends grow the block
	// asynchronously (field stats load after the map paints), so we must re-measure
	// on the real size change, not just when the layer list changes.
	$effect(() => {
		const el = primaryEl;
		if (!el) return;
		// 26 = grab handle (~22) + the scroll box's top padding (~4).
		const measure = () => (natH = 26 + el.offsetHeight);
		measure();
		const ro = new ResizeObserver(measure);
		ro.observe(el);
		return () => ro.disconnect();
	});
	// New layer set → start the scroll at the top so you see the layers, not a
	// position the browser scroll-anchored to while the legends were loading in.
	$effect(() => {
		void app.activeLayers.length;
		if (scrollEl) scrollEl.scrollTop = 0;
	});

	const fullH = $derived(Math.round(innerH * 0.9));
	const openH = $derived(Math.min(natH, fullH));
	const snapH = $derived(snap === 'closed' ? CLOSED_H : openH);
	const sheetH = $derived(dragH ?? snapH);
	const expanded = $derived(snap !== 'closed');

	// Closed-state summary: what's behind the handle, so it's clear it's there.
	const summary = $derived(
		app.activeLayers.length
			? `${app.activeLayers.length} · ${m.active_layers()}`
			: m.featured()
	);

	let dragStartY = 0;
	let dragStartH = 0;
	let dragMoved = false;

	function nearestSnap(h: number): Snap {
		return Math.abs(h - CLOSED_H) < Math.abs(h - openH) ? 'closed' : 'open';
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
		dragH = Math.min(fullH, Math.max(CLOSED_H, dragStartH + dy));
	}
	function onHandleUp() {
		if (dragH === null) return;
		// A tap (no real drag) toggles; a drag snaps to the nearer of closed / open.
		snap = dragMoved ? nearestSnap(dragH) : expanded ? 'closed' : 'open';
		dragH = null;
	}

	/** A layer card opened its style panel by hand — open the sheet so the
	 *  controls are actually visible (only from the collapsed state). */
	function onStyleOpen() {
		if (!isDesktop && !expanded) snap = 'open';
	}

	// When the inspector opens on a phone it covers the screen — collapse to the
	// handle so the map + the selected feature own the view.
	$effect(() => {
		if (app.selected && !isDesktop) {
			snap = 'closed';
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
		class="block w-full shrink-0 cursor-grab touch-none px-4 pt-2.5 pb-1.5 md:hidden"
		aria-label={expanded ? 'Collapse layers panel' : 'Expand layers panel'}
		aria-expanded={expanded}
		onpointerdown={onHandleDown}
		onpointermove={onHandleMove}
		onpointerup={onHandleUp}
		onpointercancel={onHandleUp}
	>
		<div class="mx-auto h-1.5 w-10 rounded-full bg-slate-300"></div>
		{#if !expanded}
			<div class="mt-1.5 flex items-center justify-center gap-1 text-[11px] font-medium text-slate-500">
				<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" class="h-3 w-3 text-slate-400" aria-hidden="true">
					<path d="m4 10 4-4 4 4" />
				</svg>
				<span>{summary}</span>
			</div>
		{/if}
	</button>

	<!-- The one scroll region. `open` hugs the primary block (layers + Add); the
	     map settings + footer follow below it, reached by scrolling or dragging up.
	     overflow-anchor:none so an async legend growing below the fold can't yank
	     the scroll position down off the layers. -->
	<div
		bind:this={scrollEl}
		class="flex min-h-0 flex-1 flex-col overflow-y-auto pt-1 [overflow-anchor:none] md:pt-3"
	>
		<div bind:this={primaryEl}>
			{#if !app.manifest}
				<p class="px-4 py-4 text-sm text-slate-400">{m.loading()}</p>
			{:else if !app.activeLayers.length}
				<!-- front door: nothing on the map yet -->
				<p class="px-4 pb-2 text-[11px] font-semibold tracking-wide text-slate-400 uppercase">
					{m.featured()}
				</p>
				<FeaturedStrip />
			{:else}
				<!-- active layer manager -->
				<div class="flex items-center gap-2 px-4 pb-2">
					<span class="text-[11px] font-semibold tracking-wide text-slate-500 uppercase">
						{m.active_layers()} · {app.activeLayers.length}
					</span>
					<button
						type="button"
						class="ml-auto shrink-0 rounded-lg px-2 py-1 text-xs font-medium text-slate-500 transition hover:bg-rose-50 hover:text-rose-600"
						onclick={() => app.clearAll()}>{m.clear_all()}</button>
				</div>
				<div class="space-y-2 px-3">
					{#each app.activeLayers as l (l.key)}
						<ActiveLayerCard layer={l} {onStyleOpen} />
					{/each}
				</div>
			{/if}

			{#if app.manifest}
				<div class="px-3 pt-2.5 pb-2.5">
					<button
						type="button"
						class="flex h-12 w-full items-center justify-center gap-2 rounded-xl bg-emerald-600 text-sm font-semibold text-white shadow-sm transition hover:bg-emerald-700 active:scale-[.99]"
						onclick={() => (app.browserOpen = true)}
					>
						<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" class="h-4.5 w-4.5 shrink-0" aria-hidden="true">
							<path d="M10 4.5v11M4.5 10h11" />
						</svg>
						{app.activeLayers.length ? m.add_layers() : m.browse_catalog()}
					</button>
				</div>
			{/if}
		</div>

		<!-- Display options + footer: below the fold of the `open` snap. -->
		{#if app.manifest}
			<div class="border-t border-black/5 px-4 pt-2.5 pb-3">
				<MapSettings />
			</div>
			<footer
				class="border-t border-black/5 px-4 py-2 text-[11px] text-slate-400"
				style="padding-bottom: calc(0.5rem + env(safe-area-inset-bottom, 0px))"
			>
				{m.attribution()}
			</footer>
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
