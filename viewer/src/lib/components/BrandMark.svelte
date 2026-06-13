<script lang="ts">
	// The wordmark: a small contour-line loma glyph + the name. "Cali es Cali,
	// lo demás es loma" — and this map is mostly about the loma.
	let { glyphClass = 'h-5 w-5', textClass = 'text-[15px]' }: { glyphClass?: string; textClass?: string } = $props();
</script>

<span class="flex items-center gap-2">
	<svg
		viewBox="0 0 24 24"
		fill="none"
		stroke="currentColor"
		stroke-width="1.7"
		stroke-linecap="round"
		class="{glyphClass} shrink-0"
		aria-hidden="true"
	>
		<path d="M2.5 19.5c3-7 6.5-11 9.5-11s6.5 4 9.5 11" />
		<path d="M7 19.5c1.7-4 3.4-6 5-6s3.3 2 5 6" />
		<path d="M10.4 19.5c.6-1.4 1.1-2.1 1.6-2.1s1 .7 1.6 2.1" />
	</svg>
	<span class="{textClass} font-serif italic leading-none tracking-tight whitespace-nowrap">
		lo demás es loma
	</span>
</span>
