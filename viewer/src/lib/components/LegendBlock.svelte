<script lang="ts">
	// Contextual legend for a layer colored by a field: a histogram + ramp bar
	// for numeric fields, a swatch list for categorical ones. Stats come from
	// the features currently loaded (a sample for pmtiles layers).
	import { m } from '$lib/paraglide/messages';
	import type { Layer } from '$lib/config';
	import { app } from '$lib/state/app.svelte';
	import { fmtNum } from '$lib/i18n';

	let { layer }: { layer: Layer } = $props();

	const stats = $derived(app.fieldStats[layer.key]);
	const rampGradient = $derived(
		`linear-gradient(to right, ${app.theme.graduatedRamp
			.map(([t, c]) => `${c} ${Math.round(t * 100)}%`)
			.join(', ')})`
	);
</script>

{#if stats?.kind === 'numeric'}
	{@const peak = Math.max(1, ...stats.bins)}
	<div class="mt-1.5 flex h-8 items-end gap-px" aria-hidden="true">
		{#each stats.bins as c, i (i)}
			<div
				class="min-w-0 flex-1 rounded-sm"
				style="height:{Math.max(2, Math.round((c / peak) * 100))}%;background:{app.theme.graduatedRamp[
					Math.min(
						app.theme.graduatedRamp.length - 1,
						Math.floor((i / stats.bins.length) * app.theme.graduatedRamp.length)
					)
				][1]}"
			></div>
		{/each}
	</div>
	<div class="mt-1 h-1.5 rounded" style="background:{rampGradient}"></div>
	<div class="mt-0.5 flex justify-between text-[10px] tabular-nums text-slate-400">
		<span>{fmtNum(stats.min)}</span>
		<span>n={stats.total}{#if layer.serve === 'pmtiles'}&nbsp;({m.sample_note()}){/if}</span>
		<span>{fmtNum(stats.max)}</span>
	</div>
{:else if stats?.kind === 'categorical'}
	{@const peak = Math.max(1, ...stats.items.map((it) => it.count))}
	<ul class="mt-1.5 space-y-0.5">
		{#each stats.items.slice(0, 8) as it (it.value)}
			<li class="flex items-center gap-1.5 text-[10px] text-slate-500">
				<span class="inline-block h-2.5 w-2.5 shrink-0 rounded-sm" style="background:{it.color}"></span>
				<span class="min-w-0 flex-1 truncate" title={it.value}>{it.value}</span>
				<span
					class="h-1.5 shrink-0 rounded-sm bg-slate-300"
					style="width:{Math.round((it.count / peak) * 36) + 2}px"
				></span>
				<span class="w-8 shrink-0 text-right tabular-nums text-slate-400">{it.count}</span>
			</li>
		{/each}
		{#if stats.items.length > 8}
			<li class="text-[10px] text-slate-400">+{stats.items.length - 8} …</li>
		{/if}
	</ul>
{/if}
