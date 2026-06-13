<script lang="ts">
	// The layer browser: full-screen on phones, a docked sheet on desktop.
	// Empty query → featured views + the catalog grouped by (friendly-named)
	// workspace. Typing filters the whole catalog. Turning a layer ON closes
	// the browser and flies to it — the map is the payoff; turning one OFF
	// keeps the browser open.
	import { fade, fly } from 'svelte/transition';
	import { m } from '$lib/paraglide/messages';
	import type { Layer } from '$lib/config';
	import { FEATURED } from '$lib/featured';
	import { app } from '$lib/state/app.svelte';
	import { workspaceColor } from '$lib/map';
	import { workspaceLabel } from '$lib/workspaces';
	import { locale, titleOf, leafTitle, categoryOf, featuredTitle, featuredBlurb } from '$lib/i18n';
	import FeaturedIcon from './FeaturedIcon.svelte';

	let search = $state('');
	let searchEl: HTMLInputElement | undefined = $state();

	$effect(() => {
		if (app.browserOpen) {
			search = '';
			// Focus after the fly-in starts so the mobile keyboard opens.
			setTimeout(() => searchEl?.focus(), 60);
		}
	});

	function close() {
		app.browserOpen = false;
	}

	function pickLayer(l: Layer) {
		if (app.active.includes(l.key)) {
			app.disable(l.key);
		} else {
			app.enable(l);
			close();
		}
	}

	const groups = $derived.by(() => {
		if (!app.manifest) return [] as { workspace: string; layers: Layer[] }[];
		const q = search.trim().toLowerCase();
		const byWs = new Map<string, Layer[]>();
		for (const l of app.manifest.layers) {
			if (q) {
				const hay =
					`${l.title_es} ${l.title_en} ${l.typename} ${workspaceLabel(l.workspace, locale)}`.toLowerCase();
				if (!hay.includes(q)) continue;
			}
			(byWs.get(l.workspace) ?? byWs.set(l.workspace, []).get(l.workspace)!).push(l);
		}
		return [...byWs.entries()]
			.sort((a, b) =>
				workspaceLabel(a[0], locale).localeCompare(workspaceLabel(b[0], locale), locale)
			)
			.map(([workspace, layers]) => ({ workspace, layers }));
	});
</script>

