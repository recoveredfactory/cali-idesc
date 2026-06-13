// Smart default styling: pick a sensible "color by" field for a layer the user
// just turned on from the browser or the 🎲 surprise roll, so it arrives looking
// intentional instead of a flat workspace-color blob. Curated `featured` views
// keep their hand-picked styling — this only fills in the un-styled ad-hoc adds.
//
// It scores the layer's colorable fields (numeric ranges + categorical domains)
// and returns the best one, or nothing when no field is clearly meaningful —
// deliberately conservative, since a wrong auto-pick is worse than a flat layer.
// Identifiers, geometry-derived measures (areas, lengths, coordinates), dates and
// foreign-key code columns are excluded; decoded glossary fields and recognized
// "value" semantics (estrato, speed, decibels, density, …) are preferred.

import type { Layer } from './config';
import type { LayerStyle } from './state/app.svelte';
import { fieldDef } from './fields';

// Never color by these — pure identifiers / housekeeping columns.
const EXCLUDE =
	/^(gid|objectid|fid|id|cod|codigo|punto|registro|comuna|barrio|corregimiento|vereda|sector|manzana|gridcode|anno|anio|ano)$/i;
// Foreign-key / coded id columns (prefer their decoded text sibling).
const ID_LIKE = /(^id_|_id$|idpred|idpredi|idredcic|^aifid$|stopid|id_perim)/i;
// Geometry-derived or coordinate measures — not thematic values.
const GEOM_LIKE =
	/(^area$|_area$|shape_|_leng$|perimetro|perímetro|longitud|latitud|^lon$|^lat$|coord|^km|_km$)/i;
const DATE_LIKE = /(fecha|^fec_|_fecha$|fecpub|date|^a_\d{4}$)/i;
// Numeric names that read as a real magnitude worth a ramp.
const VALUE_NUM =
	/(valor|densidad|^laeq|_db$|^vpm|^vmix|^vvm|nivel|^npisos$|^pisos$|altura|poblac|cantidad|^total$|conteo|^n_|carriles|cupos)/i;
// Names that look like a class/type/status — good categorical color-bys.
const TYPEY = /(tip|clas|categor|estado|nivel|jerarq|sentido|servic|tipolog|red|estrato|los_)/i;

function scoreField(layer: Layer, field: string, kind: 'numeric' | 'categorical'): number {
	if (EXCLUDE.test(field) || ID_LIKE.test(field) || GEOM_LIKE.test(field) || DATE_LIKE.test(field)) {
		return -Infinity;
	}
	let s = 0;
	if (fieldDef(layer.workspace, field)) s += 50; // decoded in the glossary → meaningful
	if (kind === 'numeric') {
		if (VALUE_NUM.test(field)) s += 30;
	} else {
		const n = (layer.field_categories?.[field] ?? []).length;
		if (n >= 2 && n <= 8) s += 18; // a tidy legend
		else if (n <= 12) s += 6;
		else s -= 20; // too many categories to read
		if (/id/i.test(field)) s -= 12; // coded id sibling, prefer the decoded one
	}
	if (TYPEY.test(field)) s += 10;
	return s;
}

/** Recommend a default style (currently just a color-by field) for an ad-hoc
 *  layer add. Returns `{}` when nothing scores well enough to beat a flat fill. */
export function autoStyle(layer: Layer): LayerStyle {
	let bestField: string | undefined;
	let bestScore = -Infinity;
	const consider = (field: string, score: number) => {
		if (score > bestScore) {
			bestScore = score;
			bestField = field;
		}
	};
	for (const [f, r] of Object.entries(layer.field_ranges ?? {})) {
		if (!Array.isArray(r) || !(r[1] > r[0])) continue; // degenerate range → nothing to graduate
		consider(f, scoreField(layer, f, 'numeric'));
	}
	for (const [f, vals] of Object.entries(layer.field_categories ?? {})) {
		if (!vals || vals.length < 2) continue;
		consider(f, scoreField(layer, f, 'categorical'));
	}
	return bestField && bestScore >= 15 ? { colorField: bestField } : {};
}
