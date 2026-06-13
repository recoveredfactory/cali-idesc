// The curated front door: ~10 hand-picked "views" that demo the catalog well.
// Each card applies one or more layers WITH preset styling (color-by field,
// 3D extrusion, relief) and moves the camera — one tap from a blank map to
// something that makes sense. Edit freely: titles/blurbs live here (not in
// paraglide) so adding a card is a one-stop change.

export type FeaturedLayerRef = {
	key: string;
	/** Preset "color by" field (must exist in the layer's field_ranges/categories). */
	colorField?: string;
	/** Extrude in 3D by this numeric field. */
	extrudeField?: string;
};

export type Featured = {
	id: string;
	emoji: string;
	title_es: string;
	title_en: string;
	blurb_es: string;
	blurb_en: string;
	layers: FeaturedLayerRef[];
	/** Turn the DEM relief on for this view. */
	relief?: boolean;
	/** Camera override; otherwise the map fits the first layer's bbox. */
	camera?: { center: [number, number]; zoom: number; pitch?: number };
};

export const FEATURED: Featured[] = [
	{
		id: 'loma',
		emoji: '⛰️',
		title_es: 'Lo demás es loma',
		title_en: 'The rest is hillside',
		blurb_es: 'El relieve de Cali con sus curvas de nivel, del valle a los Farallones.',
		blurb_en: "Cali's terrain with its contour lines, from the valley to the Farallones.",
		layers: [{ key: 'pot_2014__bcs_curvas_nivel' }],
		relief: true,
		camera: { center: [-76.58, 3.41], zoom: 11.6 }
	},
	{
		id: 'edificios-3d',
		emoji: '🏙️',
		title_es: 'La ciudad en 3D',
		title_en: 'The city in 3D',
		blurb_es: 'Cada construcción de Cali, levantada según su número de pisos.',
		blurb_en: 'Every building in Cali, raised by its number of floors.',
		layers: [{ key: 'catastro__cat_bas_construcciones', extrudeField: 'npisos' }],
		camera: { center: [-76.5315, 3.4516], zoom: 15.2, pitch: 55 }
	},
	{
		id: 'trafico',
		emoji: '🚗',
		title_es: '¿A qué velocidad va el tráfico?',
		title_en: 'How fast does traffic move?',
		blurb_es: 'Velocidad promedio en la hora pico de la mañana, vía por vía (2015).',
		blurb_en: 'Average speed in the morning peak hour, road by road (2015).',
		layers: [{ key: 'dapm_movilidad__mv_aiv_cv_vpm_hpm', colorField: 'vpm_hpm' }]
	},
	{
		id: 'congestion',
		emoji: '🛑',
		title_es: '¿Dónde se traba el tráfico?',
		title_en: 'Where traffic jams up',
		blurb_es: 'Nivel de servicio vial en la hora pico AM: de A (fluido) a F (colapsado).',
		blurb_en: 'Road level of service in the morning peak: from A (free-flowing) to F (gridlock).',
		layers: [{ key: 'dapm_movilidad__mv_aiv_cv_ns_hpm', colorField: 'los_hpm' }]
	},
	{
		id: 'mio',
		emoji: '🚌',
		title_es: 'El MIO',
		title_en: 'The MIO',
		blurb_es: 'Rutas troncales y estaciones del transporte masivo.',
		blurb_en: 'Trunk routes and stations of the bus rapid transit system.',
		layers: [
			{ key: 'metrocali__sitm_rutas_troncales' },
			{ key: 'metrocali__sitm_estaciones', colorField: 't_estacion' }
		]
	},
	{
		id: 'estratos',
		emoji: '🏘️',
		title_es: 'Los estratos de Cali',
		title_en: "Cali's strata",
		blurb_es: 'Cada predio coloreado por su estrato socioeconómico, de 1 (bajo) a 6 (alto).',
		blurb_en: 'Every property colored by its socioeconomic stratum, 1 (low) to 6 (high).',
		layers: [{ key: 'dapm__pdt_est_estrato_urbano_expansion', colorField: 'estestrato' }]
	},
	{
		id: 'crecimiento',
		emoji: '📈',
		title_es: 'La ciudad que crece',
		title_en: 'The growing city',
		blurb_es: 'El perímetro urbano en 1962, 1980, 1991 y 2000: anillos de una ciudad en expansión.',
		blurb_en: 'The urban perimeter in 1962, 1980, 1991 and 2000: rings of an expanding city.',
		layers: [{ key: 'idesc__mc_perimetro_urbano_anno_2000', colorField: 'anno' }]
	},
	{
		id: 'inundacion',
		emoji: '🌊',
		title_es: 'Amenaza por inundación',
		title_en: 'Flood hazard',
		blurb_es: 'Zonas de amenaza por inundación fluvial según la CVC.',
		blurb_en: 'River-flood hazard zones according to the CVC.',
		layers: [
			{ key: 'gestion_riesgo__gri_cri_amenaza_inundacion_fluvial_cvc', colorField: 'aiftipame' }
		]
	},
	{
		id: 'arboles',
		emoji: '🌳',
		title_es: 'El bosque urbano',
		title_en: 'The urban forest',
		blurb_es: 'Densidad de árboles en el área urbana, según el censo arbóreo.',
		blurb_en: 'Tree density across the urban area, from the tree census.',
		layers: [{ key: 'dagma__obs_arb_densidad_arborea', colorField: 'valor' }]
	},
	{
		id: 'ruido',
		emoji: '🔊',
		title_es: '¿Dónde suena Cali?',
		title_en: 'Where is Cali loud?',
		blurb_es: 'Zonas de ruido entre semana, de día: cada polígono por su nivel en decibelios.',
		blurb_en: 'Weekday daytime noise zones: each polygon by its level in decibels.',
		layers: [
			{ key: 'expediente_municipal__emc_amb_sos_ruido_semana_diurno', colorField: 'laeq_db' }
		]
	},
	{
		id: 'bici',
		emoji: '🚲',
		title_es: 'Cali en bici',
		title_en: 'Cali by bike',
		blurb_es: 'La red de cicloinfraestructura, por tipo de vía.',
		blurb_en: 'The bike-infrastructure network, by type.',
		layers: [{ key: 'movilidad__mt_tt_red_cicloinfraestructura', colorField: 'tipredcic' }]
	},
	{
		id: 'comunas',
		emoji: '🗺️',
		title_es: 'Comunas y barrios',
		title_en: 'Comunas & neighborhoods',
		blurb_es: 'Las 22 comunas y los 339 barrios que arman la ciudad.',
		blurb_en: 'The 22 comunas and 339 neighborhoods that make up the city.',
		layers: [{ key: 'idesc__mc_comunas' }, { key: 'idesc__mc_barrios' }]
	}
];
