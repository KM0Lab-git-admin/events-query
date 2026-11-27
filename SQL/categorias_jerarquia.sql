-- ============================================================================
-- categorias_jerarquia.sql
-- ============================================================================
-- Añade jerarquía padre/hijo a la tabla CATEGORIAS y puebla el catálogo
-- inicial con 7 categorías padre + 7 subcategorías.
--
-- Alineado con scripts/schema.sql: columnas Slug, Nombre_CAT (no Codigo/Nombre_CA).
--
-- Es IDEMPOTENTE: se puede ejecutar varias veces sin romper nada. Si la tabla
-- ya tenía las categorías padre del intento anterior, no las duplica; si la
-- columna ID_Categoria_Padre ya existe, el ALTER fallará (ver nota más abajo).
--
-- NOTAS DE EJECUCIÓN:
--   - Si la columna ID_Categoria_Padre ya existe, el ALTER dará error
--     "Duplicate column name". En ese caso, comenta el bloque 1.
--   - Los bloques 2 y 3 (INSERTs) son siempre seguros: usan ON DUPLICATE KEY
--     UPDATE sobre UNIQUE(Slug) para no duplicar.
-- ============================================================================


-- ----------------------------------------------------------------------------
-- BLOQUE 1: ALTER TABLE — añadir jerarquía
-- Ejecutar SOLO una vez. Si ya está aplicado, comenta este bloque.
-- ----------------------------------------------------------------------------

ALTER TABLE `CATEGORIAS`
  ADD COLUMN `ID_Categoria_Padre` INT NULL AFTER `Nombre_CAT`,
  ADD CONSTRAINT `FK_CAT_PADRE`
    FOREIGN KEY (`ID_Categoria_Padre`) REFERENCES `CATEGORIAS` (`ID_Categoria`);

CREATE INDEX `IDX_CAT_PADRE` ON `CATEGORIAS` (`ID_Categoria_Padre`);


-- ----------------------------------------------------------------------------
-- BLOQUE 2: Categorías padre
-- Idempotente: si ya existen del intento anterior, solo actualiza orden.
-- ----------------------------------------------------------------------------

INSERT INTO `CATEGORIAS` (`Slug`, `Nombre_ES`, `Nombre_CAT`, `ID_Categoria_Padre`, `Orden`, `Activo`) VALUES
  ('musica',    'Música',   'Música',   NULL, 10, 1),
  ('cultura',   'Cultura',  'Cultura',  NULL, 20, 1),
  ('infantil',  'Infantil', 'Infantil', NULL, 30, 1),
  ('deporte',   'Deporte',  'Esport',   NULL, 40, 1),
  ('talleres',  'Talleres', 'Tallers',  NULL, 50, 1),
  ('fiestas',   'Fiestas',  'Festes',   NULL, 60, 1),
  ('gastro',    'Gastro',   'Gastro',   NULL, 70, 1)
ON DUPLICATE KEY UPDATE
  `Nombre_ES`          = VALUES(`Nombre_ES`),
  `Nombre_CAT`         = VALUES(`Nombre_CAT`),
  `ID_Categoria_Padre` = VALUES(`ID_Categoria_Padre`),
  `Orden`              = VALUES(`Orden`);


-- ----------------------------------------------------------------------------
-- BLOQUE 3: Subcategorías
-- Idempotente. Resuelve el ID del padre por JOIN al insertar.
-- ----------------------------------------------------------------------------

INSERT INTO `CATEGORIAS` (`Slug`, `Nombre_ES`, `Nombre_CAT`, `ID_Categoria_Padre`, `Orden`, `Activo`)
SELECT
  new_data.slug,
  new_data.nombre_es,
  new_data.nombre_cat,
  parent.`ID_Categoria`,
  new_data.orden,
  1
FROM (
              SELECT 'cine'            AS slug, 'Cine'            AS nombre_es, 'Cinema'         AS nombre_cat, 'cultura' AS padre_slug, 1 AS orden
    UNION ALL SELECT 'teatro',                    'Teatro',                       'Teatre',                     'cultura',                 2
    UNION ALL SELECT 'exposiciones',              'Exposiciones',                 'Exposicions',                'cultura',                 3
    UNION ALL SELECT 'charlas',                   'Charlas',                      'Xerrades',                   'cultura',                 4
    UNION ALL SELECT 'lectura',                   'Lectura',                      'Lectura',                    'cultura',                 5
    UNION ALL SELECT 'fiestas-mayores',           'Fiestas mayores',              'Festes majors',              'fiestas',                 1
    UNION ALL SELECT 'ferias',                    'Ferias',                       'Fires',                      'fiestas',                 2
) AS new_data
JOIN `CATEGORIAS` AS parent ON parent.`Slug` = new_data.padre_slug
ON DUPLICATE KEY UPDATE
  `Nombre_ES`          = VALUES(`Nombre_ES`),
  `Nombre_CAT`         = VALUES(`Nombre_CAT`),
  `ID_Categoria_Padre` = VALUES(`ID_Categoria_Padre`),
  `Orden`              = VALUES(`Orden`);


-- ----------------------------------------------------------------------------
-- VERIFICACIÓN: ver el árbol resultante
-- ----------------------------------------------------------------------------

SELECT
    parent.`Nombre_ES` AS Padre,
    child.`Slug`,
    child.`Nombre_ES`,
    child.`Orden`
FROM `CATEGORIAS` child
LEFT JOIN `CATEGORIAS` parent ON parent.`ID_Categoria` = child.`ID_Categoria_Padre`
ORDER BY
    COALESCE(parent.`Orden`, child.`Orden`),
    child.`ID_Categoria_Padre` IS NOT NULL,
    child.`Orden`;
