<script lang="ts">
	// Map-wide controls: the 3D exaggeration slider (when anything is extruded —
	// kept up top, tied to the active layers), the relief / basemap toggles, and
	// the theme swatches (the whole look moves together).
	import { m } from '$lib/paraglide/messages';
	import { THEMES } from '$lib/config';
	import { app } from '$lib/state/app.svelte';
	import { themeLabel } from '$lib/i18n';
	import { track, debounce } from '$lib/analytics';
	import Recenter from '~icons/solar/gps-bold-duotone';

	// The slider restyles live on every `oninput` tick; log only once it settles.
	const trackExag = debounce((value: number) => track('exaggeration-change', { value }), 500);
</script>

<div class="space-y-2.5">
	{#if app.anyExtruded}
		<label class="flex items-center gap-2 rounded-lg bg-amber-50 px-2.5 py-1.5 text-xs font-medium text-amber-800">
			<span class="shrink-0">{m.exaggeration()}</span>
			<input
				type="range"
				class="min-w-0 flex-1 accent-amber-500"
				min="1"
				max="12"
				step="0.5"
				bind:value={app.exaggeration}
				oninput={() => {
					app.applyExaggeration();
					trackExag(app.exaggeration);
				}}
				title={m.exaggeration_hint()}
			/>
			<span class="w-9 shrink-0 text-right tabular-nums">{app.exaggeration}×</span>
		</label>
	{/if}

	<div class="flex flex-wrap items-center gap-1.5">
		<button
			type="button"
			class="flex h-8 items-center gap-1 rounded-lg pr-2.5 pl-1.5 text-xs font-semibold transition
			       {app.dem
				? 'bg-emerald-600 text-white shadow-sm'
				: 'bg-slate-100 text-slate-700 hover:bg-slate-200'}"
			title={m.dem_hint()}
			aria-pressed={app.dem}
			onclick={() => app.toggleDem()}
		>
			<span
				class="flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded border text-[9px] leading-none
				       {app.dem ? 'border-white/80 text-white' : 'border-slate-400 text-transparent'}"
				aria-hidden="true">✓</span>
			{m.dem()}
		</button>
		<button
			type="button"
			class="flex h-8 items-center gap-1 rounded-lg pr-2.5 pl-1.5 text-xs font-semibold transition
			       {app.baseVisible
				? 'bg-slate-700 text-white shadow-sm'
				: 'bg-slate-100 text-slate-700 hover:bg-slate-200'}"
			title={m.base_hint()}
			aria-pressed={app.baseVisible}
			onclick={() => app.toggleBase()}
		>
			<span
				class="flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded border text-[9px] leading-none
				       {app.baseVisible ? 'border-white/80 text-white' : 'border-slate-400 text-transparent'}"
				aria-hidden="true">✓</span>
			{m.base()}
		</button>
		<button
			type="button"
			class="flex h-8 items-center gap-1 rounded-lg bg-slate-100 pr-2.5 pl-1.5 text-xs font-semibold
			       text-slate-700 transition hover:bg-slate-200"
			title={m.reset_view_hint()}
			onclick={() => app.resetView()}
		>
			<Recenter class="h-4 w-4 shrink-0" aria-hidden="true" />
			{m.reset_view()}
		</button>

		<div class="ml-auto flex items-center gap-1" title={m.theme_hint()}>
			{#each THEMES as t (t.id)}
				<button
					type="button"
					class="h-6 w-6 rounded-full border-2 transition
					       {app.themeId === t.id
						? 'scale-110 border-emerald-600 ring-2 ring-emerald-600/25'
						: 'border-black/15 hover:scale-105'}"
					style="background:{t.background}"
					title={themeLabel(t)}
					aria-label={themeLabel(t)}
					aria-pressed={app.themeId === t.id}
					onclick={() => app.pickTheme(t)}
				></button>
			{/each}
		</div>
	</div>
</div>
