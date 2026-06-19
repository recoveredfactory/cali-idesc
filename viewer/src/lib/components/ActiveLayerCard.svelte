<script lang="ts">
	// One enabled layer in the dock: identity row (tap = fly to it) with
	// remove/info, plus a progressive style panel — color-by, 3D, legend —
	// that only appears when the layer actually supports it.
	import { m } from '$lib/paraglide/messages';
	import type { Layer } from '$lib/config';
	import {
		workspaceColor,
		fitToLayer,
		colorableFields,
		hasColorableFields,
		extrudableFields,
		defaultExtrudeField,
		defaultLineWidth
	} from '$lib/map';
	import { fieldLabel } from '$lib/fields';
	import { workspaceLabel } from '$lib/workspaces';
	import { app } from '$lib/state/app.svelte';
	import { track } from '$lib/analytics';
	import { leafTitle, titleOf, locale } from '$lib/i18n';
	import LegendBlock from './LegendBlock.svelte';

	let {
		layer,
		onStyleOpen,
		desktop = false,
		showGrip = false,
		dragging = false,
		onGripDown
	}: {
		layer: Layer;
		onStyleOpen?: () => void;
		desktop?: boolean;
		/** Show the drag-reorder grip (only when more than one layer is active). */
		showGrip?: boolean;
		/** This card is the one currently being dragged. */
		dragging?: boolean;
		/** Pointer-down on the grip — the dock owns the reorder gesture. */
		onGripDown?: (e: PointerEvent) => void;
	} = $props();

	const style = $derived(app.styleByKey[layer.key] ?? {});
	const colorable = $derived(hasColorableFields(layer));
	const extrudable = $derived(extrudableFields(layer).length > 0);
	// Layers that draw a line/outline (lines + polygons; unknown geometries draw
	// both) can have their stroke width tuned. Pure point layers can't.
	const lineable = $derived(/line|polygon|unknown/.test((layer.geometry_type ?? '').toLowerCase()));
	const styleable = $derived(colorable || extrudable || lineable);

	// Pre-styled featured / shared-link layers auto-open their style panel ON
	// DESKTOP, where the legend is worth the room. On a phone several open panels
	// (one per layer) ate the whole sheet and left no room for the map, so there
	// they start closed — tap the style button to reveal the controls + legend.
	let open = $state(false);
	$effect.pre(() => {
		if (desktop && (style.colorField || style.extrude || style.lineWidth != null)) open = true;
	});

	const fLabel = (f: string) => fieldLabel(layer.workspace, f, locale);
</script>

<div
	class="overflow-hidden rounded-xl border bg-white shadow-sm transition
	       {dragging ? 'border-emerald-300 shadow-lg ring-2 ring-emerald-200' : 'border-black/5'}"
