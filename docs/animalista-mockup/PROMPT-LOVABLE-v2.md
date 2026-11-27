# Prompt para Lovable — Demo v2 «El Viajero Animalista»

> Cómo usarlo: en el proyecto de Lovable de la v1, sustituye
> `public/data/contenidos.xml` por el nuevo fichero y envía este prompt
> entero. Es una reescritura completa de la demo, no un parche: pide a Lovable
> que rehaga las pantallas con la estructura nueva. El XML contiene contenidos
> reales de los últimos diez días; nada es inventado.

---

## Prompt

Reconstruye por completo la demo **El Viajero Animalista** a partir del
fichero `public/data/contenidos.xml` (versión 0.2). Todo lo que se muestre
debe salir del XML; no inventes datos ni rellenes huecos. Carga el XML con
`fetch('/data/contenidos.xml')` y `DOMParser`. Sin backend, sin login, solo
las librerías que ya trae el proyecto (React, Tailwind, shadcn/ui,
lucide-react). Todo en castellano. Mobile first, debe verse bien a 375 px y
en escritorio.

### Qué es

Un buscador de noticias, eventos, iniciativas públicas, campañas y recursos
sobre animales en España, recopilado y clasificado automáticamente con IA.
Hay dos públicos: el visitante de la web (vista pública) y el equipo que
supervisa el sistema (panel interno). La información interna nunca se mezcla
con la pública.

### Estructura del XML (resumen)

- `taxonomia`: `tiposContenido`, `temas`, `animales`, `ambitos`, `gruposFuente`, `estadosEvento`, `procedencias`. Cada uno con `slug` y `nombre`. Usa siempre el `nombre` para mostrar.
- `geo`: las 19 comunidades autónomas con sus 52 provincias.
- `catalogoMunicipios`: municipios citados, con `codigoINE`, `nombre`, `provincia`, `ccaa`, `urlFicha`.
- `catalogoPlayas`: playas caninas de ejemplo con `id`, `nombre`, `municipio`, `urlFicha`.
- `fuentes`: cada fuente con `id`, `nombre`, `grupo`, `modo`, `activa`, `estado`, `vistos`, `aportados`, `descartados`, `ultimoError`, `motivoExclusion`.
- `contenidos/contenido` con atributos `id` y `tipo`, e hijos: `titulo`, `resumen`, `fechaPublicacion`, `ultimaActualizacion?`, `idiomaOrigen`, `evento?` (`fechaInicio`, `fechaFin`, `horario`, `lugar`, `precio`, `esGratuito`, `inscripcion`, `condiciones`, `accesoAnimales`, `estado`), `campana?` (`entidadImpulsora`, `comoParticipar`, `enlaceOficial`, `fechaLimite`), `recurso?` (`autoria`, `ultimaActualizacion`), `publica` (`nombre`, `grupo`), `organiza?` (`nombre`, `tipo`), `ambito`, `ubicacion/lugar` (`nivel`, `codigoINE`, `nombre`, `provincia`, `ccaa`, `rol`, `principal`, `urlFicha`), `playas?/playa` (`ref`, `nombre`, `urlFicha`), `animales/animal`, `temas/tema` (`slug`, `principal`), `etiquetas/etiqueta`, `fuentes/fuente` (`ref`, `medio`, `url`, `principal`, `fecha`) e `interno` (relevancia, procedencia, notas, dedupe).
- `ejecucion`: datos del último crawl, `descartes/descarte` con `motivo`, `cantidad` y `muestra`, y `coberturaGeo`.

Las etiquetas de los nombres de campo en pantalla son estas: Tipo, Tema,
Animal, Comunidad autónoma, Provincia, Municipio, Ámbito, Fuente, Fecha de
publicación, Fecha del evento, Horario, Lugar, Precio, Organiza, Fuente (quien
publica), Inscripción, Condiciones de participación, Acceso con animales,
Entidad impulsora, Cómo participar, Enlace oficial, Fecha límite, Autoría,
Última actualización, Estado, Animales, Temas, Etiquetas.

### Vista pública: Explorar

- Cabecera con el nombre, un subtítulo de una línea y tres contadores calculados: contenidos, eventos próximos o en curso, provincias con contenidos.
- Filtros combinables, poblados desde el XML, con chips de filtros activos y botón «Limpiar»:
  - **Tipo**: Todos + los cinco tipos por su nombre.
  - **Tema**: Todos + los quince temas. Un contenido con varios temas aparece en todos ellos.
  - **Animal**: Todos + los once grupos.
  - **Comunidad autónoma** y **Provincia** (las provincias dependen de la comunidad elegida). Lista completa desde `geo`, no solo las que tienen contenidos; si una no tiene resultados, el estado vacío lo dice.
  - **Municipio**: campo de texto con autocompletado sobre `catalogoMunicipios`; al coincidir varios nombres se muestra la provincia entre paréntesis.
  - **Ámbito**: Todos, Estatal, Autonómico, Provincial, Municipal, Varios territorios.
  - **Fuente**: Todas + los once grupos de fuente, por su nombre. Nunca el nombre concreto de la fuente en el filtro.
  - **Fecha de publicación**: Todas, Últimos 7 días, Últimos 30 días, Intervalo personalizado.
  - **Fecha del evento** (solo visible si el tipo es Evento o Todos): Cualquier fecha, Hoy, Este fin de semana, Próximos 7 días, Intervalo personalizado.
  - **Buscar**: texto libre sobre título, resumen y etiquetas.
