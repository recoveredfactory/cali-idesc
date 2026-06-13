<script lang="ts">
	// Floating top row: brand chip (opens About), a Google-Maps-style search
	// pill (opens the layer browser), and the locale toggle.
	import { m } from '$lib/paraglide/messages';
	import { setLocale, locales } from '$lib/paraglide/runtime';
	import { locale } from '$lib/i18n';
	import { app } from '$lib/state/app.svelte';
	import BrandMark from './BrandMark.svelte';
</script>

<div
	class="pointer-events-none absolute inset-x-0 top-0 z-20 flex items-center gap-2 p-3"
	style="padding-top: calc(0.75rem + env(safe-area-inset-top, 0px))"
>
	<button
		type="button"
		class="pointer-events-auto flex h-11 shrink-0 items-center rounded-full bg-white/90 px-3.5 text-slate-800 shadow-lg backdrop-blur transition hover:bg-white"
		title={m.about()}
		aria-label={m.about()}
		onclick={() => (app.aboutOpen = true)}
	>
		<BrandMark glyphClass="h-5 w-5 text-emerald-700" textClass="text-[15px] max-[360px]:hidden" />
	</button>

	<button
		type="button"
		class="pointer-events-auto flex h-11 min-w-0 flex-1 items-center gap-2.5 rounded-full bg-white/90 px-4 text-left shadow-lg backdrop-blur transition hover:bg-white md:max-w-sm"
		onclick={() => (app.browserOpen = true)}
	>
		<svg
			viewBox="0 0 20 20"
			fill="none"
			stroke="currentColor"
			stroke-width="1.8"
			stroke-linecap="round"
			class="h-4.5 w-4.5 shrink-0 text-slate-400"
			aria-hidden="true"
		>
			<circle cx="9" cy="9" r="6" />
			<path d="m13.5 13.5 4 4" />
		</svg>
		<span class="truncate text-sm text-slate-500">{m.search_placeholder()}</span>
		{#if app.manifest}
			<span class="ml-auto shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-[10px] tabular-nums text-slate-400">
				{m.layers_count({ count: app.manifest.generated_layers })}
			</span>
		{/if}
	</button>

	<div
		class="pointer-events-auto flex h-11 shrink-0 items-center gap-0.5 rounded-full bg-white/90 p-1 shadow-lg backdrop-blur"
		aria-label={m.language()}
	>
		{#each locales as loc (loc)}
			<button
				type="button"
				class="flex h-8 w-8 items-center justify-center rounded-full text-xs font-medium uppercase transition
				       {loc === locale ? 'bg-slate-800 text-white' : 'text-slate-500 hover:bg-slate-100'}"
				onclick={() => setLocale(loc)}>{loc}</button>
		{/each}
	</div>
</div>
