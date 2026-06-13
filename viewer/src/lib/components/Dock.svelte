<script lang="ts">
	// The main control surface. On phones it's a draggable bottom sheet that
	// snaps between peek / half / full; on ≥md it's a docked left panel. Its
	// peek state is the "front door": when nothing is on the map it shows the
	// featured strip, otherwise the active-layer manager.
	import { m } from '$lib/paraglide/messages';
	import { app } from '$lib/state/app.svelte';
	import ActiveLayerCard from './ActiveLayerCard.svelte';
	import FeaturedStrip from './FeaturedStrip.svelte';
	import MapSettings from './MapSettings.svelte';

	let innerH = $state(typeof window !== 'undefined' ? window.innerHeight : 800);
	let innerW = $state(typeof window !== 'undefined' ? window.innerWidth : 1024);
	const isDesktop = $derived(innerW >= 768);

	// Peek shows the featured strip when the map is empty, the active-layer
	// header + first card when it isn't.
	const peek = $derived(app.activeLayers.length ? 168 : 236);
	let sheetH = $state(236);
	let dragging = $state(false);
	let dragStartY = 0;
	let dragStartH = 0;
	let dragMoved = false;
	const halfH = $derived(Math.round(innerH * 0.5));
	const fullH = $derived(Math.round(innerH * 0.88));
	const expanded = $derived(sheetH > peek + 24);

	function snapNearest(h: number): number {
		return [peek, halfH, fullH].reduce((a, b) => (Math.abs(b - h) < Math.abs(a - h) ? b : a));
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
		sheetH = Math.min(fullH, Math.max(peek, dragStartH + dy));
	}
	function onHandleUp() {
		if (!dragging) return;
		dragging = false;
		// A tap (no real drag) toggles between peek and half.
		sheetH = dragMoved ? snapNearest(sheetH) : sheetH <= peek + 8 ? halfH : peek;
	}

	// When the inspector opens on a phone it covers the screen — duck the dock.
	$effect(() => {
		if (app.selected && !isDesktop && !dragging) sheetH = peek;
	});
	// Keep a collapsed sheet aligned with the (content-dependent) peek height.
	$effect(() => {
		if (!dragging && sheetH < halfH - 48 && sheetH !== peek) sheetH = peek;
	});
</script>

<svelte:window bind:innerHeight={innerH} bind:innerWidth={innerW} />

<section
	class="dock z-10 flex flex-col bg-white/95 shadow-2xl backdrop-blur"
	class:dragging
	style={isDesktop ? '' : `height:${sheetH}px`}
>
	<!-- drag handle (phones only) -->
	<button
		type="button"
		class="block w-full shrink-0 cursor-grab touch-none px-4 pt-2 md:hidden"
		aria-label="Resize panel"
		aria-expanded={expanded}
		onpointerdown={onHandleDown}
		onpointermove={onHandleMove}
		onpointerup={onHandleUp}
		onpointercancel={onHandleUp}
	>
		<div class="mx-auto mb-1.5 h-1.5 w-10 rounded-full bg-slate-300"></div>
	</button>

	<div class="flex min-h-0 flex-1 flex-col overflow-y-auto pt-1 md:pt-3">
		{#if !app.manifest}
			<p class="px-4 py-4 text-sm text-slate-400">{m.loading()}</p>
		{:else if !app.activeLayers.length}
			<!-- front door: nothing on the map yet -->
			<p class="shrink-0 px-4 pb-2 text-[11px] font-medium tracking-wide text-slate-400 uppercase">
				{m.featured()}
			</p>
			<FeaturedStrip />
			<button
				type="button"
				class="mx-4 mt-3 flex h-10 shrink-0 items-center justify-center gap-2 rounded-xl border border-slate-200 text-sm font-medium text-slate-600 transition hover:bg-slate-50"
				onclick={() => (app.browserOpen = true)}
			>
				<span aria-hidden="true">＋</span>{m.browse_catalog()}
			</button>
		{:else}
			<!-- active layer manager -->
			<div class="flex shrink-0 items-center gap-1.5 px-4 pb-2">
				<span class="min-w-0 truncate text-[11px] font-medium tracking-wide text-slate-400 uppercase">
					{m.active_layers()} ({app.activeLayers.length})
				</span>
				<button
					type="button"
					class="ml-auto flex h-8 shrink-0 items-center gap-1 rounded-lg border border-slate-200 px-2 text-xs font-medium text-slate-600 transition hover:bg-slate-50"
					onclick={() => (app.browserOpen = true)}
				>
					<span aria-hidden="true">＋</span><span class="max-[360px]:hidden">{m.add_layers()}</span>
				</button>
				<button
					type="button"
					class="flex h-8 shrink-0 items-center rounded-lg border border-violet-200 px-2 text-xs font-medium text-violet-700 transition hover:bg-violet-50"
					title={m.surprise_hint()}
					onclick={() => app.surprise()}
				>
					🎲<span class="ml-1 max-[420px]:hidden">{app.randomKey ? m.surprise_again() : m.surprise()}</span>
				</button>
				<button
					type="button"
					class="flex h-8 shrink-0 items-center rounded-lg px-2 text-xs text-slate-400 underline transition hover:text-slate-700"
					onclick={() => app.clearAll()}>{m.clear_all()}</button>
			</div>
			<div class="shrink-0 space-y-2 px-3 pb-3">
				{#each app.activeLayers as l (l.key)}
					<ActiveLayerCard layer={l} />
				{/each}
			</div>
		{/if}

		<div class="mt-auto shrink-0 border-t border-black/5 px-4 py-2.5">
			<MapSettings />
		</div>
		<footer
			class="shrink-0 border-t border-black/5 px-4 py-2 text-[11px] text-slate-400"
			style="padding-bottom: calc(0.5rem + env(safe-area-inset-bottom, 0px))"
		>
			{m.attribution()}
		</footer>
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
			width: 380px;
			height: auto !important;
			max-height: none;
			border-radius: 1rem;
			transition: none;
		}
	}
</style>
