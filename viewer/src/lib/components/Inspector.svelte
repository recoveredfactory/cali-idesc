<script lang="ts">
	// Tap-a-feature inspector. Leads with a curated card: the handful of
	// fields the glossary knows how to explain (friendly labels, units), then
	// other populated fields — junk ids and shape_* metrics last, behind
	// "show all". Raw JSON copy stays one tap away.
	import { fly } from 'svelte/transition';
	import { m } from '$lib/paraglide/messages';
	import { app } from '$lib/state/app.svelte';
	import { workspaceColor } from '$lib/map';
	import { workspaceLabel } from '$lib/workspaces';
	import { fieldDef, fieldLabel, fieldTitle } from '$lib/fields';
	import { locale, titleOf, leafTitle, fmtNum } from '$lib/i18n';

	const sel = $derived(app.selected);

	let showAll = $state(false);
	let copied = $state(false);
	$effect.pre(() => {
		// Reset per feature.
		void app.selected;
		showAll = false;
		copied = false;
	});

	// Fields nobody needs up front: synthetic ids + GIS bookkeeping.
	const JUNK = /^(gid|objectid|objectid_\d+|globalid|fid|id)$|^shape_|^se_anno/;

	const isEmpty = (v: unknown) => v === null || v === undefined || v === '';

	/** All candidate fields, ordered: glossary-known → plain populated →
	 *  junk/empty. The curated card shows the first 6; "show all" the rest. */
	const ordered = $derived.by(() => {
		if (!sel) return [] as string[];
		const keys = [...new Set([...(sel.layer?.fields ?? []), ...Object.keys(sel.props)])];
		const score = (k: string) => {
			if (fieldDef(sel.workspace, k) && !isEmpty(sel.props[k])) return 0;
			if (!JUNK.test(k) && !isEmpty(sel.props[k])) return 1;
			if (!isEmpty(sel.props[k])) return 2;
			return 3;
		};
		return keys
			.map((k, i) => ({ k, i, s: score(k) }))
			.sort((a, b) => a.s - b.s || a.i - b.i)
			.map((x) => x.k);
	});
	const CURATED_COUNT = 6;
	const shown = $derived(showAll ? ordered : ordered.slice(0, CURATED_COUNT));

	function fmtValue(k: string, v: unknown): string {
		if (isEmpty(v)) return '—';
		if (typeof v === 'number') return fmtNum(v);
		return String(v);
	}

	async function copyProps() {
		if (!sel) return;
		await navigator.clipboard.writeText(JSON.stringify(sel.props, null, 2));
		copied = true;
		setTimeout(() => (copied = false), 1500);
	}
</script>

{#if sel}
	<section
		class="inspector z-30 flex flex-col bg-white/95 shadow-2xl backdrop-blur"
		transition:fly={{ y: 320, duration: 250 }}
	>
		<header class="flex items-start gap-2.5 border-b border-black/10 px-4 pt-3 pb-2.5">
			<span
				class="mt-1 inline-block h-2.5 w-2.5 shrink-0 rounded-full"
				style="background:{workspaceColor(sel.workspace)}"
			></span>
			<div class="min-w-0 flex-1">
				<h2 class="text-sm leading-snug font-semibold text-slate-800" title={sel.layer ? titleOf(sel.layer) : sel.key}>
					{sel.layer ? leafTitle(sel.layer) : sel.key}
				</h2>
				<p class="truncate text-[11px] text-slate-400">
					{workspaceLabel(sel.workspace, locale)}
					{#if sel.id !== null}· {m.feature_id()} {sel.id}{/if}
					{#if sel.moreCount > 0}· {m.more_here({ count: sel.moreCount })}{/if}
				</p>
			</div>
			<button
				type="button"
				class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
				title={m.close()}
				aria-label={m.close()}
				onclick={() => app.closeInspector()}>✕</button>
		</header>

		<div class="min-h-0 flex-1 overflow-y-auto px-4 py-2">
			<dl class="divide-y divide-slate-100">
				{#each shown as k (k)}
					{@const v = sel.props[k]}
					<div class="grid grid-cols-[42%_58%] gap-2 py-1.5 text-sm">
						<dt
							class="flex min-w-0 items-center text-[11px] leading-snug text-slate-500"
							title={fieldTitle(sel.workspace, k, locale)}
						>
							<span class="truncate">{fieldLabel(sel.workspace, k, locale)}</span>
						</dt>
						<dd class="leading-snug break-words {isEmpty(v) ? 'text-slate-300' : 'text-slate-800'}">
							{fmtValue(k, v)}
						</dd>
					</div>
				{/each}
			</dl>
		</div>

		<footer class="flex items-center gap-2 border-t border-black/10 px-4 py-2">
			{#if ordered.length > CURATED_COUNT}
				<button
					type="button"
					class="rounded-lg bg-slate-100 px-2.5 py-1.5 text-xs font-medium text-slate-600 transition hover:bg-slate-200"
					onclick={() => (showAll = !showAll)}
				>
					{showAll ? m.show_less() : m.show_all({ count: ordered.length })}
				</button>
			{/if}
			<button
				type="button"
				class="ml-auto rounded-lg px-2.5 py-1.5 text-xs text-slate-400 transition hover:bg-slate-100 hover:text-slate-600"
				onclick={copyProps}>{copied ? m.copied() : m.copy_json()}</button>
		</footer>
	</section>
{/if}

<style>
	.inspector {
		position: absolute;
		bottom: 0;
		left: 0;
		right: 0;
		max-height: 62dvh;
		border-top-left-radius: 1rem;
		border-top-right-radius: 1rem;
		overflow: hidden;
	}
	@media (min-width: 768px) {
		.inspector {
			left: auto;
			right: 1rem;
			top: 5rem;
			bottom: auto;
			width: 380px;
			max-height: 70dvh;
			border-radius: 1rem;
		}
	}
</style>
