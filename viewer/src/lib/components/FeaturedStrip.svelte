<script lang="ts">
	// The curated front door. On phones a horizontally-scrolling strip; on the
	// desktop sidebar a 2-column grid showing all of them. "Surprise me" leads
	// — it's the most fun way in. Each card applies a whole preset (layers +
	// styling + camera) in one tap.
	import { m } from '$lib/paraglide/messages';
	import { FEATURED } from '$lib/featured';
	import { app } from '$lib/state/app.svelte';
	import { featuredTitle, featuredBlurb } from '$lib/i18n';
</script>

<div
	class="flex shrink-0 snap-x snap-mandatory gap-2 overflow-x-auto px-4 pb-1 md:grid md:grid-cols-2 md:gap-2.5 md:overflow-visible [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
>
	<button
		type="button"
		class="flex w-36 shrink-0 snap-start flex-col items-start gap-1.5 rounded-2xl border-2 border-dashed border-violet-300 bg-violet-50 px-3.5 py-3 text-left shadow-sm transition hover:bg-violet-100 active:scale-[0.97] md:w-auto"
		title={m.surprise_hint()}
		onclick={() => app.surprise()}
	>
		<span class="text-2xl leading-none" aria-hidden="true">🎲</span>
		<span class="text-sm leading-snug font-semibold text-violet-700">
			{app.randomKey ? m.surprise_again() : m.surprise()}
		</span>
		<span class="hidden text-xs leading-snug text-violet-500 md:line-clamp-2">{m.surprise_hint()}</span>
	</button>

	{#each FEATURED as f (f.id)}
		<button
			type="button"
			class="flex w-36 shrink-0 snap-start flex-col items-start gap-1.5 rounded-2xl border border-slate-200 bg-white px-3.5 py-3 text-left shadow-sm transition hover:border-slate-300 hover:shadow active:scale-[0.97] md:w-auto"
			onclick={() => app.applyFeatured(f)}
		>
			<span class="text-2xl leading-none" aria-hidden="true">{f.emoji}</span>
			<span class="line-clamp-2 text-sm leading-snug font-semibold text-slate-700">{featuredTitle(f)}</span>
			<span class="hidden text-xs leading-snug text-slate-400 md:line-clamp-2">{featuredBlurb(f)}</span>
		</button>
	{/each}
</div>
