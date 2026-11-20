# Mockup v2 — cambios en el crawl y en `contenidos.xml`

**Fecha:** 07-11-2026 · **Origen:** `Ideas cambios buscador con IA.docx` (revisión del
amigo) y `Fuentes_buscador_IA_Viajero_Animalista.xlsx` (87 fuentes curadas).
**Decisiones del product owner (07-11-2026):** enriquecimiento con OpenAI real
(cuenta de Albert), entran también las webs sin RSS, noticias de los últimos
10 días, sin fichas de adopción ni de directorio, el blog propio va por su
lado, muestra de 250 a 300 contenidos, catálogo de municipios y playas de
ejemplo con la costa del Maresme.

---

## 1. Qué cambia respecto a la v1

| Área | v1 (12-10-2026) | v2 |
| --- | --- | --- |
| Fuentes | 6 consultas Google News + 5 feeds | 67 fuentes del Excel (39 RSS, 21 listados HTML, 7 páginas de recurso) + 10 consultas Google News |
| Enriquecimiento | A mano | OpenAI `gpt-4.1-mini` con JSON Schema estricto, mismo patrón que KM0 |
| Descubrimiento en listados sin RSS | No existía | LLM interpreta el listado y devuelve los enlaces candidatos |
| Tipos | 3 usados (NOTICIA, EVENTO, INICIATIVA) | 5: `NOTICIA`, `EVENTO`, `INICIATIVA`, `CAMPANA`, `RECURSO` |
| Temas | 9 | 15 (ver §3) |
| Animales | 9 | 11 (`exoticos` se divide en reptiles y anfibios, peces y acuáticos, otros) |
| Ámbito | NACIONAL, CCAA, PROVINCIA, MUNICIPIO, MULTI | `ESTATAL`, `AUTONOMICO`, `PROVINCIAL`, `MUNICIPAL`, `VARIOS` |
| Fuente que publica | Nombre de la fuente | Grupo de fuente (11 grupos) + nombre y enlace dentro de la ficha |
| Entidad | Un solo campo | `publica` (quien publica) y `organiza` (quien organiza), separados |
| Geografía | Solo lo referenciado | Las 19 CCAA y 52 provincias completas; catálogo de municipios con código INE; catálogo de playas |
| Lugar | Un solo concepto | `rol="OCURRE"` (dónde pasa) o `rol="AFECTA"` (a qué territorio afecta). Nunca se asigna un municipio por la sede de la entidad |
| Eventos | Fechas | `estado` calculado (PROXIMO, EN_CURSO, FINALIZADO) o de la fuente (CANCELADO, APLAZADO) + horario, precio, organiza, inscripción, condiciones, acceso con animales |
| Campañas | No existían | entidad impulsora, cómo participar, enlace oficial, fecha límite |
| Recursos | No existían | autoría, última actualización, botón "Consultar recurso original" |
| Información interna | Mezclada con la pública | Agrupada en `<interno>`: relevancia, scores, procedencia, notas, "aportó extracción" |
| Caducidad | 10 días | Igual: la ventana del crawl son los 10 días anteriores a la fecha de ejecución. Eventos futuros se conservan aunque se anunciaran antes |
| Enlace con la web del amigo | No existía | `codigoINE` en cada municipio y `urlFicha` construida con una plantilla configurable en la cabecera; playas enlazadas por catálogo |

## 2. Cambios en el script (`crawl_mockup_v2.py`)

Flujo, en orden. Todo lo descargado se cachea en el scratchpad para poder
repetir el enriquecimiento sin volver a descargar.

