// Human-readable glossary for cryptic attribute field names, so the viewer
// "teaches as you go" — friendly labels show wherever a raw field name would.
//
// CONFIDENCE BAR: only HIGH-confidence, unambiguous decodings live here. Coded
// numeric fields with no decoder table in the data (most of the `movilidad`
// signal/sign inventories), and names whose meaning changes across layers (e.g.
// `longitud` = segment length in dapm_movilidad but longitude/route-length in
// metrocali) are deliberately OMITTED — better a raw name than a wrong label.
//
// Lookup is workspace-scoped first (BY_WS), then a COMMON fallback for names
// that mean the same thing everywhere.

export type FieldDef = {
	es: string;
	en: string;
	/** Measurement unit, appended to the label (e.g. "km/h", "m"). */
	unit?: string;
	/** Longer explanation shown as a tooltip / popup hint. */
	desc_es?: string;
	desc_en?: string;
};

// Names consistent across every workspace.
const COMMON: Record<string, FieldDef> = {
	nombre: { es: 'Nombre', en: 'Name' },
	direccion: { es: 'Dirección', en: 'Address' },
	anno: { es: 'Año', en: 'Year' },
	sentido: {
		es: 'Sentido',
		en: 'Direction',
		desc_es: 'Sentido de circulación (rumbo, p. ej. N-S; doble si N-S,S-N).',
		desc_en: 'Direction of travel (compass, e.g. N-S; two-way if N-S,S-N).'
	},
	observaciones: { es: 'Observaciones', en: 'Notes' },
	observacio: { es: 'Observaciones', en: 'Notes' }
};

