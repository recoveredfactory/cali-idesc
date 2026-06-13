// Friendly names for the IDESC workspace codes — the raw codes (dapm,
// uaesp, …) mean nothing to a civic audience, so the catalog shows these
// instead. Codes stay visible in layer details for people who know them.

export type WorkspaceLabel = { es: string; en: string };

const LABELS: Record<string, WorkspaceLabel> = {
	bienestar_social: { es: 'Bienestar social', en: 'Social welfare' },
	catastro: { es: 'Catastro', en: 'Cadastre' },
	cultura: { es: 'Cultura', en: 'Culture' },
	dagma: { es: 'Ambiente (DAGMA)', en: 'Environment (DAGMA)' },
	dapm: { es: 'Planeación (DAPM)', en: 'Planning (DAPM)' },
	dapm_movilidad: { es: 'Estudio vial 2015 (DAPM)', en: '2015 road study (DAPM)' },
	deporte_recreacion: { es: 'Deporte y recreación', en: 'Sports & recreation' },
	desarrollo_economico: { es: 'Desarrollo económico', en: 'Economic development' },
	desarrollo_territorial_pc: {
		es: 'Desarrollo territorial',
		en: 'Territorial development'
	},
	educacion: { es: 'Educación', en: 'Education' },
	emru: { es: 'Renovación urbana (EMRU)', en: 'Urban renewal (EMRU)' },
	expediente_municipal: { es: 'Expediente municipal', en: 'Municipal records' },
	gestion_riesgo: { es: 'Gestión del riesgo', en: 'Risk management' },
	idesc: { es: 'Cartografía base (IDESC)', en: 'Base cartography (IDESC)' },
	infraestructura: { es: 'Infraestructura', en: 'Infrastructure' },
	metrocali: { es: 'MIO (Metro Cali)', en: 'MIO transit (Metro Cali)' },
	movilidad: { es: 'Movilidad', en: 'Mobility' },
	pot_2014: { es: 'POT 2014 (ordenamiento)', en: 'POT 2014 (land-use plan)' },
	salud: { es: 'Salud', en: 'Health' },
	seguridad_justicia: { es: 'Seguridad y justicia', en: 'Security & justice' },
	turismo: { es: 'Turismo', en: 'Tourism' },
	uaesp: { es: 'Servicios públicos (UAESP)', en: 'Public services (UAESP)' },
	vivienda: { es: 'Vivienda', en: 'Housing' }
};

export function workspaceLabel(workspace: string, locale: string): string {
	const l = LABELS[workspace];
	if (!l) return workspace;
	return locale === 'en' ? l.en : l.es;
}