>
	<div class="flex items-center gap-2 py-1.5 pr-1.5 {showGrip ? 'pl-1' : 'pl-3'}">
		{#if showGrip}
			<button
				type="button"
				class="flex h-8 w-5 shrink-0 cursor-grab touch-none items-center justify-center text-slate-300 transition hover:text-slate-500 active:cursor-grabbing"
				title={m.reorder_layer()}
				aria-label={m.reorder_layer()}
				onpointerdown={onGripDown}
			>
				<svg viewBox="0 0 16 16" fill="currentColor" class="h-4 w-4" aria-hidden="true">
					<circle cx="6" cy="3" r="1.3" /><circle cx="10" cy="3" r="1.3" />
					<circle cx="6" cy="8" r="1.3" /><circle cx="10" cy="8" r="1.3" />
					<circle cx="6" cy="13" r="1.3" /><circle cx="10" cy="13" r="1.3" />
				</svg>
			</button>
		{/if}
		<span
			class="h-2.5 w-2.5 shrink-0 rounded-full {layer.key === app.randomKey ? 'ring-2 ring-violet-300' : ''}"
			style="background:{workspaceColor(layer.workspace)}"
		></span>
		<button
			type="button"
			class="min-w-0 flex-1 py-1 text-left"
			title="{titleOf(layer)} — {m.zoom_to_layer()}"
			onclick={() => app.map && fitToLayer(app.map, layer)}
		>
			<span class="block truncate text-sm leading-snug font-medium text-slate-700">{leafTitle(layer)}</span>
			<span class="block truncate text-[11px] text-slate-400">
				{workspaceLabel(layer.workspace, locale)} · {m.feature_count({ count: layer.feature_count })}
			</span>
		</button>
		{#if styleable}
			<button
				type="button"
				class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition
				       {open ? 'bg-emerald-50 text-emerald-700' : 'text-slate-400 hover:bg-slate-100 hover:text-slate-700'}"
				title={m.style_layer()}
				aria-label={m.style_layer()}
				aria-expanded={open}
				onclick={() => {
					open = !open;
					if (open) onStyleOpen?.();
				}}
			>
				<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" class="h-4 w-4" aria-hidden="true">
					<path d="M3 6h14M3 10h14M3 14h14" />
					<circle cx="7" cy="6" r="1.8" fill="currentColor" stroke="none" />
					<circle cx="13" cy="10" r="1.8" fill="currentColor" stroke="none" />
					<circle cx="9" cy="14" r="1.8" fill="currentColor" stroke="none" />
				</svg>
			</button>
		{/if}
		<button
			type="button"
			class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
			title={m.details()}
			aria-label={m.details()}
			aria-haspopup="dialog"
			onclick={() => {
				app.infoLayer = layer;
				track('layer-info', { key: layer.key });
			}}>&#9432;</button>
		<button
			type="button"
			class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-slate-400 transition hover:bg-rose-50 hover:text-rose-600"
			title={m.remove_layer()}
			aria-label={m.remove_layer()}
			onclick={() => app.disable(layer.key)}>✕</button>
	</div>

	{#if open && styleable}
		<div class="space-y-2 border-t border-black/5 px-3 py-2.5">
			{#if colorable}
				{@const cf = colorableFields(layer)}
				<div>
					<label class="flex items-center gap-2">
						<span class="shrink-0 text-[11px] font-medium text-slate-500">{m.color_by()}</span>
						<select
							class="h-8 min-w-0 flex-1 rounded-lg border border-slate-200 bg-white px-2 text-xs text-slate-700"
							title={m.color_by_hint()}
							value={style.colorField ?? ''}
							onchange={(e) => app.setColorField(layer, e.currentTarget.value)}
						>
							<option value="">{m.color_flat()}</option>
							{#if cf.numeric.length}
								<optgroup label={m.color_numeric()}>
									{#each cf.numeric as f (f)}<option value={f}>{fLabel(f)}</option>{/each}
								</optgroup>
							{/if}
							{#if cf.categorical.length}
								<optgroup label={m.color_categories()}>
									{#each cf.categorical as f (f)}<option value={f}>{fLabel(f)}</option>{/each}
								</optgroup>
							{/if}
						</select>
					</label>
					{#if style.colorField}
						<LegendBlock {layer} />
					{/if}
				</div>
			{/if}
			{#if extrudable}
				<div class="flex items-center gap-2">
					<button
						type="button"
						class="h-8 shrink-0 rounded-lg border px-2.5 text-xs font-medium transition
						       {style.extrude
							? 'border-amber-500 bg-amber-500 text-white'
							: 'border-slate-200 text-slate-500 hover:bg-slate-50'}"
						title={m.extrude_hint()}
						aria-pressed={!!style.extrude}
						onclick={() => app.toggleExtrude(layer)}>{m.extrude_3d()}</button>
					{#if style.extrude && extrudableFields(layer).length > 1}
						<select
							class="h-8 min-w-0 flex-1 rounded-lg border border-slate-200 bg-white px-2 text-xs text-slate-700"
							title={m.extrude_field()}
							value={style.extrudeField ?? defaultExtrudeField(layer) ?? ''}
							onchange={(e) => app.setExtrudeField(layer, e.currentTarget.value)}
						>
							{#each extrudableFields(layer) as f (f)}
								<option value={f}>{fLabel(f)}</option>
							{/each}
						</select>
					{/if}
				</div>
			{/if}
			{#if lineable}
				<label class="flex items-center gap-2">
					<span class="shrink-0 text-[11px] font-medium text-slate-500">{m.line_width()}</span>
					<input
						type="range"
						class="h-8 min-w-0 flex-1 accent-emerald-600"
						min="0"
						max="8"
						step="0.2"
						title={m.line_width_hint()}
						value={style.lineWidth ?? defaultLineWidth(layer)}
						oninput={(e) => app.setLineWidth(layer, +e.currentTarget.value)}
						onchange={(e) => track('line-width', { key: layer.key, width: +e.currentTarget.value })}
					/>
					<span class="w-7 shrink-0 text-right text-[11px] tabular-nums text-slate-400"
						>{(style.lineWidth ?? defaultLineWidth(layer)).toFixed(1)}</span
					>
				</label>
			{/if}
		</div>
	{/if}
</div>
