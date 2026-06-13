<script lang="ts">
	// "About this map": the brand, the saying it riffs on, what the data is,
	// who made it, and the language switcher.
	import { fade } from 'svelte/transition';
	import { m } from '$lib/paraglide/messages';
	import { setLocale, locales } from '$lib/paraglide/runtime';
	import { locale } from '$lib/i18n';
	import { app } from '$lib/state/app.svelte';
	import BrandMark from './BrandMark.svelte';
	import rfLogo from '$lib/assets/recovered-factory.png';
</script>

{#if app.aboutOpen}
	<div class="absolute inset-0 z-50 flex items-end justify-center md:items-center md:p-4" transition:fade={{ duration: 150 }}>
		<button
			type="button"
			class="absolute inset-0 cursor-default bg-black/40"
			aria-label={m.close()}
			onclick={() => (app.aboutOpen = false)}
		></button>
		<div
			class="relative max-h-[88dvh] w-full overflow-y-auto rounded-t-2xl bg-white p-5 shadow-2xl md:max-w-md md:rounded-2xl"
			style="padding-bottom: calc(1.25rem + env(safe-area-inset-bottom, 0px))"
			role="dialog"
			aria-modal="true"
			aria-label={m.about()}
		>
			<div class="flex items-start gap-3">
				<div class="min-w-0 flex-1 text-emerald-800">
					<BrandMark textClass="text-xl" />
					<p class="mt-1 text-xs text-slate-500">{m.brand_tagline()}</p>
				</div>
				<button
					type="button"
					class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
					title={m.close()}
					aria-label={m.close()}
					onclick={() => (app.aboutOpen = false)}>✕</button>
			</div>

			<p class="mt-4 text-sm leading-relaxed text-slate-500 italic">{m.about_riff()}</p>

			<!-- about_body is our own static i18n string (not user input), so {@html}
			     is safe and lets the copy carry <a> links + line breaks. -->
			<p class="about-prose mt-3 text-sm leading-relaxed whitespace-pre-line text-slate-600">
				{@html m.about_body()}
			</p>

			<div class="mt-4 flex items-center gap-2 border-t border-slate-100 pt-4">
				<span class="text-xs text-slate-500">{m.language()}</span>
				<div class="flex gap-1">
					{#each locales as loc (loc)}
						<button
							type="button"
							class="rounded-lg px-2.5 py-1 text-xs font-medium uppercase transition
							       {loc === locale ? 'bg-slate-800 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}"
							onclick={() => setLocale(loc)}>{loc}</button>
					{/each}
				</div>
				<a
					href="https://recoveredfactory.net"
					target="_blank"
					rel="noopener"
					class="ml-auto opacity-80 transition hover:opacity-100"
				>
					<img src={rfLogo} alt="Recovered Factory" class="h-8 w-auto" />
				</a>
			</div>
			<p class="mt-3 text-[11px] text-slate-400">{m.attribution()}</p>
		</div>
	</div>
{/if}

<style>
	:global(.about-prose a) {
		color: #047857; /* emerald-700 */
		text-decoration: underline;
		text-underline-offset: 2px;
	}
	:global(.about-prose a:hover) {
		color: #065f46; /* emerald-800 */
	}
</style>
