# Plan de mejora del scraping de eventos — Malgrat de Mar

**Fecha:** 18-09-2026 · **Repo:** `events-query` · **Motivo:** la ingesta genera solo 5-7 eventos por ejecución.

---

## 0. La conclusión que condiciona todo el plan

**El techo principal no es el scraper: es la fuente.**

Verificado el 18-09-2026 visitando la web: `ajmalgrat.cat/comunicacio/agenda` **publica 6 eventos futuros en total** (Taller tortuga 19/09, Matinal d'Història 20/09, Aplec de la Sardana 03 y 04/10, La GRAN pantalla 20 y 27/10). No tiene paginación ni botón "veure més". Esos 6 son todo lo que hay.

Y `esdeveniments.cat`, que tienes configurada como fuente alternativa, devuelve **exactamente esos mismos 6 eventos**: es un agregador que scrapea al ajuntament. Aporta cero eventos netos.

Esto significa que **perfeccionar la extracción de la agenda municipal no va a subir la cifra**. Por muy bien que se raspe una página con 6 eventos, salen 6. El plan tiene por tanto tres frentes, en este orden de retorno:

1. **Medir** dónde está realmente el 5-7 (hay tres sitios posibles donde se pierde la cuenta, y uno de ellos no es un bug).
2. **Tapar las fugas** del pipeline actual, que sí las hay y son graves: en un municipio con más agenda, el sistema hoy perdería eventos de verdad.
3. **Ampliar la base de fuentes**, que es lo único que sube el número de forma sostenida.

Una expectativa honesta antes de empezar: Malgrat tiene ~18.000 habitantes. Su agenda pública futura real ronda los **10-30 eventos** en un momento cualquiera, con picos de 50+ en Festa Major. Con las fases 1 y 2 de este plan deberías estabilizarte en **15-25**; con la fase 3, superar los **60 en temporada**. Si el producto necesita más densidad que eso el año entero, la respuesta no es más scraping: es ampliar qué cuenta como "agenda" (§7).

---

## 1. Fase 0 — Medir antes de tocar nada (medio día)

Sin esto, todo lo demás es adivinar. Hay **tres sitios distintos** donde pueden desaparecer los eventos y dan la misma cifra de 5-7:

| Hipótesis | Cómo se comprueba | Si es esto… |
|---|---|---|
| **A. Hay pocos eventos en BD** | `SELECT COUNT(*) FROM EVENTOS_MASTER WHERE Poblacion_Nombre='Malgrat de Mar'` | Es problema de ingesta → fases 1-3 |
| **B. Hay muchos en BD pero la API agrupa** | La API devuelve **una tarjeta por familia** (`es_familia`, con `actividades` anidadas). Comparar el `COUNT(*)` con lo que ves en la app | No hay bug de ingesta: es presentación |
| **C. 5-7 son los *nuevos* de ese run** | La ingesta es **incremental por defecto**. Un run sobre una web que no cambió devuelve 0 | El sistema funciona como está diseñado |

**Comandos exactos:**

```sql
-- ¿Cuántos eventos vivos hay realmente?
SELECT COUNT(*) AS total,
       SUM(CASE WHEN h.ultima >= CURDATE() THEN 1 ELSE 0 END) AS futuros
FROM EVENTOS_MASTER e
LEFT JOIN (SELECT ID_Unico_Evento, MAX(Fecha_Fin) ultima
           FROM EVENTO_HORARIOS GROUP BY ID_Unico_Evento) h
  ON h.ID_Unico_Evento = e.ID_Unico_Evento
WHERE e.Poblacion_Nombre = 'Malgrat de Mar';

-- ¿Cuántas familias? (esto es lo que ve el usuario en la app)
SELECT COUNT(DISTINCT COALESCE(ID_Familia, ID_Unico_Evento))
FROM EVENTOS_MASTER WHERE Poblacion_Nombre = 'Malgrat de Mar';

-- ¿De qué fuente viene cada evento? (para saber qué fuente aporta y cuál no)
SELECT f.Nombre, COUNT(DISTINCT ef.ID_Unico_Evento) AS eventos
FROM EVENTO_FUENTES ef JOIN BIBLIOTECA_FUENTES f ON f.ID_Fuente = ef.ID_Fuente
GROUP BY f.Nombre ORDER BY eventos DESC;
```

```bash
# Run de diagnóstico: ignora incremental y fingerprints, no escribe
python scripts/ingest_all.py --poblacion "Malgrat de Mar" --refresh --dry-run -v
```

De ese run, leer **por fuente** estas tres líneas que el código ya emite:

- `"N eventos en el listado"` (`ingest_all.py:2248`) → cuántos vio el LLM
- `"Omitidos por ya existir en BD: X · fecha pasada: Y · nuevos a procesar: Z"` (`2281`)
- `"Tras fusión (umbral 0.75): M eventos únicos"` (`4391`)

**Lectura del resultado:** si N es alto y X es alto → el problema es el descarte por "ya existe" (§2.1). Si N es bajo ya de entrada → el problema es de captura (§2.3, §2.4). Si N es alto y M mucho menor → el problema es la fusión (§2.2).

> **Comprobación adicional de 1 minuto:** revisar si el cron o el comando habitual lleva `--max-items`. El ejemplo canónico de la documentación es `--max-items 5`, exactamente el orden de magnitud del síntoma, y ese flag **cuenta eventos + noticias juntos** y es un tope duro por población.

---

## 2. Fase 1 — Tapar las fugas del pipeline (2-3 días)

Cinco bugs reales, ordenados por daño. Los dos primeros son destructivos y deberían arreglarse aunque el diagnóstico de la fase 0 apunte a otra cosa.

### 2.1. 🔴 El descarte por "mismo recinto ±1 día" — el más grave

`scripts/ingest_all.py:1074-1082`, dentro de `buscar_evento_existente()`:

```python
if lugar_norm and fecha_d and e.get("lugar") and e.get("fmin"):
    if normalize_place(e["lugar"]) == lugar_norm:
        fmin, fmax = e["fmin"], e["fmax"] or e["fmin"]
        if (fmin - timedelta(days=1)) <= fecha_d <= (fmax + timedelta(days=1)):
            return e
```

Traducido: *"si ya tengo un evento en ese mismo recinto cuya franja de fechas cubre este día, es el mismo evento"* — **sin mirar el título**.

Por qué es catastrófico: `fmin`/`fmax` salen de `MIN()`/`MAX()` sobre **todos** los horarios del evento. Una exposición de "1 de setembre al 31 de desembre" en la Biblioteca crea un rango de cuatro meses en ese recinto. A partir de ahí, **cualquier actividad nueva en la Biblioteca durante cuatro meses se considera ya existente y se descarta sin procesar**. Un municipio concentra su agenda en 4-6 equipamientos (biblioteca, centre cívic, teatre, casal, plaça). Basta un evento de rango largo en cada uno para que la agenda entera quede absorbida.

**Arreglo propuesto:** exigir también similitud de título en ese segundo criterio, y no aplicarlo cuando el evento existente abarca más de N días (un evento-paraguas no debe bloquear su recinto):

```python
if normalize_place(e["lugar"]) == lugar_norm:
    rango_dias = ((e["fmax"] or e["fmin"]) - e["fmin"]).days
    if rango_dias <= 1 and titulos_similares(titulo, e["titulo"], 0.85):
        return e
```

### 2.2. 🔴 La fusión intra-run tiene el mismo defecto

`ingest_all.py:2367-2370`:

```python
if lugar_rep and lugar_c and lugar_rep == lugar_c and fechas_solapan(rep, c):
    return True
```

Dos actividades **distintas**, el mismo sábado, en el mismo Centre Cívic → fusionadas en una. Agravantes verificados:

- `fechas_solapan` devuelve `True` ante fechas malformadas (`675-676`: `except (ValueError, TypeError): return True`) — o sea, falla hacia fusionar.
- `normalize_place` corta en el primer `.`/`,`/`(` (`638-645`): "Biblioteca. Sala A" y "Biblioteca. Sala B" son el mismo sitio.
- `normalize_title` borra el año (`622`) y el ID del evento se deriva de ahí (`682-683`): **"Fira de Sant Roc 2026" y "Fira de Sant Roc 2027" generan el mismo `id_unico`**. Las ediciones se pisan entre años.

**Arreglo:** el mismo criterio de título que en 2.1; dejar de borrar el año en `normalize_title` cuando forma parte del identificador; que `fechas_solapan` falle hacia `False` ante fechas inválidas.

### 2.3. 🟠 El dedupe posterior borra físicamente

`scripts/dedupe_events.py:477-494`: con coseno **≥ 0.90 fusiona automáticamente y borra el perdedor**, sin pasar por el juez LLM. Y el score lleva bonus acumulativos (`+0.04` mismo lugar, `+0.02` mismo organizador, `+0.02` misma fecha), que pueden empujar un 0.88 real por encima del umbral. El texto que se embebe es `"Título. Recinto. descripción"` — dos talleres distintos del mismo centro con descripción boilerplate superan 0.90 con facilidad.

**Arreglo:** (a) subir `DEDUPE_UMBRAL_DUP` a 0.94; (b) pasar **siempre** por el juez LLM antes de una fusión destructiva; (c) cambiar el borrado físico por un borrado lógico (`Estado='FUSIONADO'` + `ID_Fusionado_En`), para que sea auditable y reversible sin volver a pagar LLM.

### 2.4. 🟠 La limpieza de HTML amputa la página

`ingest_all.py:1259-1264`:

```python
for tag in soup(["script","style","head","nav","footer","aside","noscript","iframe","form","header"]):
    tag.decompose()
main = soup.find("main") or soup.find("article") or soup.body or soup
```

Dos fugas:

- **`form` se destruye.** El calendari de la Biblioteca (`bibliotecavirtual.diba.cat/.../cercaCalendari`) es un buscador cuyos resultados viven dentro de un `<form>`. Esa fuente puede estar dando 0 sistemáticamente por esto.
- **`soup.find("article")` coge el PRIMER `<article>`.** En un CMS que envuelve cada evento en su propio `<article>`, esto reduce la agenda entera **a un solo evento**.

**Arreglo:** no eliminar `<form>`; y si no hay `<main>`, elegir el contenedor con **más** `<article>` descendientes, no el primero.

### 2.5. 🟠 Truncado y paginación

- `LLM_MAX_INPUT_CHARS = 20000` (`140`, `1471-1474`): todo lo que caiga después del carácter 20.000 no existe para el extractor. **Arreglo:** trocear el listado en ventanas solapadas y hacer N llamadas, en vez de truncar.
- `LISTADO_MAX_PAGINAS = 4` (`170`) y el paginador solo entiende `?pag=N`/`?page=N` del mismo path (`1365-1369`). No entiende `/page/2/`, `offset=`, ni "cargar más". **Arreglo:** añadir esos patrones y subir el tope.
- El primer error de red corta la paginación entera (`1408-1410`: `break`). **Arreglo:** reintentar y continuar.

### 2.6. 🟡 Descartes silenciosos — el problema de fondo

`ingest_all.py:2257-2260` descarta sin **un solo log** los items sin título, sin fecha, o que no mencionan el municipio. Y los extractores de `app/ingestion/` se tragan errores con `logger.debug` y hasta con `except Exception: pass` (`ical_extract.py:29-30`).

La documentación describe una tabla `AUDITORIA_SCRAPING` con un enum `Motivo_Skip` exactamente para esto, pero **no está implementada**. Mientras no exista, nadie puede responder "¿por qué no salió este evento?".

**Arreglo (el más rentable de toda la fase 1):** un contador por fuente y motivo, volcado al final del run:

```
turismemalgrat.com → 23 en listado · 4 sin fecha · 2 sin municipio
                     · 11 omitidos por existir · 3 fusionados · 3 persistidos
```

Con eso, el próximo diagnóstico dura 30 segundos en vez de una tarde.

### 2.7. 🟡 Bug de eventos en curso (ruta `app/ingestion/`)

`app/ingestion/gate.py:22` filtra por `c.fecha_inicio < today`, cuando la propia documentación dice literalmente: *"Eventos en curso (que empezaron ayer y siguen hoy) sí entran: el filtro es `fecha_fin >= hoy`, no `fecha_inicio >= hoy`"*. Descarta festivales, exposiciones y ciclos ya empezados. `ingest_all.py` sí lo hace bien (`filtrar_futuro`, línea 2424), así que esto solo afecta a quien use `python -m app.ingestion.cli`.

> **Nota de arquitectura:** hay **dos pipelines vivos** en el repo. `app/ingestion/` (1.043 líneas, sin LLM, sin paginación, sin detalle, último commit 5-jun) y `scripts/ingest_all.py` (4.614 líneas, el de producción, commits de septiembre). Mantener los dos cuesta y confunde: la documentación describe mayoritariamente el primero, que es el que **no** se usa. Recomiendo decidir explícitamente cuál muere.

---

## 3. Fase 2 — Fuentes estructuradas (2-4 días, el mejor retorno)

Aquí es donde se gana de verdad, y además es lo que hace escalable el producto a otros municipios.

### 3.1. ⭐ API de Dades Obertes de la Diputació de Barcelona — **verificada y funcionando**

Sin clave, sin registro, actualización diaria. Verificado hoy con datos reales:

```
https://do.diba.cat/api/dataset/actesbiblioteques_ca/format/json/camp-municipi_nom/Malgrat%20de%20Mar/ord-data_inici/desc
```

Devuelve JSON con estos campos por acto: `acte_id`, `titol`, `data_inici`, `data_fi`, `descripcio`, `imatge`, `acte_organitzadors`, `acte_url`, `grup_adreca`, `preu`, `durada`, `observacions_horari`, `dies`, `tipus`, `public`, `inscripcio`, `url_inscripcions`, `rel_municipis`, `rel_temes`, `tags`, `categoria`…

Es decir: **el mismo modelo de datos que necesitas, ya normalizado, sin LLM y sin fragilidad de HTML.**

Datasets disponibles para Malgrat (código INE **08110**): `actesbiblioteques_ca` (126 registros), `exposicions` (2), `actesturisme_ca` (1), más `patrimoni_cultural` (214) y `puntesports` (18) que no son agenda pero sirven para enriquecer lugares.

Trampas ya identificadas, para no perder tiempo:
- El filtro que funciona es `camp-municipi_nom/<nombre>`. El `camp-rel_municipis-like/08110` que usan sus propios enlaces **no filtra** en `/api/` y revienta con error de límite de 10.000 registros.
- La ordenación es `ord-` (no `ordre-`). Sin ella el orden es ascendente y la primera página trae 2024.
- Paginación con `start_item=N`. Formato `json` o `xml`; el `csv` da error.
- El endpoint agregado `/api/tipus/acte/` está parcialmente roto: consultar dataset a dataset.

**Acción:** sustituir el scraping HTML de `bibliotecavirtual.diba.cat` por esta API. Mismo contenido, cero LLM, cero fragilidad.

**Y lo estratégico:** ese mismo endpoint, cambiando el nombre del municipio, cubre **los 311 municipios de la provincia de Barcelona**. Es la diferencia entre integrar una fuente por municipio y una integración para toda la provincia.

### 3.2. Agenda Cultural de Catalunya (Generalitat) — open data + RSS por municipio

Dataset Socrata `rhpv-yr4f`, actualización **horaria**, licencia abierta:

```
https://analisi.transparenciacatalunya.cat/resource/rhpv-yr4f.json?$where=...&$limit=...
```

Volumen esperado para Malgrat: bajo (1-3 eventos; solo recoge actividades culturales destacadas), pero es gratis, estructurado y horario.

Además, `https://agenda.cultura.gencat.cat/ca/rss.html` **permite generar un feed RSS filtrado por municipio**. Son 10 minutos con el navegador: seleccionar Malgrat de Mar y copiar la URL del feed. Sería una fuente RSS municipal pura.

⚠️ Lo que **no** hay que hacer: scrapear el HTML de `agenda.cultura.gencat.cat`. Es una SPA que inyecta los resultados por AJAX; un fetch devuelve siempre 0.

### 3.3. 🔍 El iCal del propio ajuntament — la pista más valiosa sin confirmar

El `robots.txt` de `ajmalgrat.cat` contiene, literalmente:

```
Disallow: /rss/
Disallow: /rssext/
Disallow: /ical/
Disallow: /pdflist/
Crawl-delay: 60
```

**Un CMS no bloquea `/ical/` si no sirve iCal.** Y `https://www.ajmalgrat.cat/rss` (sin barra) devuelve un RSS 2.0 válido con `lastBuildDate` de hoy, aunque con cero items: es el feed genérico sin parámetro de sección.

Si `/ical/agenda` o `/rss/agenda` existen, **es la mejor fuente posible del proyecto**: oficial, estructurada, inmune a cambios de maquetación, coste cero.

No he podido sondearlo: la política de red de esta sesión bloquea ese dominio y las herramientas de fetch respetan el `robots.txt`, que precisamente desautoriza esas rutas. **Y ahí está la cuestión importante:** ese `Disallow` es una instrucción explícita a los crawlers. Antes de rasparlo, lo correcto —y además lo más eficaz— es **pedírselo al ajuntament**. Sois su partner en el piloto: un correo preguntando "¿la agenda se puede exportar en iCal/RSS?" resuelve en un día lo que el scraping no resuelve nunca del todo, y de paso legitima el acceso. El mismo `Crawl-delay: 60` es relevante: si se respeta, pedir 90 páginas del histórico son 90 minutos.

### 3.4. turismemalgrat.com — probable WordPress

La estructura de URLs (`/categoria-gaudeix/agenda-activitats/`) es taxonomía de WordPress. Si lo es, tienes gratis la REST API y el feed:

```
https://turismemalgrat.com/wp-json/wp/v2/types     ← ver si hay un CPT de eventos
https://turismemalgrat.com/categoria-gaudeix/agenda-activitats/feed/
```

Una petición cuesta comprobarlo. No he podido verificarlo desde aquí (timeout del dominio).

### 3.5. Fuentes que hay que retirar

| Fuente | Motivo |
|---|---|
| `esdeveniments.cat` | **Espejo de ajmalgrat.cat**: verificado que devuelve los mismos 6 eventos. Aporta 0 netos |
| `bibliotecavirtual.diba.cat` (HTML) | Sustituida por la API Diba (§3.1), mismo dato sin fragilidad |
| `seu-e.cat`, si está | Verificado: su página de agenda **no contiene ni un evento**, solo enlaza de vuelta al ajuntament |
| `festacatalunya.cat` | Verificado: ficha de Malgrat sin ninguna fecha |
| Histórico de la agenda | Son eventos **pasados**: no sirven para la agenda de la app. Además está paginado al revés (90 páginas, la 1 es diciembre de 2019). Útil solo para detectar recurrencias (§7) |

---

## 4. Fase 3 — Donde está el volumen de verdad (1-2 semanas)

### 4.1. ⭐ Los programas de Festa Major en PDF

Malgrat tiene **dos** festas majors:

| Fiesta | Fechas | Programa |
|---|---|---|
| **Sant Roc** | ~6-17 de agosto | `turismemalgrat.com/gaudeix/festa-major-sant-roc/` + PDF del ajuntament |
| **Sant Nicolau** | **1-8 de diciembre** | PDF en `ajmalgrat.cat/media/repository/noticies/<any>/Documents_pdf/` |

Un programa de festa major trae **30-80 actos de golpe**: más que todas las demás fuentes juntas. Y es contenido que **nunca llega a la agenda web** en formato individual.

Esto es exactamente donde el LLM se gana su coste: extraer eventos estructurados de un PDF maquetado es su punto fuerte, y ya tenéis la pieza (`CARTEL_SCHEMA`, extracción de PDF del Centre Cívic). Falta el disparador: **vigilar `/comunicacio/noticies` en julio y noviembre** y seguir el enlace al PDF.

Encaja además con el modelo de familias que ya tenéis: la festa major es el evento paraguas y los 60 actos sus actividades.

> Ojo con el PDF del Centre Cívic que ya tenéis configurado: verifiqué que la ficha del Centre Cívic en la web municipal **no enlaza ningún PDF de programación**. Si la URL está hardcodeada, probablemente esté caducada y devolviendo 0.

### 4.2. El tejido asociativo — la cola larga

`https://www.ajmalgrat.cat/el-municipi/entitats` es un directorio de **~100 entitats en 5 páginas**, con ficha, web y contacto de cada una. Entre las verificadas: Agrupació Sardanista La Barretina, Ateneu Popular El Rovell, Aula d'Extensió Universitària per a la Gent Gran (conferencias **semanales**), Club d'Atletisme, Club d'Escacs, AMPAs, AAVV.

Recorrer esas 5 páginas **una sola vez** da el mapa completo del tejido asociativo. De ahí salen las 10-15 entitats realmente activas, que son las que programan.

### 4.3. Redes sociales — con honestidad sobre lo que hoy no funciona

Tienes 4 perfiles de Instagram configurados, pero **el scraping de Instagram con `httpx` plano no funciona**: Meta bloquea IPs de datacenter y exige sesión. El propio `fuentes/Malgrat.json` lo admite ("si Meta bloquea (429), usa scripts/fuentes/instagram_media/") y el fallback es **subir carteles JPG a mano**. Eso no es una fuente automatizada.

Tres caminos reales, en orden de preferencia:

1. **Pedir acceso a la Graph API de Meta al propio ajuntament.** Sois su partner del piloto; son sus cuentas. Es legítimo, gratuito y estable. Es, de largo, la mejor opción.
2. **Apify** u otro proveedor de scraping (de pago, ya contemplado en el diseño original como "ruta C").
3. **Desactivar los perfiles IG** y dejar de contarlos como fuente, para que el inventario no mienta.

Handles verificados que merece la pena añadir cuando haya vía de acceso: **`Comissió de Festes Malgrat de Mar` (Facebook)** — la de mayor rendimiento potencial, porque publica el desglose de actos que no llega a la web —, `@malgratjovesensetitol` (Espai Jove, enlazado desde la web oficial), Geganters de Malgrat, Inter Esportiu Malgrat.

**Telegram sí funciona** (la vista `t.me/s/` es HTML estático). Pero está limitado a `TELEGRAM_MAX_PAGINAS = 3` y `TELEGRAM_MAX_DIAS = 14`: en temporada de festa major eso se queda corto. Subirlo es una línea.

---

## 5. Fase 4 — Cambiar el modelo: de raspar a recibir

El scraping siempre será una carrera contra los cambios de maquetación. La jugada estructural, y la que hace viable escalar a más municipios, es **dejar de raspar y empezar a recibir**:

- **Pedir al ajuntament un feed** (iCal/RSS, §3.3) o, mejor, un export. Coste cero, calidad máxima.
- **Definir un contrato mínimo de "feed municipal"** que podáis pedirle a cada nuevo ayuntamiento del roadmap. Cinco campos y un iCal resuelven el 80%.
- **Dejar que las entitats publiquen directamente en KM0 Lab** desde el backoffice que ya tenéis. Convierte el problema de cobertura en producto: la entitat gana difusión, vosotros ganáis el dato en origen.

Y para saber si todo esto funciona, implementar lo que el propio diseño ya definió y quedó pendiente: un **`Coverage_Score` por fuente** y un informe semanal de eventos aportados por fuente. Una fuente que lleva tres semanas aportando 0 tiene que saltar sola.

---

## 6. Resumen ejecutivo del plan

| Fase | Qué | Esfuerzo | Impacto en el número |
|---|---|---|---|
| **0** | Medir: SQL + run `--refresh --dry-run` + revisar `--max-items` | medio día | — (pero decide todo lo demás) |
| **1** | Arreglar descarte por recinto, fusión, dedupe destructivo, `clean_html`, truncado, paginación, instrumentación | 2-3 días | Evita pérdidas; imprescindible para escalar |
| **2** | API Diba, open data Generalitat, sondear iCal del ajuntament, WP REST de turisme; retirar fuentes espejo | 2-4 días | **5-7 → 15-25** |
| **3** | PDFs de festa major, directorio de entitats, vía legítima para redes sociales | 1-2 semanas | **60+ en temporada** |
| **4** | Feed municipal negociado, publicación directa de entitats, `Coverage_Score` | continuo | Sostenibilidad y escalado a otros municipios |

---

## 7. Una pregunta de producto, más allá del scraping

Si tras todo esto Malgrat da 20-25 eventos y la app necesita más densidad, el problema ya no es técnico sino de definición. Tres vetas que hoy no se están tocando y que son estructuradas y de alto volumen:

- **Calendarios deportivos.** Las federaciones catalanas publican los calendarios de liga de cada club local: son decenas de partidos por temporada, con fecha, hora y lugar, en formato estructurado. Para un vecino, "juega el Malgrat este domingo" es agenda.
- **Actividades regulares.** Los cursos del casal, el gimnàs, la ludoteca, la coral, la Aula d'Extensió Universitària (conferencias semanales) son series recurrentes. Modeladas como recurrencia, llenan el calendario sin inventar nada. Vuestro modelo de `EVENTO_HORARIOS` ya lo soporta.
- **Programación de cine y comercio.** La cartelera y las promociones de comercios adheridos (que ya tenéis en el otro backend) son contenido con fecha.

Merece la pena decidir esto antes de invertir semanas en exprimir la última gota del scraping.

---

## Apéndice — Qué está verificado y qué no

**Verificado por mí (18-09-2026):**
- La API de Dades Obertes de la Diba responde y devuelve datos reales de Malgrat, con los campos listados en §3.1.
- El `.env` apunta a MySQL local (no arrancado) y a Railway (`caboose.proxy.rlwy.net:55339`); **ninguno es alcanzable desde esta sesión**, por eso las consultas SQL de la fase 0 las tienes que lanzar tú.
- Todas las referencias a archivo:línea del §2 salen de leer el código del repo.

**Verificado por búsqueda web:**
- La agenda de `ajmalgrat.cat` tiene 6 eventos futuros; `esdeveniments.cat` devuelve los mismos 6.
- El `robots.txt` de `ajmalgrat.cat` lista `/ical/`, `/rss/`, `/rssext/`, `/pdflist/` y `Crawl-delay: 60`.
- El histórico son 90 páginas en orden inverso; el directorio de entitats, 5 páginas.
- Fechas de las dos festas majors y el patrón de URL de sus PDF.

**NO verificado, pendiente de comprobar:**
- Si `/ical/agenda` o `/rss/agenda` existen (bloqueado por red y por `robots.txt` → preguntar al ajuntament).
- Si `turismemalgrat.com` expone `wp-json` y `/feed/`.
- El volumen real del dataset Socrata de la Generalitat para Malgrat.
- Los números de la BD: cuántos eventos hay realmente frente a cuántas tarjetas ve el usuario.
