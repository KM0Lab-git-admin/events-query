# Prompt para Lovable — Demo «El Viajero Animalista»

> Cómo usarlo: crea un proyecto nuevo en Lovable, sube `contenidos.xml` a
> `public/data/contenidos.xml` (o pégalo cuando Lovable lo pida) y envía el
> prompt de abajo tal cual. El XML contiene 50 contenidos reales recogidos el
> 12-10-2026; nada es inventado. La demo no tiene backend ni login.

---

## Prompt

Construye una demo web en castellano llamada **El Viajero Animalista** que lea
el fichero `public/data/contenidos.xml` (ya está en el proyecto) y lo
visualice. No inventes datos: todo lo que se muestre debe salir del XML.
Carga el XML con `fetch('/data/contenidos.xml')` y pársealo con `DOMParser`.
Sin backend, sin autenticación, sin librerías nuevas más allá de las que ya
trae el proyecto (React, Tailwind, shadcn/ui, lucide-react).

### Qué es

Un módulo que recopila automáticamente noticias y eventos del mundo animalista
en toda España, los enriquece con IA y los clasifica. La demo sirve para que
el propietario del proyecto valide tres cosas: qué contenidos encontramos,
cómo los clasificamos y cómo se supervisa la calidad del proceso.

### Estructura del XML

- `taxonomia`: tipos de contenido, temas, animales, ámbitos y procedencias, con `slug` y `nombre`.
- `geo`: comunidades autónomas (`ccaa`) con sus provincias.
- `fuentes`: las fuentes rastreadas, con estadísticas (`vistos`, `aportados`, `descartados`, `ultimoEstado`).
- `contenidos/contenido`: cada noticia o evento. Atributos `id`, `tipo`, `estado`, `relevancia`. Hijos: `titulo`, `resumen`, `fechaPublicacion`, `fechaCaducidad` (solo noticias), `evento` (solo eventos: `fechaInicio`, `fechaFin`, `horaInicio`, `horaFin`, `lugar`, `esGratuito`), `entidad`, `ambito`, `geo/lugar` (`nivel`, `nombre`, `provincia`, `ccaa`, `principal`), `animales/animal`, `temas/tema` (`principal`, `score`), `tags/tag`, `fuentes/fuenteRef` (`medio`, `url`, `principal`, `aportoExtraccion`, `otrasFuentesDetectadas`), `procedencia` (un atributo por campo con valor `extraido`, `inferido`, `generado`, `maestro` o `fuente`) y, a veces, `notaCalidad`.
- `ejecucion`: resumen de la última ejecución del crawl, con `descartes/descarte` (motivo, cantidad, muestras) y `coberturaGeo`.

### Pantallas

Navegación superior con tres pestañas. Diseño limpio, cálido, pensado para
una web de viajes con animales. Mobile first: debe verse bien a 375 px y en
escritorio. Nada de hex sueltos: usa los tokens del tema.

**1. Explorar** (la vista principal, es lo que vería un usuario de la web)

- Cabecera con el nombre, un subtítulo corto y tres contadores calculados del XML: contenidos activos, eventos próximos, provincias cubiertas.
- Barra de filtros combinables, todos poblados desde el XML: tipo de contenido, tema, animal, comunidad autónoma, provincia (dependiente de la comunidad elegida), ámbito, fuente, relevancia mínima (slider de 0 a 1) y búsqueda de texto sobre título, resumen y tags. Botón «Limpiar filtros». Chips con los filtros activos.
- Rejilla de tarjetas (1 columna en móvil, 2 en tablet, 3 en escritorio). Cada tarjeta muestra: badge del tipo con color propio (NOTICIA, EVENTO, INICIATIVA), título, resumen recortado a tres líneas, fecha de publicación o, en eventos, fecha y lugar del evento destacados, chips de animales (icono de perro, gato o pata genérica), chips de temas, línea de lugar con comunidad y provincia o «España» si el ámbito es nacional, nombre del medio principal y, si hay más de una fuente, un indicador «+N fuentes». Una barra o punto de color para la relevancia. Sin imágenes: usa un bloque de color o un icono grande por tema como cabecera de la tarjeta.
- Orden por defecto: eventos próximos primero, después noticias por fecha de publicación descendente. Selector para cambiar a relevancia.
- Estado vacío claro cuando no hay resultados.