1. **Fuentes.** Lee `fuentes_v2.json` (derivado del Excel más la comprobación en vivo del 07-11-2026). Cada fuente tiene `modo`: `rss`, `listado`, `pagina` o `google_news`. Las redes sociales, el blog propio, el directorio Miwuki y las inaccesibles llevan `excluir` y no se procesan.
2. **Captura.** `robots.txt` por dominio. `rss`: se parsea el feed y se toman los ítems con fecha dentro de la ventana. `listado`: se descarga la página, se limpia a texto con enlaces y el LLM devuelve los ítems candidatos con su URL y fecha. `pagina`: la propia URL es un candidato de tipo recurso. `google_news`: se decodifican los enlaces de redirección como en la v1.
3. **Filtro barato.** URL repetida, fecha fuera de la ventana (salvo eventos, que se evalúan por fecha de celebración), dominio no permitido por robots. Cada descarte se cuenta por fuente y motivo.
4. **Artículo.** Descarga única, extracción de título, fecha, descripción y primeros párrafos. HTTP 403 o sin texto se cuentan como descarte.
5. **Clasificación y enriquecimiento** en una sola llamada por artículo con esquema estricto: relevante y relevancia, motivo de descarte, tipo, título normalizado, resumen de tres frases, fecha, quién publica y quién organiza, bloque de evento, campaña o recurso según el tipo, ámbito, lugares con rol, playas mencionadas, temas con principal, animales con principal, etiquetas, procedencia por campo y nota de calidad. El prompt prohíbe inventar y exige `null` cuando el dato no consta.
6. **Resolución geográfica** sin LLM contra el maestro INE: municipio por nombre normalizado, desambiguado por provincia si el texto la da o por la provincia de referencia de la fuente; si sigue ambiguo se sube a provincia. Alias de prensa (Vizcaya, Catalunya, Mallorca…).
7. **Playas.** Si el texto menciona una playa del catálogo y el municipio coincide, se enlaza.
8. **Deduplicación.** Embeddings de título más resumen; coseno por encima de 0,90 con el mismo tipo y fechas a menos de 7 días se fusiona como fuente adicional, nunca se borra.
9. **Estado de eventos** por fecha de ejecución.
10. **Salida.** `contenidos.xml` v2, `run.json` con costes y descartes, y `descartes.csv`.

## 3. Taxonomía v2

**Tipos:** `NOTICIA` (Noticia y reportaje), `EVENTO` (Evento y actividad),
`INICIATIVA` (Iniciativa pública), `CAMPANA` (Campaña y participación),
`RECURSO` (Recurso y guía práctica). Tipo principal único; temas múltiples.
Una jornada de un ayuntamiento es `EVENTO`, no `INICIATIVA`.

**Temas (15):** `adopcion-proteccion`, `salud-bienestar`,
`comportamiento-educacion`, `legislacion`, `turismo-viajes`,
`naturaleza-rutas`, `playas-caninas`, `espacios-convivencia`,
`ocio-actividades-deporte`, `educacion-divulgacion`, `fauna-conservacion`,
`sociedad-historias`, `colonias-felinas-cer`, `maltrato-abandono`,
`protectoras-santuarios`.

**Animales (11):** `perros`, `gatos`, `pequenos-mamiferos`, `aves`,
`reptiles-anfibios`, `caballos-equidos`, `granja`, `fauna-silvestre`,
`peces-acuaticos`, `otros`, `general`.

**Grupos de fuente (11):** `ayuntamientos`, `organismos` (diputaciones,
gobiernos autonómicos y organismos estatales), `protectoras`, `santuarios`,
`asociaciones`, `medios`, `portales`, `profesionales`, `empresas`,
`creadores`, `otras`.

**Ámbitos (5):** `ESTATAL`, `AUTONOMICO`, `PROVINCIAL`, `MUNICIPAL`, `VARIOS`.

**Estados de evento:** `PROXIMO`, `EN_CURSO`, `FINALIZADO`, `CANCELADO`, `APLAZADO`.

## 4. Estructura del XML v2

```
viajeroAnimalista @version=0.2 @generado @ventanaDias @urlFichaMunicipio @urlFichaPlaya
  taxonomia/ tiposContenido, temas, animales, ambitos, gruposFuente, estadosEvento, procedencias
  geo/ ccaa (19) / provincia (52)
  catalogoMunicipios/ municipio @codigoINE @nombre @provincia @ccaa @slug @urlFicha
  catalogoPlayas/ playa @id @nombre @municipioINE @municipio @slug @urlFicha @fuente @nota
  fuentes/ fuente @id @nombre @grupo @modo @url @rss @activa @vistos @aportados @descartados @estado @ultimoError
  contenidos @total
    contenido @id @tipo
      titulo, resumen, fechaPublicacion, ultimaActualizacion?, idiomaOrigen
      evento? @fechaInicio @fechaFin @horario @lugar @precio @esGratuito @inscripcion @condiciones @accesoAnimales @estado
      campana? @entidadImpulsora @comoParticipar @enlaceOficial @fechaLimite
      recurso? @autoria @ultimaActualizacion
      publica @nombre @grupo
      organiza? @nombre @tipo
      ambito
      ubicacion/ lugar @nivel @codigoINE @nombre @provincia @ccaa @rol @principal @urlFicha?
      playas?/ playa @ref @nombre @urlFicha
      animales/ animal @slug @principal
      temas/ tema @slug @principal
      etiquetas/ etiqueta
      fuentes/ fuente @ref @medio @url @principal @fecha
      interno/ @relevancia @motivoCalidad ; procedencia @campo=valor ; scores ; notaCalidad ; fuentesAportoExtraccion
  ejecucion @id @inicio @fin @modelo @costeUsd @llamadasLlm @tokensIn @tokensOut @fuentesOk @fuentesError @candidatos @contenidos @descartados
    descartes/ descarte @motivo @cantidad / muestra @fuente @titulo @url
    coberturaGeo/ ccaa @nombre @contenidos
```

