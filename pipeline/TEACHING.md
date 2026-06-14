# Dagster en 10 minutos — "lo demás es datos"

Una clase corta y práctica. Dos formas de definir lo mismo:

## 1. La forma normal: assets en Python (`src/cali_geo/defs/`)

Cada `@dg.asset` es un paso del pipeline. Las dependencias se declaran y Dagster
dibuja el grafo (linaje), corre los pasos en orden, y revisa la calidad con
*asset checks*.

```
wfs_catalog ──► layer_translations ─┐
     │                              ├─► viewer_manifest
     └─► layer_geojson ─► layer_pmtiles ─► (dem_relief) ─┘
```

Mira `defs/catalog.py` y `defs/layers.py`: `@dg.asset`, `deps=[...]`,
`check_specs=[...]`, particiones dinámicas, recursos (`WfsResource`). Todo eso
es Dagster moderno (modelo *asset-centric*).

## 2. La forma nueva: **componentes** (escribe el comportamiento una vez, declara en YAML)

Cuando muchos assets comparten el mismo comportamiento, no copies código:
escribe un **Component** una vez y declara instancias en YAML.

- **El tipo** vive en `src/cali_geo/components/wfs_layer_set.py` (registrado por
  `registry_modules` en `pyproject.toml`).
- **La instancia** vive en `src/cali_geo/defs/featured_layers/defs.yaml`.

Agregar una capa = agregar tres líneas de YAML. Sin tocar Python:

```yaml
type: cali_geo.components.WfsLayerSet
attributes:
  layers:
    - typename: idesc:mc_comunas
      title: Comunas de Cali
```

## El demo en vivo (la parte "esto va a dominar tu mundo de datos")

```bash
cd pipeline
uv sync                 # o: pip install -e ".[dev]"
dg dev                  # abre http://localhost:3000
```

1. Muestra el grafo: los 4 assets de `featured` salieron del YAML.
2. Edita `defs.yaml`, agrega una capa, recarga → aparece un asset nuevo.
3. Materializa `idesc__mc_comunas` → el check `has_features` se pone verde
   (Cali tiene **22 comunas**).

Misma idea que los assets en Python, pero declarativa: el código define el
*cómo*, el YAML define el *qué*.
