<script lang="ts">
	// Map-wide controls: theme swatches (the whole look moves together) and the
	// relief / Cali-mask / basemap toggles, plus the 3D exaggeration slider
	// while anything is extruded.
	import { m } from '$lib/paraglide/messages';
	import { THEMES } from '$lib/config';
	import { app } from '$lib/state/app.svelte';
	import { themeLabel } from '$lib/i18n';
</script>

<div class="space-y-2">
	<div class="flex items-center gap-1.5">
		<span
			class="mr-0.5 shrink-0 text-[10px] font-medium tracking-wide text-slate-400 uppercase"
			title={m.theme_hint()}>{m.theme()}</span>
		{#each THEMES as t (t.id)}
			<button
				type="button"
				class="h-7 w-7 rounded-full border transition
				       {app.themeId === t.id
					? 'scale-110 border-emerald-600 ring-2 ring-emerald-600/30'
					: 'border-black/10 hover:scale-105'}"
				style="background:{t.background}"
				title={themeLabel(t)}
				aria-label={themeLabel(t)}
				aria-pressed={app.themeId === t.id}
				onclick={() => app.pickTheme(t)}
			></button>
		{/each}
	</div>

	<div class="flex flex-wrap items-center gap-1.5">
		<button
			type="button"
			class="h-8 rounded-lg border px-2.5 text-xs font-medium transition
			       {app.dem
				? 'border-emerald-600 bg-emerald-600 text-white'
				: 'border-slate-200 text-slate-600 hover:bg-slate-50'}"
			title={m.dem_hint()}
			aria-pressed={app.dem}
			onclick={() => app.toggleDem()}>{m.dem()}</button>
		<button
			type="button"
			class="h-8 rounded-lg border px-2.5 text-xs font-medium transition
			       {app.maskOn
				? 'border-emerald-600 bg-emerald-600 text-white'
				: 'border-slate-200 text-slate-600 hover:bg-slate-50'}"
			title={m.mask_hint()}
			aria-pressed={app.maskOn}
			onclick={() => app.toggleMask()}>{m.mask()}</button>
		<button
			type="button"
			class="h-8 rounded-lg border px-2.5 text-xs font-medium transition
			       {app.baseVisible
				? 'border-slate-600 bg-slate-600 text-white'
				: 'border-slate-200 text-slate-600 hover:bg-slate-50'}"
			title={m.base_hint()}
			aria-pressed={app.baseVisible}
			onclick={() => app.toggleBase()}>{m.base()}</button>
	</div>

	{#if app.anyExtruded}
		<label class="flex items-center gap-2 text-xs text-slate-500">
			<span class="shrink-0">{m.exaggeration()}</span>
			<input
				type="range"
				class="min-w-0 flex-1 accent-amber-500"
				min="1"
				max="12"
				step="0.5"
				bind:value={app.exaggeration}
				oninput={() => app.applyExaggeration()}
				title={m.exaggeration_hint()}
			/>
			<span class="w-9 shrink-0 text-right tabular-nums text-slate-600">{app.exaggeration}×</span>
		</label>
	{/if}
</div>
