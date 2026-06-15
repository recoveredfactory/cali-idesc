<script lang="ts">
	// One Solar (Bold Duotone) icon per featured view, tinted with the view's
	// accent color — the duotone draws its two shades from currentColor, so a
	// single `color` gives a two-tone fill. Icons are bundled at build time by
	// unplugin-icons (no runtime fetch); to add a card, map its id to a
	// `~icons/solar/<name>-bold-duotone` import here.
	import Landscape from '~icons/solar/earth-bold-duotone';
	import Apartment from '~icons/solar/buildings-2-bold-duotone';
	import Speed from '~icons/solar/spedometer-max-bold-duotone';
	import Traffic from '~icons/solar/traffic-bold-duotone';
	import Bus from '~icons/solar/bus-bold-duotone';
	import Layers from '~icons/solar/layers-minimalistic-bold-duotone';
	import Trending from '~icons/solar/chart-2-bold-duotone';
	import Flood from '~icons/solar/water-bold-duotone';
	import Forest from '~icons/solar/leaf-bold-duotone';
	import Volume from '~icons/solar/soundwave-bold-duotone';
	import Bike from '~icons/solar/bicycling-bold-duotone';
	import MapIcon from '~icons/solar/map-bold-duotone';
	import Shuffle from '~icons/solar/magic-stick-3-bold-duotone';

	let {
		id,
		accent,
		size = 'h-6 w-6'
	}: { id: string; accent?: string; size?: string } = $props();

	const ICONS = {
		loma: Landscape,
		'edificios-3d': Apartment,
		trafico: Speed,
		congestion: Traffic,
		mio: Bus,
		estratos: Layers,
		crecimiento: Trending,
		inundacion: Flood,
		arboles: Forest,
		ruido: Volume,
		bici: Bike,
		comunas: MapIcon,
		surprise: Shuffle
	};
	const Icon = $derived(ICONS[id as keyof typeof ICONS] ?? MapIcon);
</script>

<Icon class="{size} shrink-0" style={accent ? `color:${accent}` : undefined} aria-hidden="true" />
