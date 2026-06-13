<script lang="ts">
	// Wordmark: "Mapas Cali", a clean serif lockup. Text-only by design — no
	// glyph. (David draws the Farallones himself if/when he wants a mark.)
	let { textClass = 'text-[15px]' }: { textClass?: string } = $props();
</script>

<span
	class="{textClass} font-serif leading-none font-semibold tracking-tight whitespace-nowrap text-emerald-800"
>
	Mapas <span class="italic">Cali</span>
</span>
