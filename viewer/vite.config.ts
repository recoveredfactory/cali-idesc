import { paraglideVitePlugin } from '@inlang/paraglide-js';
import tailwindcss from '@tailwindcss/vite';
import { sveltekit } from '@sveltejs/kit/vite';
import Icons from 'unplugin-icons/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [
		tailwindcss(),
		sveltekit(),
		// Material Symbols (and any Iconify set) as bundled, tree-shaken Svelte
		// components — imported as `~icons/<collection>/<name>`. Resolved offline
		// at build time from @iconify/json, no runtime API fetch.
		Icons({ compiler: 'svelte' }),
		paraglideVitePlugin({
			project: './project.inlang',
			outdir: './src/lib/paraglide',
			strategy: ['localStorage', 'preferredLanguage', 'baseLocale']
		})
	]
});
