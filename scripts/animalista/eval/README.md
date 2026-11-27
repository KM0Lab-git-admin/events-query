# Conjunto de evaluación — El Viajero Animalista

`evaluacion.csv` es el conjunto etiquetado a mano con el que se mide la
precisión del clasificador y del enriquecimiento en cada cambio de prompt
(fase 4 del plan). Objetivo: 100 filas antes de dar por calibrado el MVP.

## Columnas

| Columna | Valores |
| --- | --- |
| `id` | Identificador libre, p. ej. `ev-001` |
| `url` | URL real del artículo |
| `medio` | Nombre del medio |
| `fecha_publicacion` | `AAAA-MM-DD` |
| `tipo_esperado` | `NOTICIA`, `EVENTO`, `INICIATIVA`, `RECURSO`, `DESCARTAR` |
| `relevante` | `1` o `0` (relevante para El Viajero Animalista) |
| `tema_principal_esperado` | Slug de `CAT_TEMAS` o vacío si `DESCARTAR` |
| `animales_esperados` | Slugs de `CAT_ANIMALES` separados por coma |
| `ambito_esperado` | `NACIONAL`, `CCAA`, `PROVINCIA`, `MUNICIPIO`, `MULTI` |
| `ccaa_esperada` / `provincia_esperada` / `municipio_esperado` | Código INE o vacío |
| `etiquetado_por` / `fecha_etiquetado` | Trazabilidad del etiquetado |
| `notas` | Por qué es un caso difícil, si lo es |

Separador `;`. Codificación UTF-8.

## Qué incluir

- Casos claros de cada tipo y tema.
- Casos frontera: noticias de Latinoamérica, divulgación sin actualidad,
  notas de prensa de marcas, eventos ya celebrados, ayuntamientos que
  prohíben animales en edificios.
- Al menos 10 contenidos sin ningún lugar explícito (ámbito nacional).

Los 50 contenidos de `docs/animalista-mockup/contenidos.xml` son una
primera fuente de filas: ya están etiquetados.
