<script lang="ts">
	// Wordmark: a filled Farallones-silhouette glyph + "lo demás es mapa",
	// a riff on the saying "Cali es Cali, lo demás es loma". The glyph uses
	// currentColor, so the wrapper's text color drives both peaks and type.
	// (Placeholder silhouette — easy to swap for a hand-drawn Farallones.)
	let { textClass = 'text-[15px]', glyphClass = 'h-4 w-auto' }: {
		textClass?: string;
		glyphClass?: string;
	} = $props();
</script>

<span class="inline-flex items-center gap-2 text-emerald-800">
	<svg viewBox="0 0 48 26" class="{glyphClass} shrink-0" fill="currentColor" aria-hidden="true">
		<path d="M0 25 L9 7 L15 15 L23 3 L31 15 L37 10 L44 17 L48 12 L48 25 Z" />
	</svg>
	<span class="{textClass} font-serif leading-none font-medium tracking-tight whitespace-nowrap">
		lo demás es <span class="italic">mapa</span>
	</span>
</span>
