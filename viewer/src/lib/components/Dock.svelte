<script lang="ts">
	// The main control surface. On phones it's a bottom sheet with two states:
	// `closed` (the grab handle + a one-line summary — the map is a pure navigation
	// surface showing your selected layers) and `open`. Open is sized to show the
	// "primary" block — the front door / active-layer list, the catalog button, AND
	// the display options (relief / base / theme) — so the styling row lands within
	// reach without scrolling; only the footer sits below the fold. Capped at 90% so
	// a long active-layer list scrolls in place. On ≥md it's a docked panel where the
	// active-layer list scrolls and the styling row + footer stay pinned at the
	// bottom, always visible.
	import { m } from '$lib/paraglide/messages';
	import { app } from '$lib/state/app.svelte';
	import { track } from '$lib/analytics';
	import ActiveLayerCard from './ActiveLayerCard.svelte';
	import FeaturedStrip from './FeaturedStrip.svelte';
	import MapSettings from './MapSettings.svelte';
	import { flip } from 'svelte/animate';
	import type { Layer } from '$lib/config';

	let innerH = $state(typeof window !== 'undefined' ? window.innerHeight : 800);
	let innerW = $state(typeof window !== 'undefined' ? window.innerWidth : 1024);
	const isDesktop = $derived(innerW >= 768);

	type Snap = 'closed' | 'open';
	let snap = $state<Snap>('open'); // open to the front door on first load
	let dragH = $state<number | null>(null);

	const CLOSED_H = 60; // grab handle + the summary line, nothing more

	// Measure the PRIMARY block (content + catalog button + display options) so
	// `open` hugs it: you land on the layers + Add + the styling row, with only the
	// footer one scroll below — never a dead gap. Caps at 90% (then it scrolls).
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

	// --- active-layer drag reordering ----------------------------------------
	// The list is shown TOP = top-of-map (the standard layers-panel convention),
	// so it renders `app.active` (draw order, bottom→top) reversed. Dragging a
	// grip swaps cards as the pointer crosses each card's box; `animate:flip`
	// slides them. On drop we commit the new order to the app (which restacks the
	// map z-order and persists to the URL). Window listeners (not pointer capture)
	// let the move logic see every card, regardless of which one started the drag.
	let dragKey = $state<string | null>(null);
	let dragOrder = $state<string[] | null>(null); // working display order during a drag
	let cardEls: HTMLElement[] = $state([]);
	// A swap reorders the list and `animate:flip` slides the cards over ~FLIP_MS.
	// Measuring getBoundingClientRect() mid-slide returns transitional positions
	// that flip-flop which card is "under" the pointer → the cards vibrate. So after
	// each swap, lock further swaps until the slide settles, then measure at rest.
	// (Plain lets, not reactive state.)
	const FLIP_MS = 160;
	let swapLockUntil = 0;

	const displayLayers = $derived<Layer[]>(
		dragOrder
			? dragOrder.map((k) => app.byKey.get(k)).filter((l): l is Layer => !!l)
			: [...app.activeLayers].reverse()
	);

	function startDrag(e: PointerEvent, key: string) {
		if (displayLayers.length < 2) return;
		e.preventDefault();
		e.stopPropagation();
		dragKey = key;
		dragOrder = displayLayers.map((l) => l.key);
		window.addEventListener('pointermove', onDragMove);
		window.addEventListener('pointerup', endDrag);
		window.addEventListener('pointercancel', endDrag);
	}

	function onDragMove(e: PointerEvent) {
		if (!dragKey || !dragOrder) return;
		e.preventDefault();
		// Don't re-evaluate while the previous swap's flip is still animating.
		if (performance.now() < swapLockUntil) return;
		const from = dragOrder.indexOf(dragKey);
		if (from < 0) return;
		// The card the pointer is over (clamped to the ends when past them).
		let over = -1;
		const n = displayLayers.length;
		for (let i = 0; i < n; i++) {
			const r = cardEls[i]?.getBoundingClientRect();
			if (r && e.clientY >= r.top && e.clientY <= r.bottom) {
				over = i;
				break;
			}
		}
		if (over < 0) {
			const firstR = cardEls[0]?.getBoundingClientRect();
			const lastR = cardEls[n - 1]?.getBoundingClientRect();
			if (firstR && e.clientY < firstR.top) over = 0;
			else if (lastR && e.clientY > lastR.bottom) over = n - 1;
		}
		// Move `from` to the slot the pointer is over. Splicing the item out then
		// in at `over` lands it correctly with no off-by-one (see splice semantics).
		if (over >= 0 && over !== from) {
			const next = dragOrder.slice();
			next.splice(over, 0, next.splice(from, 1)[0]);
			dragOrder = next;
			swapLockUntil = performance.now() + FLIP_MS + 40; // let this slide finish first
		}
	}

	function endDrag() {
		window.removeEventListener('pointermove', onDragMove);
		window.removeEventListener('pointerup', endDrag);
		window.removeEventListener('pointercancel', endDrag);
		if (dragKey && dragOrder) {
			// Display order (top→bottom) → draw order (bottom→top).
			app.setOrder([...dragOrder].reverse());
			track('layer-reorder', { key: dragKey });
		}
		dragKey = null;
		dragOrder = null;
	}

	// Defensive: drop any window listeners if we unmount mid-drag.
	$effect(() => () => {
		window.removeEventListener('pointermove', onDragMove);
		window.removeEventListener('pointerup', endDrag);
		window.removeEventListener('pointercancel', endDrag);
	});

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

	<!-- The one scroll region. `open` hugs the primary block (layers + Add + the
	     styling row); only the footer follows below it, reached by scrolling.
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
				<div class="space-y-2 px-3" class:select-none={!!dragKey}>
					{#each displayLayers as l, i (l.key)}
						<div bind:this={cardEls[i]} animate:flip={{ duration: 160 }}>
							<ActiveLayerCard
								layer={l}
								{onStyleOpen}
								desktop={isDesktop}
								showGrip={displayLayers.length > 1}
								dragging={l.key === dragKey}
								onGripDown={(e) => startDrag(e, l.key)}
							/>
						</div>
					{/each}
				</div>
			{/if}

			{#if app.manifest}
				<div class="px-3 pt-2.5 pb-2.5">
					<button
						type="button"
						class="flex h-12 w-full items-center justify-center gap-2 rounded-xl bg-emerald-600 text-sm font-semibold text-white shadow-sm transition hover:bg-emerald-700 active:scale-[.99]"
						onclick={() => {
							app.browserOpen = true;
							track('browser-open');
						}}
					>
						<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" class="h-4.5 w-4.5 shrink-0" aria-hidden="true">
							<path d="M10 4.5v11M4.5 10h11" />
						</svg>
						{app.activeLayers.length ? m.add_layers() : m.browse_catalog()}
					</button>
				</div>

				<!-- Phones: the styling row rides inside the measured block so it's
				     visible within the open snap. Desktop pins its own copy below. -->
				<div class="border-t border-black/5 px-4 pt-2.5 pb-3 md:hidden">
					<MapSettings />
				</div>
			{/if}
		</div>

		<!-- Phone footer: below the fold of the `open` snap. -->
		{#if app.manifest}
			<footer
				class="border-t border-black/5 px-4 py-2 text-[11px] text-slate-400 md:hidden"
				style="padding-bottom: calc(0.5rem + env(safe-area-inset-bottom, 0px))"
			>
				{m.attribution()}
			</footer>
		{/if}
	</div>

	<!-- Desktop: the styling row + footer are pinned to the panel bottom (outside
	     the scroll region) so they're always visible, never scrolled to. -->
	{#if app.manifest}
		<div class="hidden shrink-0 md:block">
			<div class="border-t border-black/5 px-4 pt-2.5 pb-3">
				<MapSettings />
			</div>
			<footer class="border-t border-black/5 px-4 py-2 text-[11px] text-slate-400">
				{m.attribution()}
			</footer>
		</div>
	{/if}
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
