<script lang="ts">
	// Wordmark: "Mapas Cali" set in Dancing Script (weight 600), a flowing script
	// with a hand-lettered feel. Used in the top-bar chip and About; callers size
	// it via `textClass`. (David draws the Farallones himself if/when he wants a
	// glyph alongside it.)
	let { textClass = 'text-lg' }: { textClass?: string } = $props();
</script>

<span class="{textClass} font-script font-semibold leading-none whitespace-nowrap text-emerald-800">
	Mapas Cali
</span>
