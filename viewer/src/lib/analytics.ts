// Thin, typed wrapper over Umami's global `window.umami.track`. App state lives
// in the URL hash (not routes), so Umami auto-tracks ~one pageview per visit —
// these custom events are the real signal for how the map gets used.
//
// Everything here is a safe no-op when the Umami script is absent: in dev (the
// `data-domains` attribute on the tag stops sends from any non-prod host), when
// an ad blocker drops the script, or before it has loaded. It is also SSR-safe
// (the app is client-only, but we guard `typeof window` anyway) and never
// throws — `track` calls sit at the top of hot state methods, so a broken
// analytics call must never break the app.

/** Low-cardinality dimension. Keep payloads tiny — Umami stores event data as
 *  columns and has practical key/size limits. Never send free text or PII. */
type Str = string;

/** The curated event taxonomy: name → payload shape. `key` is a layer key
 *  (e.g. "idesc__mc_comunas"); `field` a field name. Events whose payload is
 *  `void` take no data argument. Names are kebab-case so they read cleanly in
 *  the Umami dashboard and don't collide visually with the snake_case field
 *  names that appear inside payloads (e.g. `los_hpm`). */
export type AnalyticsEvents = {
	// The first real action of a visit — the single best "front door" signal.
	// Emitted automatically by `track` (see below), not by callers.
	'first-action': { action: AnalyticsEvent };
	// --- layer actions ---
	'layer-enable': { key: Str };
	'layer-disable': { key: Str };
	'layers-clear': void;
	// --- featured / discovery ---
	'featured-apply': { id: Str };
	surprise: { key: Str };
	// --- styling ---
	'color-by': { key: Str; field: Str | null };
	'extrude-toggle': { key: Str; on: boolean };
	'exaggeration-change': { value: number };
	'line-width': { key: Str; width: number };
	'layer-reorder': { key: Str };
	// --- view / 3D ---
	'dem-toggle': { on: boolean };
	'basemap-toggle': { on: boolean };
	'theme-pick': { theme: Str };
	'view-reset': void;
	// --- inspection ---
	'feature-inspect': { key: Str; geometry: Str };
	// --- navigation / UI ---
	'browser-open': void;
	'about-open': void;
	'layer-info': { key: Str };
	// --- language ---
	'language-set': { locale: Str };
};

export type AnalyticsEvent = keyof AnalyticsEvents;

/** Umami's global, present only after script.js loads on a tracked domain. */
type UmamiGlobal = {
	track: ((event: string, data?: Record<string, unknown>) => void) &
		((payload: Record<string, unknown>) => void);
};

declare global {
	interface Window {
		umami?: UmamiGlobal;
	}
}

/** Master switch. Flipped off during shared-link restore so replaying a link
 *  doesn't log a burst of fake user actions (see the boot guard in +page). */
let enabled = true;
export function setAnalyticsEnabled(on: boolean): void {
	enabled = on;
}

/** Whether the one-time `first-action` event has already fired this visit. */
let firstActionFired = false;

/**
 * Fire a typed custom event. No-ops safely if disabled, server-side, or if the
 * Umami script hasn't loaded (dev / blocked / untracked domain). The first real
 * (enabled, non-suppressed) call of a visit also emits a one-time `first-action`
 * event naming what the user did first.
 */
export function track<E extends AnalyticsEvent>(
	event: E,
	...args: AnalyticsEvents[E] extends void ? [] : [data: AnalyticsEvents[E]]
): void {
	if (!enabled) return;
	if (typeof window === 'undefined') return;
	const u = window.umami;
	if (!u) return; // script blocked / not loaded / untracked domain
	try {
		if (!firstActionFired) {
			firstActionFired = true;
			u.track('first-action', { action: event });
		}
		const data = args[0] as Record<string, unknown> | undefined;
		if (data) u.track(event, data);
		else u.track(event);
	} catch {
		// Analytics must never break the app.
	}
}

/**
 * Trailing-edge debounce for high-frequency events (the exaggeration slider
 * fires on every `oninput` tick). Returns a stable function.
 */
export function debounce<A extends unknown[]>(
	fn: (...a: A) => void,
	ms = 400
): (...a: A) => void {
	let t: ReturnType<typeof setTimeout> | undefined;
	return (...a: A) => {
		if (t) clearTimeout(t);
		t = setTimeout(() => fn(...a), ms);
	};
}
