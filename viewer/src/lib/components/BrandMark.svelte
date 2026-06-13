<script lang="ts">
	// Text-only wordmark for now — "lo demás es mapa", a riff on the saying
	// "Cali es Cali, lo demás es loma". (A Farallones-silhouette glyph may land
	// here later.)
	let { textClass = 'text-[15px]' }: { textClass?: string } = $props();
</script>

<span class="{textClass} font-serif leading-none font-medium tracking-tight whitespace-nowrap">
	lo demás es <span class="italic">mapa</span>
</span>