**2. Detalle** (al hacer clic en una tarjeta, panel lateral o página)

- Todo el contenido: título, resumen completo, tipo, estado, relevancia, fechas, datos del evento, entidad, ámbito, lugares con su nivel, animales, temas con su puntuación, tags.
- Bloque «Fuentes»: lista de medios con enlace externo a la URL original, cuál es la principal, si aportó extracción y cuántas otras fuentes detectó el sistema. Los enlaces deben abrirse en pestaña nueva.
- Bloque «Procedencia de cada dato»: tabla campo por campo con un badge por valor: `extraido` verde, `inferido` ámbar, `generado` azul, `maestro` gris, `fuente` violeta. Explica en una línea qué significa cada uno usando la sección `procedencias` del XML.
- Si existe `notaCalidad`, mostrarla en un aviso destacado.
- Aviso al pie: «Solo se almacena este resumen y el enlace. El artículo completo está en la fuente.»

**3. Panel de ingesta** (la vista de operaciones)

- Sub-pestaña **Fuentes**: tabla con nombre, tipo, tipo de contenido, estado (OK verde, ERROR rojo, PAUSADO gris), vistos, aportados, descartados, tasa de aporte calculada y el último error si lo hay. Un interruptor «activa» que solo cambia el estado visual.
- Sub-pestaña **Ejecución**: tarjeta con los datos de `ejecucion` (inicio, fin, modelo, coste estimado, llamadas, contenidos nuevos, descartados). Un gráfico de barras sencillo de descartes por motivo hecho con divs, sin librerías, y debajo las muestras de cada motivo. Otro bloque con la cobertura por comunidad autónoma ordenada de mayor a menor. Un botón «Ejecutar ingesta» que abre un diálogo explicando que en la demo no hace nada.
- Sub-pestaña **Taxonomía**: las listas de tipos, temas, animales y procedencias tal como vienen en el XML, con el número de contenidos que usan cada valor.

### Reglas

- Todo en castellano. Fechas en formato «12 oct 2026».
- Los filtros deben poder combinarse y la URL debe reflejar los filtros activos en la query string para poder compartir una vista.
- Accesible: contraste suficiente, foco visible, etiquetas en los controles.
- Si un contenido no tiene `geo/lugar`, muéstralo como «España» y permite filtrarlo con la opción «Ámbito nacional».
- No añadas contenidos de ejemplo ni rellenes huecos con texto inventado. Si un campo no existe en el XML, no lo muestres.
- Pie de página: «Mockup con datos reales del 12-10-2026. Fuentes enlazadas. Proyecto en fase de validación.»

Empieza por la pestaña Explorar con los filtros y las tarjetas; después el detalle; después el panel.

---

## Qué validar con el amigo al enseñarle la demo

1. ¿Los seis tipos de contenido tienen sentido, o sobran o faltan? Las fichas de adopción, por ejemplo, encajan mejor como «recurso» que como noticia.
2. ¿Los nueve temas cubren lo que su web quiere contar? ¿Alguno sobra o se solapa?
3. ¿La lista de animales es la correcta para su público? Perros y gatos dominan; el resto apenas aparece en diez días de noticias.
4. ¿Filtrar por comunidad y provincia le basta para la primera versión, o necesita ya el municipio y el mapa?
5. ¿Le vale que las noticias desaparezcan a los diez días?
6. ¿Qué peso quiere dar a las noticias nacionales de legislación frente a las locales de ayuntamientos? Con las consultas actuales salen a partes iguales.
7. ¿Le parece suficiente «resumen más enlace» o quiere más texto? (El artículo completo no se puede republicar.)
8. ¿Quiere imágenes de los medios, imágenes generadas, o ninguna?
