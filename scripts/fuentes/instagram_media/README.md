# Carteles Instagram (fallback sin Apify)

Meta suele bloquear el scrape público (429 / login wall). Si el conector no
puede leer el perfil en vivo, usa las imágenes de esta carpeta:

```
instagram_media/<handle>/*.{jpg,jpeg,png,webp}
```

Handles de Malgrat:

- `laguardadelllibre/` — La Guarda del Llibre
- `ajmalgrat/` — Ajuntament
- `visitmalgratdemar/` — Visit Malgrat de Mar
- `bibliomalgrat/` — Biblioteca La Cooperativa

Ejemplo: `laguardadelllibre/carteles_guarda.png`

El pipeline las envía al LLM multimodal (cartel-OCR) y genera eventos.
Cuando Meta dé 429, deposita carteles aquí y reingesta con
`--url-contains instagram.com`.

## Cómo actualizar los carteles (proceso manual)

1. Abre el perfil en el navegador (con sesión de Instagram si hace falta):
   `https://www.instagram.com/<handle>/`
2. Descarga las imágenes de los posts que anuncien actividades (click derecho
   → "Guardar imagen como…", o desde la vista del post). Solo carteles con
   texto: fecha, lugar, hora. Fotos sin datos no aportan.
3. Déjalas en la carpeta del handle con un nombre reconocible y fecha:
   `<handle>/<yyyymmdd>-<descripcion-corta>.jpg`
   Ejemplo: `ajmalgrat/20260918-barrakes-sant-roc.jpg`
4. Borra los carteles de eventos ya pasados: el fingerprint local usa
   nombre+mtime+tamaño, así que cualquier cambio en la carpeta fuerza
   reingesta del lote completo en el siguiente run.
5. Reingesta solo Instagram:
   `python scripts/ingest_all.py --target local --poblacion "Malgrat de Mar" --url-contains instagram.com`

## Cadencia recomendada

- Una vez por semana (p. ej. lunes) para captar la programación del finde.
- Antes de festes majors o festivales (Sant Roc, Libèl·lula), repaso extra.

## Notas

- Máximo por lote: `INSTAGRAM_MAX_POSTS` (20 por defecto). Si hay más
  carteles, prioriza los más recientes.
- Formatos: jpg, jpeg, png, webp. Los ficheros que empiezan por `.` se ignoran.
- Si el scrape en vivo funciona (Meta no bloquea), estas carpetas no se usan:
  el live tiene prioridad.
