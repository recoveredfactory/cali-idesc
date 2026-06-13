<script lang="ts">
	// One Material Symbol per featured view, tinted with the view's accent color.
	// Icons are bundled at build time by unplugin-icons (no runtime fetch); to add
	// a card, map its id to a `~icons/material-symbols/<name>` import here.
	import Landscape from '~icons/material-symbols/landscape-rounded';
	import Apartment from '~icons/material-symbols/apartment-rounded';
	import Speed from '~icons/material-symbols/speed-rounded';
	import Traffic from '~icons/material-symbols/traffic-rounded';
	import Bus from '~icons/material-symbols/directions-bus-rounded';
	import Layers from '~icons/material-symbols/layers-rounded';
	import Trending from '~icons/material-symbols/trending-up-rounded';
	import Flood from '~icons/material-symbols/flood-rounded';
	import Forest from '~icons/material-symbols/forest-rounded';
	import Volume from '~icons/material-symbols/volume-up-rounded';
	import Bike from '~icons/material-symbols/directions-bike-rounded';
	import MapIcon from '~icons/material-symbols/map-rounded';
	import Shuffle from '~icons/material-symbols/shuffle-rounded';

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