Reglas para Lovable: todo lo que cuelga de `<interno>` solo se ve en el
panel; los atributos ausentes no se muestran o se muestran como "No consta"
cuando el campo es esperable para ese tipo; la ficha pública lleva la frase
"Resumen elaborado con ayuda de inteligencia artificial a partir de las
fuentes enlazadas".

## 5. Enlace con la web de Viajero Animalista (propuesta)

- **Municipios.** La clave es el código INE de cinco cifras, no el CIF del ayuntamiento. Cada `lugar` de nivel municipio lleva `codigoINE` y `urlFicha`, construida con la plantilla `urlFichaMunicipio` de la cabecera (`{codigoINE}` y `{slug}` disponibles). Héctor solo tiene que cambiar la plantilla por la ruta real de sus fichas, o publicar un CSV `codigoINE;url` que sustituya la plantilla.
- **Playas.** El catálogo `catalogoPlayas` lo mantendría la propia web del amigo. Para la muestra se incluye un catálogo de ejemplo de la costa del Maresme con nombre, municipio, código INE y una `urlFicha` de plantilla. Un contenido enlaza con una playa cuando el texto la nombra y el municipio coincide.
- **Varios municipios.** `ubicacion` admite varios `lugar`; la ficha municipal de cada uno podría listar los contenidos que lo citan filtrando por `codigoINE`.
- **Coste para ellos.** Un endpoint `/api/v1/animalista/contenidos?municipio=08121` en la fase de producto, y un `<script>` o componente en su web. Sin cambios en su modelo de datos si ya usan INE; si usan otro identificador, una tabla de equivalencias.

## 6. Decisiones tomadas durante el crawl (07-11-2026)

- **robots.txt se aplica a páginas HTML, no a feeds.** Un RSS o una consulta de Google News es sindicación que la web ofrece a lectores; se lee sin consultar robots. Los listados HTML de Blanes, Diputació de Barcelona y Generalitat quedan bloqueados por sus robots.txt y se registran como descarte `ROBOTS`.
- **Sin reintentos ante 403.** Un sitio que bloquea la descarga automática queda como descarte `HTTP_ERROR`; no se cambia de identidad para esquivarlo.
- **Rescate de eventos antiguos.** Un ítem del feed con más de 10 días cuyo título sugiere evento (jornada, feria, taller, marcha…) se lee igualmente, hasta 60 días atrás, por si anuncia una fecha futura.
- **Fecha en el texto.** Cuando faltan metadatos, se busca `<time datetime>` o una fecha escrita («7 de noviembre de 2026», catalán y gallego incluidos) en los primeros 4.000 caracteres.
- **Normativa europea aplicable en España** se considera relevante; el resto de hechos fuera de España se descarta por geografía.
- **Consultas regionales** en Google News (8 por bloques de comunidades + 2 temáticas) para equilibrar la cobertura territorial.

- **Post-filtro geográfico.** Si el ámbito no es estatal, el LLM cita lugares y ninguno existe en el maestro INE, el contenido se descarta como `NO_RELEVANTE_GEO`. Tapó fugas de México y Colombia que el clasificador había aceptado.
- **Recursos sin fecha.** Un recurso puede no llevar `fechaPublicacion`; la demo muestra «No consta». Máximo 5 recursos por fuente para que un portal de guías no domine la muestra.
- **24 consultas Google News** en total: 10 generales, 8 regionales y 14 temáticas, con tope de 100 ítems por consulta.

## 7. Pendiente de verificar tras el crawl

- Volumen real por fuente en una ventana de 10 días (muchas asociaciones publican poco).
- Ruido de Google News fuera de España y de notas de prensa comerciales.
- Fuentes en catalán: calidad del resumen en castellano.
- Las 8 fuentes inaccesibles hoy (Affinity, Igualdad Animal, GEMFE, Herpetológica, Diario de Madrid, Baleària, Trasmed, blog propio).
