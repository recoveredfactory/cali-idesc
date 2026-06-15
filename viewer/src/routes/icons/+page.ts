// The rest of the app is a client-only SPA (MapLibre needs the browser), but
// this icon-comparison page is pure SVG — prerender it so it renders without JS
// (and can be screenshotted / served statically). Override the layout's ssr=off.
export const ssr = true;
export const prerender = true;
