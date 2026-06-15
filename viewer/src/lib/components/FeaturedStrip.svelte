<script lang="ts">
	// The curated front door. On phones a horizontally-scrolling strip of compact
	// icon+title cards; on the desktop sidebar a 2-column grid that also shows the
	// blurb. "Surprise me" leads — it's the most fun way in. Each card applies a
	// whole preset (layers + styling + camera) in one tap.
	import { m } from '$lib/paraglide/messages';
	import { FEATURED } from '$lib/featured';
	import { app } from '$lib/state/app.svelte';
	import { featuredTitle, featuredBlurb } from '$lib/i18n';
	import FeaturedIcon from './FeaturedIcon.svelte';

	// Mobile: icon left, title right (short, no trapped vertical space). Desktop
	// (md): stack into a card with the blurb. Shared by every card below.
	const card =
		'flex w-48 shrink-0 snap-start flex-row items-center gap-3 rounded-2xl px-3.5 py-3 text-left shadow-sm transition active:scale-[0.97] md:w-auto md:flex-col md:items-start md:gap-1.5';
	const iconSize = 'h-7 w-7 md:h-6 md:w-6';
</script>

<div
	class="flex snap-x snap-mandatory gap-2 overflow-x-auto px-4 pb-1 md:grid md:grid-cols-2 md:gap-2.5 md:overflow-visible [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
>
	<button
		type="button"
		class="{card} border-2 border-dashed border-violet-300 bg-violet-50 hover:bg-violet-100"
		title={m.surprise_hint()}
		onclick={() => app.surprise()}
	>
		<FeaturedIcon id="surprise" accent="#7c3aed" size={iconSize} />
		<span class="line-clamp-2 text-sm leading-snug font-semibold text-violet-700">
			{app.randomKey ? m.surprise_again() : m.surprise()}
		</span>
		<span class="hidden text-xs leading-snug text-violet-500 md:line-clamp-2">{m.surprise_hint()}</span>
	</button>

	{#each FEATURED as f (f.id)}
		<button
			type="button"
			class="{card} border border-slate-200 bg-white hover:border-slate-300 hover:shadow"
			onclick={() => app.applyFeatured(f)}
		>
			<FeaturedIcon id={f.id} accent={f.accent} size={iconSize} />
			<span class="line-clamp-2 text-sm leading-snug font-semibold text-slate-700">{featuredTitle(f)}</span>
			<span class="hidden text-xs leading-snug text-slate-400 md:line-clamp-2">{featuredBlurb(f)}</span>
		</button>
	{/each}
</div>