{#if app.browserOpen}
	<div class="absolute inset-0 z-40" transition:fade={{ duration: 120 }}>
		<button
			type="button"
			class="absolute inset-0 cursor-default bg-black/30"
			aria-label={m.close()}
			onclick={close}
		></button>
		<div
			class="browser absolute flex flex-col bg-white shadow-2xl"
			role="dialog"
			aria-modal="true"
			aria-label={m.search_placeholder()}
			transition:fly={{ y: 24, duration: 200 }}
		>
			<header
				class="flex shrink-0 items-center gap-2 border-b border-black/5 px-3 py-2.5"
				style="padding-top: calc(0.625rem + env(safe-area-inset-top, 0px))"
			>
				<button
					type="button"
					class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-slate-500 transition hover:bg-slate-100"
					title={m.close()}
					aria-label={m.close()}
					onclick={close}
				>
					<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" class="h-5 w-5" aria-hidden="true">
						<path d="M12.5 4 7 10l5.5 6" />
					</svg>
				</button>
				<div class="relative min-w-0 flex-1">
					<input
						bind:this={searchEl}
						class="h-10 w-full rounded-xl border border-slate-200 bg-slate-50 pr-9 pl-3 text-sm focus:border-slate-400 focus:bg-white focus:outline-none"
						placeholder={m.search_placeholder()}
						bind:value={search}
					/>
					{#if search}
						<button
							type="button"
							class="absolute top-1/2 right-1.5 flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-full text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
							title={m.search_clear()}
							aria-label={m.search_clear()}
							onclick={() => {
								search = '';
								searchEl?.focus();
							}}>✕</button>
					{/if}
				</div>
			</header>

			<div class="min-h-0 flex-1 overflow-y-auto pb-4">
				{#if !app.manifest}
					<p class="px-4 py-4 text-sm text-slate-400">{m.loading()}</p>
				{:else}
					{#if !search.trim()}
						<!-- featured views -->
						<p class="px-4 pt-3 pb-1 text-[11px] font-medium tracking-wide text-slate-400 uppercase">
							{m.featured()}
						</p>
						<ul>
							{#each FEATURED as f (f.id)}
								<li>
									<button
										type="button"
										class="flex w-full items-start gap-3 px-4 py-2.5 text-left transition hover:bg-slate-50"
										onclick={() => {
											app.applyFeatured(f);
											close();
										}}
									>
										<FeaturedIcon id={f.id} accent={f.accent} size="h-5 w-5" />
										<span class="min-w-0">
											<span class="block text-sm leading-snug font-medium text-slate-700">{featuredTitle(f)}</span>
											<span class="block text-xs leading-snug text-slate-400">{featuredBlurb(f)}</span>
										</span>
									</button>
								</li>
							{/each}
						</ul>
						<p class="px-4 pt-4 pb-1 text-[11px] font-medium tracking-wide text-slate-400 uppercase">
							{m.browse_catalog()} · {m.layers_count({ count: app.manifest.generated_layers })}
						</p>
					{/if}

					{#if groups.length === 0}
						<p class="px-4 py-4 text-sm text-slate-400">{m.empty_results()}</p>
					{:else}
						{#each groups as group (group.workspace)}
							<details class="group" open={!!search.trim()}>
								<summary
									class="flex cursor-pointer items-center gap-2.5 px-4 py-2.5 transition select-none hover:bg-slate-50"
								>
									<span
										class="inline-block h-2.5 w-2.5 shrink-0 rounded-full"
										style="background:{workspaceColor(group.workspace)}"
									></span>
									<span class="min-w-0 flex-1 truncate text-sm font-medium text-slate-700">
										{workspaceLabel(group.workspace, locale)}
									</span>
									<span class="shrink-0 text-xs tabular-nums text-slate-400">{group.layers.length}</span>
									<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" class="h-3.5 w-3.5 shrink-0 text-slate-300 transition group-open:rotate-180" aria-hidden="true">
										<path d="m4 6 4 4 4-4" />
									</svg>
								</summary>
								<ul class="pb-1">
									{#each group.layers as l (l.key)}
										{@const on = app.active.includes(l.key)}
										{@const dead = l.serve === 'empty'}
										<li class="flex items-center gap-1 pr-2 pl-4">
											<button
												type="button"
												class="flex h-auto min-w-0 flex-1 items-start gap-2.5 rounded-lg py-2 pl-2 text-left transition
												       {dead ? 'opacity-40' : 'hover:bg-slate-50'}"
												disabled={dead}
												onclick={() => pickLayer(l)}
											>
												<span
													class="mt-0.5 flex h-4.5 w-4.5 shrink-0 items-center justify-center rounded-md border text-[11px] leading-none
													       {on
														? 'border-emerald-600 bg-emerald-600 text-white'
														: 'border-slate-300 text-transparent'}"
													aria-hidden="true">✓</span>
												<span class="min-w-0">
													<span class="block truncate text-sm leading-snug text-slate-700" title={titleOf(l)}>{leafTitle(l)}</span>
													<span class="flex items-center gap-1.5 text-[11px] text-slate-400">
														{#if categoryOf(l)}
															<span class="max-w-[55%] shrink truncate rounded bg-slate-100 px-1.5 py-px text-[10px] font-medium text-slate-500">{categoryOf(l)}</span>
														{/if}
														<span class="shrink-0">{#if dead}{m.no_geometry()}{:else}{m.feature_count({ count: l.feature_count })}{/if}</span>
													</span>
												</span>
											</button>
											<button
												type="button"
												class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
												title={m.details()}
												aria-label={m.details()}
												aria-haspopup="dialog"
												onclick={() => (app.infoLayer = l)}>&#9432;</button>
										</li>
									{/each}
								</ul>
							</details>
						{/each}
					{/if}
				{/if}
			</div>
		</div>
	</div>
{/if}

<style>
	.browser {
		inset: 0;
	}
	@media (min-width: 768px) {
		.browser {
			inset: auto;
			left: 1rem;
			top: 4.5rem;
			bottom: 1rem;
			width: 420px;
			border-radius: 1rem;
		}
	}
</style>
