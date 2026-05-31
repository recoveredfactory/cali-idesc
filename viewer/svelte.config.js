import adapter from '@sveltejs/adapter-static';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	compilerOptions: {
		// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
		runes: ({ filename }) => filename.split(/[/\\]/).includes('node_modules') ? undefined : true
	},
	// SPA mode: the viewer is entirely client-side (MapLibre is browser-only),
	// so prerender to a single index.html fallback.
	kit: { adapter: adapter({ fallback: 'index.html' }) }
};

export default config;