const BY_WS: Record<string, Record<string, FieldDef>> = {
	// Planning (DAPM): socioeconomic stratification census.
	dapm: {
		estestrato: {
			es: 'Estrato socioeconómico',
			en: 'Socioeconomic stratum',
			desc_es: 'Estrato urbano del predio, 1 (bajo-bajo) a 6 (alto); 8/9 = no residencial.',
			desc_en: 'Urban stratum of the property, 1 (lowest) to 6 (highest); 8/9 = non-residential.'
		},
		erestrato: {
			es: 'Estrato socioeconómico',
			en: 'Socioeconomic stratum',
			desc_es: 'Estrato rural del predio, 1 (bajo-bajo) a 6 (alto); 8/9 = no residencial.',
			desc_en: 'Rural stratum of the property, 1 (lowest) to 6 (highest); 8/9 = non-residential.'
		}
	},
	// 2015 road-network study "Análisis Integral de la Red de Infraestructura Vial".
	dapm_movilidad: {
		id_tramo: { es: 'ID del tramo vial', en: 'Road-segment ID' },
		nombre_via: { es: 'Nombre de la vía', en: 'Road name' },
		jerarquia: {
			es: 'Jerarquía vial',
			en: 'Road hierarchy',
			desc_es: 'Vía arteria principal/secundaria, colectora o local.',
			desc_en: 'Arterial (primary/secondary), collector or local road.'
		},
		n_carriles: { es: 'Número de carriles', en: 'Lanes' },
		tpavimento: {
			es: 'Tipo de pavimento',
			en: 'Pavement type',
			desc_es: 'Flexible, rígido, mixto o sin pavimento.',
			desc_en: 'Flexible, rigid, mixed or unpaved.'
		},
		estado_infraestructura: {
			es: 'Estado de la vía',
			en: 'Road condition',
			desc_es: 'Bueno, regular, malo o sin pavimento.',
			desc_en: 'Good, fair, poor or unpaved.'
		},
		// Peak-hour windows (free-text clock ranges). hp = hora pico.
		hpm: { es: 'Franja hora pico AM', en: 'AM peak window' },
		hpmd: { es: 'Franja hora pico medio día', en: 'Midday peak window' },
		hpt: { es: 'Franja hora pico PM', en: 'PM peak window' },
		// LOS = Level of Service grade A–F (HCM) per peak.
		los_hpm: {
			es: 'Nivel de servicio (AM)',
			en: 'Level of service (AM)',
			desc_es: 'Escala A–F: A = flujo libre, F = congestión total.',
			desc_en: 'Grade A–F: A = free flow, F = gridlock.'
		},
		los_hpmd: {
			es: 'Nivel de servicio (medio día)',
			en: 'Level of service (midday)',
			desc_es: 'Escala A–F: A = flujo libre, F = congestión total.',
			desc_en: 'Grade A–F: A = free flow, F = gridlock.'
		},
		los_hpt: {
			es: 'Nivel de servicio (PM)',
			en: 'Level of service (PM)',
			desc_es: 'Escala A–F: A = flujo libre, F = congestión total.',
			desc_en: 'Grade A–F: A = free flow, F = gridlock.'
		},
		// vpm = velocidad promedio mixto (km/h).
		vpm_hpm: { es: 'Velocidad promedio (AM)', en: 'Avg. speed (AM)', unit: 'km/h' },
		vpm_hpmd: { es: 'Velocidad promedio (medio día)', en: 'Avg. speed (midday)', unit: 'km/h' },
		vpm_hpt: { es: 'Velocidad promedio (PM)', en: 'Avg. speed (PM)', unit: 'km/h' },
		// vmix = volumen vehicular mixto (count) per peak hour.
		vmix_hpm: {
			es: 'Volumen vehicular (AM)',
			en: 'Vehicle volume (AM)',
			unit: 'veh',
			desc_es: 'Conteo de vehículos mixtos en la hora pico.',
			desc_en: 'Mixed-vehicle count in the peak hour.'
		},
		vmix_hpmd: {
			es: 'Volumen vehicular (medio día)',
			en: 'Vehicle volume (midday)',
			unit: 'veh',
			desc_es: 'Conteo de vehículos mixtos en la hora pico.',
			desc_en: 'Mixed-vehicle count in the peak hour.'
		},
		vmix_hpt: {
			es: 'Volumen vehicular (PM)',
			en: 'Vehicle volume (PM)',
			unit: 'veh',
			desc_es: 'Conteo de vehículos mixtos en la hora pico.',
			desc_en: 'Mixed-vehicle count in the peak hour.'
		},
		// Road cross-section element widths (metres). _izq/_der = left/right.
		total_sec: { es: 'Ancho total de sección', en: 'Total cross-section width', unit: 'm' },
		calzada: { es: 'Tipo de calzada', en: 'Carriageway type' },
		and_izq: { es: 'Andén izquierdo', en: 'Sidewalk (left)', unit: 'm' },
		and_der: { es: 'Andén derecho', en: 'Sidewalk (right)', unit: 'm' },
		ciclo_izq: { es: 'Cicloruta izquierda', en: 'Bike lane (left)', unit: 'm' },
		ciclo_der: { es: 'Cicloruta derecha', en: 'Bike lane (right)', unit: 'm' },
		ciclo_sep: { es: 'Separador de cicloruta', en: 'Bike-lane separator', unit: 'm' },
		cmio_izq: { es: 'Carril MIO izquierdo', en: 'MIO bus lane (left)', unit: 'm' },
		cmio_der: { es: 'Carril MIO derecho', en: 'MIO bus lane (right)', unit: 'm' },
		scentral: { es: 'Separador central', en: 'Central median', unit: 'm' },
		cestac_izq: { es: 'Carril de estacionamiento izq.', en: 'Parking lane (left)', unit: 'm' },
		cestac_der: { es: 'Carril de estacionamiento der.', en: 'Parking lane (right)', unit: 'm' },
		carril_serv_izq: { es: 'Carril de servicio izq.', en: 'Service lane (left)', unit: 'm' },
		carril_serv_der: { es: 'Carril de servicio der.', en: 'Service lane (right)', unit: 'm' },
		cdesacel_izq: { es: 'Carril de desaceleración izq.', en: 'Deceleration lane (left)', unit: 'm' },
		cdesacel_der: { es: 'Carril de desaceleración der.', en: 'Deceleration lane (right)', unit: 'm' },
		otro: { es: 'Otro elemento', en: 'Other element', unit: 'm' },
		// Parking-bay inventory.
		largo: { es: 'Largo', en: 'Length', unit: 'm' },
		ancho: { es: 'Ancho', en: 'Width', unit: 'm' },
		n_cupos: { es: 'Número de cupos', en: 'Parking spaces' },
		tp_bahia: {
			es: 'Tipo de bahía',
			en: 'Bay type',
			desc_es: 'Bahía masivo (MIO) o particular.',
			desc_en: 'Mass-transit (MIO) or general-purpose bay.'
		},
		reconocedor: { es: 'Equipo de campo', en: 'Survey crew' }
	},
	// SITM-MIO bus rapid transit (Metro Cali).
	metrocali: {
		stopid: { es: 'ID de parada', en: 'Stop ID' },
		ruta: { es: 'Ruta', en: 'Route' },
		orden_ruta: { es: 'Orden en la ruta', en: 'Stop sequence' },
		t_estacion: {
			es: 'Tipo de estación',
			en: 'Station type',
			desc_es: 'EMC = Estación Mío Cable, EST = Estación, TER = Terminal.',
			desc_en: 'EMC = cable station, EST = station, TER = terminal.'
		},
		corredor: { es: 'Corredor troncal', en: 'Trunk corridor' },
		estado: {
			es: 'Estado',
			en: 'Status',
			desc_es: 'AC = activa, IN = inactiva.',
			desc_en: 'AC = active, IN = inactive.'
		},
		servicio: {
			es: 'Tipo de servicio',
			en: 'Service tier',
			desc_es: 'ALI = alimentador, PRE = pretroncal, EXP = expresa, TRO = troncal.',
			desc_en: 'ALI = feeder, PRE = pre-trunk, EXP = express, TRO = trunk.'
		},
		tipologia: {
			es: 'Tipología de vehículo',
			en: 'Vehicle type',
			desc_es: 'ART = articulado, PAD = padrón, DUA = dual, COM = complementario.',
			desc_en: 'ART = articulated, PAD = standard, DUA = dual, COM = complementary.'
		},
		variante: {
			es: 'Variante de ruta',
			en: 'Route variant',
			desc_es: 'NL = normal, CT = corta, LG = larga, DV = desvío, CV = ciclovía.',
			desc_en: 'NL = normal, CT = short, LG = long, DV = detour, CV = open-streets.'
		},
		dia_tipo: {
			es: 'Días de operación',
			en: 'Days of operation',
			desc_es: 'HAB = hábil, SD = sáb./dom., DF = dom./festivos, HSD = hábil-sáb.-dom.',
			desc_en: 'HAB = weekday, SD = Sat/Sun, DF = Sun/holidays, HSD = weekday-Sat-Sun.'
		},
		franja: {
			es: 'Franja horaria',
			en: 'Service window',
			desc_es: 'PIC = pico, VLL = valle, FDS = fin de semana, ESP = especial.',
			desc_en: 'PIC = peak, VLL = off-peak, FDS = weekend, ESP = special.'
		},
		habil: { es: 'Horario hábil', en: 'Weekday hours' },
		sabado: { es: 'Horario sábado', en: 'Saturday hours' },
		dom_fest: { es: 'Horario dom./festivos', en: 'Sun/holiday hours' }
	}
};

/** The glossary entry for a field in a workspace, or null when undecoded. */
export function fieldDef(workspace: string | undefined, field: string): FieldDef | null {
	return (workspace ? BY_WS[workspace]?.[field] : undefined) ?? COMMON[field] ?? null;
}

/** Friendly label for a field (with unit), or the raw name when undecoded. */
export function fieldLabel(workspace: string | undefined, field: string, locale: string): string {
	const d = fieldDef(workspace, field);
	if (!d) return field;
	const base = locale === 'en' ? d.en : d.es;
	return d.unit ? `${base} (${d.unit})` : base;
}

/** Tooltip text: "raw_name — description", or the raw name when undecoded. */
export function fieldTitle(workspace: string | undefined, field: string, locale: string): string {
	const d = fieldDef(workspace, field);
	if (!d) return field;
	const desc = locale === 'en' ? d.desc_en : d.desc_es;
	return desc ? `${field} — ${desc}` : field;
}
