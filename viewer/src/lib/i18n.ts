// Locale-aware helpers shared by every component. `setLocale` reloads the
// page (paraglide strategy), so reading the locale once per module load is
// safe — there is no live locale switching to react to.

import { getLocale } from '$lib/paraglide/runtime';
import type { Layer, Theme } from './config';
import type { Featured } from './featured';

export const locale = getLocale();

export const titleOf = (l: Layer): string =>
	locale === 'en' ? l.title_en || l.title_es : l.title_es || l.title_en;

export const abstractOf = (l: Layer): string =>
	(locale === 'en' ? l.abstract_en || l.abstract_es : l.abstract_es || l.abstract_en) ?? '';

/** The identifying tail of a title. Titles read "Area - Category - Sub:
 *  Specific name"; the part after the last ':' is what actually distinguishes
 *  the layer. Falls back to the full title. */
export const leafTitle = (l: Layer): string => {
	const t = titleOf(l);
	const i = t.lastIndexOf(':');
	return i >= 0 && t.slice(i + 1).trim() ? t.slice(i + 1).trim() : t;
};

export const themeLabel = (t: Theme): string => (locale === 'en' ? t.label_en : t.label_es);

export const featuredTitle = (f: Featured): string =>
	locale === 'en' ? f.title_en : f.title_es;

export const featuredBlurb = (f: Featured): string =>
	locale === 'en' ? f.blurb_en : f.blurb_es;

/** Compact number formatting (histogram min/max labels, attribute values). */
export function fmtNum(n: number): string {
	const a = Math.abs(n);
	if (a !== 0 && (a >= 100000 || a < 0.01)) return n.toExponential(1);
	return (Math.round(n * 100) / 100).toLocaleString(locale);
}
