# Cómo contribuir

¡Gracias por tu interés en *Cali — lo demás es mapa*! Es un proyecto cívico y de
código abierto, publicado **para estudio y reutilización**.

## Formas de aportar

- **Reportar un problema** del visor (un error, una capa que no carga, una
  traducción rara): abre un *issue*.
- **Señalar un dato incorrecto** que venga del IDESC: ábrelo también como *issue*.
  Muchas veces conviene corregirlo en la fuente (IDESC); aquí lo documentamos y,
  cuando se puede, lo manejamos en el `pipeline/`.
- **Proponer una mejora o una capa nueva**: abre un *issue* con la idea antes de
  escribir mucho código, para acordar el enfoque.
- **Enviar código**: haz un *fork*, crea una rama y abre un *pull request*.

## Levantar el proyecto

El [`README.md`](README.md) tiene las instrucciones completas. En resumen:

- **`pipeline/`** (Python + `uv` + Dagster) descarga y procesa los datos.
  Requiere `uv`, GDAL ≥ 3.4 y `tippecanoe`.
- **`viewer/`** (SvelteKit + MapLibre) es el visor. Requiere Node ≥ 22.12 y `pnpm`.

Los **datos no están en el repo** (son grandes y se regeneran): el `pipeline/`
los reconstruye desde los servicios públicos del IDESC.

## Antes de abrir un pull request

- Mantén los *commits* pequeños y enfocados, con mensajes claros.
- En el visor, deja pasar `pnpm check` y `pnpm build` sin errores.
- Los textos de interfaz son bilingües (es/en): si tocas uno, actualiza
  `viewer/messages/es.json` **y** `viewer/messages/en.json`.
- Este espacio se rige por el [Código de conducta](CODE_OF_CONDUCT.md).

## Licencia

Al contribuir, aceptas que tu aporte se publique bajo la licencia [MIT](LICENSE)
del proyecto.
