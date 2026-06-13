<script lang="ts">
	// The curated front door: a horizontally-scrolling strip of featured views
	// plus a "surprise me" card. Each tap applies a whole preset (layers +
	// styling + camera) — one gesture from blank map to something meaningful.
	import { m } from '$lib/paraglide/messages';
	import { FEATURED } from '$lib/featured';
	import { app } from '$lib/state/app.svelte';
	import { featuredTitle } from '$lib/i18n';
</script>

<div
	class="flex shrink-0 snap-x snap-mandatory gap-2 overflow-x-auto px-4 pb-1 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
>
	{#each FEATURED as f (f.id)}
		<button
			type="button"
			class="flex w-32 shrink-0 snap-start flex-col items-start gap-1.5 rounded-xl border border-black/5 bg-white px-3 py-2.5 text-left shadow-sm transition active:scale-[0.97]"
			onclick={() => app.applyFeatured(f)}
		>
			<span class="text-xl leading-none" aria-hidden="true">{f.emoji}</span>
			<span class="line-clamp-2 text-xs leading-snug font-medium text-slate-700">{featuredTitle(f)}</span>
		</button>
	{/each}
	<button
		type="button"
		class="flex w-32 shrink-0 snap-start flex-col items-start gap-1.5 rounded-xl border border-dashed border-violet-300 bg-violet-50/60 px-3 py-2.5 text-left shadow-sm transition active:scale-[0.97]"
		title={m.surprise_hint()}
		onclick={() => app.surprise()}
	>
		<span class="text-xl leading-none" aria-hidden="true">🎲</span>
		<span class="line-clamp-2 text-xs leading-snug font-medium text-violet-700">{m.surprise()}</span>
	</button>
</div>