- **Ordenar**: Más recientes (por defecto), Próximos eventos (solo eventos, por fecha de inicio ascendente, excluyendo finalizados).
- Los filtros activos se reflejan en la query string de la URL.
- Rejilla de tarjetas: 1 columna en móvil, 2 en tablet, 3 en escritorio. Cada tarjeta muestra: badge del tipo con un color propio por tipo, título, resumen recortado a tres líneas, fecha de publicación (formato «7 nov 2026»), y en eventos la fecha del evento, el estado (Próximo, En curso, Finalizado, Cancelado, Aplazado) y el lugar; chips de animales con icono; chips de temas; línea de ubicación con municipio, provincia y comunidad, o «España» si el ámbito es estatal; el grupo de fuente y el nombre de quien publica. Si hay más de una fuente, «+N fuentes». Sin imágenes: cabecera de color o icono por tema.
- Estado vacío claro con el texto «No hay contenidos para estos filtros».

### Vista pública: ficha de un contenido

Al hacer clic, panel lateral en escritorio y página completa en móvil.

- Título, badge de tipo, resumen completo, fecha de publicación y «Última actualización» si existe.
- **Según el tipo**, solo los campos que existan en el XML:
  - Evento: Fecha del evento, Horario, Lugar, Precio (si `esGratuito` es true muestra «Gratuito»), Organiza, Inscripción, Condiciones de participación, Acceso con animales, Estado.
  - Campaña: Entidad impulsora, Cómo participar, Enlace oficial, Fecha límite.
  - Recurso: Autoría o Entidad responsable, Última actualización, y un botón destacado «Consultar recurso original».
  - Para los campos esperables de ese tipo que no vengan en el XML, muestra «No consta». Para el resto, no muestres nada.
- **Ubicación**: Municipio, Provincia y Comunidad autónoma como campos separados. Si hay varios lugares, lístalos. Un lugar con `rol="AFECTA"` se etiqueta «Afecta a»; con `rol="OCURRE"`, «Dónde».
- **Enlaces a Viajero Animalista**: por cada municipio, botón «Ver municipio en Viajero Animalista» con su `urlFicha`; por cada playa en `playas`, botón «Ver playa en Viajero Animalista». Abren en pestaña nueva.
- **Organiza** y **Fuente** (quien publica) como dos datos distintos.
- Animales, Temas y Etiquetas.
- **Fuentes**: nombre del medio o entidad y enlace original, abriendo en pestaña nueva. Marca cuál es la principal.
- Botón «Compartir»: copia el enlace y ofrece WhatsApp (`https://wa.me/?text=`).
- Botón «Comunicar un error»: abre un diálogo con un formulario sencillo (qué está mal, correo opcional) que en la demo solo muestra un mensaje de confirmación.
- Al pie: «Resumen elaborado con ayuda de inteligencia artificial a partir de las fuentes enlazadas.» Nunca la palabra «verificado».
- Nada de lo que cuelga de `<interno>` se muestra aquí. Tampoco códigos como PUBLICA o MUNICIPAL: usa siempre nombres legibles.

### Panel interno

Una pestaña aparte, «Panel», con cuatro sub-pestañas. Aquí sí se muestra todo lo interno.

- **Contenidos**: la misma lista que Explorar pero en tabla, con columnas Tipo, Título, Fecha, Fuente, Grupo, Relevancia, Procedencia resumida y Notas. Al abrir una fila se ve la tabla de procedencia campo a campo con un badge por valor (`extraido` verde, `inferido` ámbar, `generado` azul, `maestro` gris, `fuente` violeta, `no_consta` sin color), la nota de calidad, la nota de dedupe y los lugares no resueltos.
- **Fuentes**: tabla con nombre, grupo, modo, estado (OK verde, ERROR rojo, EXCLUIDA gris), vistos, aportados, descartados, tasa de aporte calculada, último error y motivo de exclusión. Filtro por grupo y por estado.
- **Ejecución**: tarjeta con los datos de `ejecucion`. Barras sencillas hechas con divs de descartes por motivo, con sus muestras debajo. Cobertura por comunidad ordenada. Botón «Ejecutar crawl» que en la demo abre un diálogo explicando que no hace nada.
- **Taxonomía**: tipos, temas, animales, ámbitos, grupos de fuente y estados de evento con el número de contenidos que usa cada valor.

### Reglas

- Todo en castellano. Fechas «7 nov 2026». Contraste suficiente y foco visible.
- No añadas contenidos de ejemplo ni texto inventado.
- Pie de página: «Mockup con datos reales de los últimos diez días. Fuentes enlazadas. Proyecto en fase de validación.»

Empieza por Explorar con los filtros y las tarjetas; después la ficha;
después el panel.

---

## Qué revisar con esta v2

1. Los cinco tipos y los quince temas con contenidos reales: ¿alguno queda casi vacío o se confunde con otro?
2. El filtro de fuente por grupos: ¿se entiende sin ver el nombre de la fuente hasta abrir la ficha?
3. El enlace a municipio y playa: la plantilla de URL de la cabecera del XML es la que Héctor debe sustituir por sus rutas reales.
4. Los campos «No consta» en eventos: ¿aportan o molestan?
5. Las noticias con ámbito estatal sin lugar: ¿se filtran bien con «Ámbito: Estatal»?
