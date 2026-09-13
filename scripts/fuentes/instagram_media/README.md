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
