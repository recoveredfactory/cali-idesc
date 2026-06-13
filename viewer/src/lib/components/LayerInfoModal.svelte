<script lang="ts">
	// Layer details: abstract + the field glossary (friendly label, raw code,
	// description) for everything the layer carries.
	import { fade } from 'svelte/transition';
	import { m } from '$lib/paraglide/messages';
	import { app } from '$lib/state/app.svelte';
	import { workspaceColor } from '$lib/map';
	import { workspaceLabel } from '$lib/workspaces';
	import { fieldDef, fieldLabel } from '$lib/fields';
	import { locale, titleOf, abstractOf } from '$lib/i18n';

	const layer = $derived(app.infoLayer);

	const fDesc = (ws: string, f: string) => {
		const d = fieldDef(ws, f);
		return d ? ((locale === 'en' ? d.desc_en : d.desc_es) ?? '') : '';
	};
</script>

{#if layer}
	<div class="absolute inset-0 z-50 flex items-center justify-center p-4" transition:fade={{ duration: 150 }}>
		<button
			type="button"
			class="absolute inset-0 cursor-default bg-black/40"
			aria-label={m.close()}
			onclick={() => (app.infoLayer = null)}
		></button>
		<div
			class="relative flex max-h-[86dvh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl"
			role="dialog"
			aria-modal="true"
			aria-label={m.details()}
		>
			<div class="flex items-start gap-2 border-b border-black/10 px-5 pt-4 pb-3.5 md:px-6">
				<span
					class="mt-1.5 inline-block h-2.5 w-2.5 shrink-0 rounded-full"
					style="background:{workspaceColor(layer.workspace)}"
				></span>
				<div class="min-w-0 flex-1">
					<h2 class="text-base leading-tight font-semibold text-slate-800 md:text-lg">{titleOf(layer)}</h2>
					<p class="mt-0.5 text-xs text-slate-500">
						{workspaceLabel(layer.workspace, locale)}
						<span class="text-slate-300">·</span>
						<code class="font-mono text-[10px] text-slate-400">{layer.workspace}</code>
						{#if layer.geometry_type}
							· {layer.geometry_type}{/if}{#if layer.serve !== 'empty'}
							· {m.feature_count({ count: layer.feature_count })}{/if}
					</p>
				</div>
				<button
					type="button"
					class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
					title={m.close()}
					aria-label={m.close()}
					onclick={() => (app.infoLayer = null)}>✕</button>
			</div>

			<div class="min-h-0 flex-1 overflow-y-auto px-5 py-4 md:px-6">
				<p class="text-sm leading-relaxed text-slate-600">
					{abstractOf(layer) || m.no_description()}
				</p>

				{#if layer.fields?.length}
					<h3 class="mt-5 mb-1 text-xs font-medium tracking-wide text-slate-500 uppercase">
						{m.attributes()}
						<span class="text-slate-400 normal-case">({layer.fields.length})</span>
					</h3>
					<dl class="divide-y divide-slate-100">
						{#each layer.fields as f (f)}
							{@const hasDef = !!fieldDef(layer.workspace, f)}
							{@const desc = fDesc(layer.workspace, f)}
							<div class="py-2">
								<dt class="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
									<span class="text-sm font-medium text-slate-800">{fieldLabel(layer.workspace, f, locale)}</span>
									{#if hasDef}
										<code class="font-mono text-[10px] text-slate-400">{f}</code>
									{/if}
									{#if layer.numeric_fields?.includes(f)}
										<span
											class="rounded bg-amber-100 px-1 text-[9px] font-semibold text-amber-700"
											title={m.numeric_field()}>#</span>
									{/if}
								</dt>
								{#if desc}
									<dd class="mt-0.5 text-[12px] leading-snug text-slate-500">{desc}</dd>
								{/if}
							</div>
						{/each}
					</dl>
				{/if}
			</div>
		</div>
	</div>
{/if}
