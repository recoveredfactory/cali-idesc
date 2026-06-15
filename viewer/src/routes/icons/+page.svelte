<script lang="ts">
	// TEMPORARY icon-set comparison. Open /icons to compare the three candidates
	// for the featured cards, then tell me which to adopt — I'll wire it into
	// FeaturedIcon.svelte and delete this route. Icons resolve offline at build
	// time from @iconify/json via unplugin-icons.
	import { FEATURED } from '$lib/featured';
	import { featuredTitle } from '$lib/i18n';

	// --- Material Symbols (current — monochrome, tinted with the card accent) ---
	import MsLoma from '~icons/material-symbols/landscape-rounded';
	import MsEdif from '~icons/material-symbols/apartment-rounded';
	import MsTraf from '~icons/material-symbols/speed-rounded';
	import MsCong from '~icons/material-symbols/traffic-rounded';
	import MsMio from '~icons/material-symbols/directions-bus-rounded';
	import MsEstr from '~icons/material-symbols/layers-rounded';
	import MsCrec from '~icons/material-symbols/trending-up-rounded';
	import MsInun from '~icons/material-symbols/flood-rounded';
	import MsArb from '~icons/material-symbols/forest-rounded';
	import MsRuido from '~icons/material-symbols/volume-up-rounded';
	import MsBici from '~icons/material-symbols/directions-bike-rounded';
	import MsCom from '~icons/material-symbols/map-rounded';
	import MsSurp from '~icons/material-symbols/shuffle-rounded';

	// --- Solar Bold Duotone (two-tone, tinted with the card accent) -------------
	import SoLoma from '~icons/solar/earth-bold-duotone';
	import SoEdif from '~icons/solar/buildings-2-bold-duotone';
	import SoTraf from '~icons/solar/spedometer-max-bold-duotone';
	import SoCong from '~icons/solar/traffic-bold-duotone';
	import SoMio from '~icons/solar/bus-bold-duotone';
	import SoEstr from '~icons/solar/layers-minimalistic-bold-duotone';
	import SoCrec from '~icons/solar/chart-2-bold-duotone';
	import SoInun from '~icons/solar/water-bold-duotone';
	import SoArb from '~icons/solar/leaf-bold-duotone';
	import SoRuido from '~icons/solar/soundwave-bold-duotone';
	import SoBici from '~icons/solar/bicycling-bold-duotone';
	import SoCom from '~icons/solar/map-bold-duotone';
	import SoSurp from '~icons/solar/magic-stick-3-bold-duotone';

	// --- Streamline Color (full multicolor — rendered as-is, no tint) -----------
	import ScLoma from '~icons/streamline-color/landscape-2-flat';
	import ScEdif from '~icons/streamline-color/building-2-flat';
	import ScTraf from '~icons/streamline-color/dashboard-3-flat';
	import ScCong from '~icons/streamline-color/traffic-cone-flat';
	import ScMio from '~icons/streamline-color/bus-flat';
	import ScEstr from '~icons/streamline-color/add-layer-2-flat';
	import ScCrec from '~icons/streamline-color/arrow-expand-flat';
	import ScInun from '~icons/streamline-color/clean-water-and-sanitation-flat';
	import ScArb from '~icons/streamline-color/tree-3-flat';
	import ScRuido from '~icons/streamline-color/announcement-megaphone-flat';
	import ScBici from '~icons/streamline-color/bicycle-bike-flat';
	import ScCom from '~icons/streamline-color/map-fold-flat';
	import ScSurp from '~icons/streamline-color/dice-3-flat';

	const ROWS = [
		{ id: 'loma', ms: MsLoma, so: SoLoma, sc: ScLoma },
		{ id: 'edificios-3d', ms: MsEdif, so: SoEdif, sc: ScEdif },
		{ id: 'trafico', ms: MsTraf, so: SoTraf, sc: ScTraf },
		{ id: 'congestion', ms: MsCong, so: SoCong, sc: ScCong },
		{ id: 'mio', ms: MsMio, so: SoMio, sc: ScMio },
		{ id: 'estratos', ms: MsEstr, so: SoEstr, sc: ScEstr },
		{ id: 'crecimiento', ms: MsCrec, so: SoCrec, sc: ScCrec },
		{ id: 'inundacion', ms: MsInun, so: SoInun, sc: ScInun },
		{ id: 'arboles', ms: MsArb, so: SoArb, sc: ScArb },
		{ id: 'ruido', ms: MsRuido, so: SoRuido, sc: ScRuido },
		{ id: 'bici', ms: MsBici, so: SoBici, sc: ScBici },
		{ id: 'comunas', ms: MsCom, so: SoCom, sc: ScCom },
		{ id: 'surprise', ms: MsSurp, so: SoSurp, sc: ScSurp }
	];
	const byId = new Map(FEATURED.map((f) => [f.id, f]));
	const accentOf = (id: string) => (id === 'surprise' ? '#7c3aed' : (byId.get(id)?.accent ?? '#64748b'));
	const labelOf = (id: string) =>
		id === 'surprise' ? 'Sorpréndeme' : (byId.has(id) ? featuredTitle(byId.get(id)!) : id);

	const COLS = [
		{ key: 'ms', name: 'Material Symbols', note: 'current · Apache-2.0 · mono, tinted' },
		{ key: 'so', name: 'Solar Bold Duotone', note: 'CC BY 4.0 · two-tone, tinted' },
		{ key: 'sc', name: 'Streamline Color', note: 'CC BY 4.0 · full multicolor' }
	] as const;
</script>

<div class="mx-auto max-w-3xl p-6 font-sans text-slate-800">
	<h1 class="text-xl font-bold">Featured icon sets — comparison</h1>
	<p class="mt-1 text-sm text-slate-500">
		Temporary preview. Mono &amp; duotone sets are tinted with each card's accent; Streamline keeps
		its own colors. Pick one and I'll wire it into <code>FeaturedIcon.svelte</code>.
	</p>

	<div class="mt-6 grid grid-cols-[10rem_repeat(3,1fr)] gap-px overflow-hidden rounded-xl border border-slate-200 bg-slate-200 text-center">
		<div class="bg-slate-50"></div>
		{#each COLS as c (c.key)}
			<div class="bg-slate-50 px-2 py-3">
				<div class="text-sm font-semibold">{c.name}</div>
				<div class="text-[11px] leading-tight text-slate-400">{c.note}</div>
			</div>
		{/each}

		{#each ROWS as r (r.id)}
			{@const Ms = r.ms}
			{@const So = r.so}
			{@const Sc = r.sc}
			<div class="flex items-center bg-white px-3 py-3 text-left text-xs font-medium text-slate-600">
				{labelOf(r.id)}
			</div>
			<div class="flex items-center justify-center bg-white py-3">
				<Ms class="h-8 w-8" style="color:{accentOf(r.id)}" />
			</div>
			<div class="flex items-center justify-center bg-white py-3">
				<So class="h-8 w-8" style="color:{accentOf(r.id)}" />
			</div>
			<div class="flex items-center justify-center bg-white py-3">
				<Sc class="h-8 w-8" />
			</div>
		{/each}
	</div>
</div>
