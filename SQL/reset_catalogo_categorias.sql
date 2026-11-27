-- =============================================================================
-- reset_catalogo_categorias.sql
-- =============================================================================
-- Borra y repobla CATEGORIAS con el catálogo final acordado:
--   - 8 categorías padre + 7 subcategorías = 15 entradas
--   - Plurales sin duplicidades:
--       Deportes (no "Deporte")
--       Gastronomía (no "Gastro")
--       Formación (no "Talleres")
--       Ocio (no "Fiestas" como padre genérico)
--
-- Jerarquía padre/hijo materializada con ID_Categoria_Padre.
--
-- Idempotente: ejecutable varias veces. Cada ejecución:
--   1. Garantiza la columna ID_Categoria_Padre y su índice/FK.
--   2. Vacía EVENTO_CATEGORIAS (las categorías de eventos se repoblarán al
--      re-correr persist_phase_c.py).
--   3. Vacía CATEGORIAS y reinicia el auto-increment.
--   4. Inserta los 8 padres + 7 subs.
--
-- ⚠ DESPUÉS de ejecutar este SQL hay que:
--     1. Actualizar enrich_phase_b.py con el catálogo nuevo (próximo entregable).
--     2. Re-correr enrich_phase_b.py sobre los CSVs (re-pago LLM ~$0.05).
--     3. Re-correr persist_phase_c.py para repoblar EVENTO_CATEGORIAS.
-- =============================================================================

USE events_db;

SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

-- -----------------------------------------------------------------------------
-- 1) Asegurar la columna ID_Categoria_Padre + FK + índice (idempotente)
-- -----------------------------------------------------------------------------

SET @columna_existe = (
  SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'CATEGORIAS'
    AND COLUMN_NAME = 'ID_Categoria_Padre'
);

SET @sql_add_col = IF(@columna_existe = 0,
  'ALTER TABLE `CATEGORIAS`
     ADD COLUMN `ID_Categoria_Padre` INT NULL AFTER `Slug`,
     ADD CONSTRAINT `FK_CAT_PADRE`
       FOREIGN KEY (`ID_Categoria_Padre`) REFERENCES `CATEGORIAS` (`ID_Categoria`)
       ON DELETE SET NULL',
  'DO 0'
);
PREPARE stmt FROM @sql_add_col; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @indice_existe = (
  SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'CATEGORIAS'
    AND INDEX_NAME = 'IDX_CAT_PADRE'
);

SET @sql_add_idx = IF(@indice_existe = 0,
  'CREATE INDEX `IDX_CAT_PADRE` ON `CATEGORIAS` (`ID_Categoria_Padre`)',
  'DO 0'
);
PREPARE stmt FROM @sql_add_idx; EXECUTE stmt; DEALLOCATE PREPARE stmt;


-- -----------------------------------------------------------------------------
-- 2) Limpiar tablas
-- -----------------------------------------------------------------------------
-- EVENTO_CATEGORIAS tiene FK a CATEGORIAS con ON DELETE RESTRICT, así que
-- la vaciamos primero. Después podemos vaciar CATEGORIAS.
-- TRUNCATE no funciona si hay FKs referenciándola; usamos DELETE + ALTER.

DELETE FROM `EVENTO_CATEGORIAS`;

DELETE FROM `CATEGORIAS`;
ALTER TABLE `CATEGORIAS` AUTO_INCREMENT = 1;


-- -----------------------------------------------------------------------------
-- 3) Insertar las 8 categorías padre
-- -----------------------------------------------------------------------------
-- Iconos: Material Symbols (https://fonts.google.com/icons)
-- Colores: paleta original de tu BD; conservamos coherencia visual

INSERT INTO `CATEGORIAS`
  (`Nombre_ES`, `Nombre_CAT`, `Slug`, `ID_Categoria_Padre`,
   `Icono`, `Color_Hex`, `Orden`, `Activo`)
VALUES
  ('Cultura',     'Cultura',     'cultura',     NULL, 'palette',       '#9C27B0', 10, 1),
  ('Deportes',    'Esports',     'deportes',    NULL, 'sports_soccer', '#4CAF50', 20, 1),
  ('Ocio',        'Oci',         'ocio',        NULL, 'celebration',   '#FF9800', 30, 1),
  ('Infantil',    'Infantil',    'infantil',    NULL, 'child_care',    '#2196F3', 40, 1),
  ('Formación',   'Formació',    'formacion',   NULL, 'school',        '#607D8B', 50, 1),
  ('Gastronomía', 'Gastronomia', 'gastronomia', NULL, 'restaurant',    '#F44336', 60, 1),
  ('Música',      'Música',      'musica',      NULL, 'music_note',    '#E91E63', 70, 1),
  ('Naturaleza',  'Naturalesa',  'naturaleza',  NULL, 'park',          '#8BC34A', 80, 1);


-- -----------------------------------------------------------------------------
-- 4) Insertar las 7 subcategorías
-- -----------------------------------------------------------------------------
-- ID_Categoria_Padre se resuelve por JOIN al Slug del padre.
-- Color_Hex se hereda del padre para coherencia visual.

INSERT INTO `CATEGORIAS`
  (`Nombre_ES`, `Nombre_CAT`, `Slug`, `ID_Categoria_Padre`,
   `Icono`, `Color_Hex`, `Orden`, `Activo`)
SELECT
  new_data.nombre_es,
  new_data.nombre_cat,
  new_data.slug,
  parent.ID_Categoria,
  new_data.icono,
  parent.Color_Hex,
  new_data.orden,
  1
FROM (
            SELECT 'Cine'            AS nombre_es, 'Cinema'        AS nombre_cat, 'cine'            AS slug, 'cultura' AS padre_slug, 'movie'           AS icono, 1 AS orden
  UNION ALL SELECT 'Teatro',                       'Teatre',                      'teatro',                  'cultura',                          'theater_comedy',                   2
  UNION ALL SELECT 'Exposiciones',                 'Exposicions',                 'exposiciones',            'cultura',                          'museum',                           3
  UNION ALL SELECT 'Charlas',                      'Xerrades',                    'charlas',                 'cultura',                          'forum',                            4
  UNION ALL SELECT 'Lectura',                      'Lectura',                     'lectura',                 'cultura',                          'menu_book',                        5
  UNION ALL SELECT 'Fiestas mayores',              'Festes majors',               'fiestas-mayores',         'ocio',                             'festival',                         1
  UNION ALL SELECT 'Ferias',                       'Fires',                       'ferias',                  'ocio',                             'storefront',                       2
) AS new_data
JOIN `CATEGORIAS` AS parent ON parent.Slug = new_data.padre_slug;


-- -----------------------------------------------------------------------------
-- 5) Verificación: árbol final con padres e hijos
-- -----------------------------------------------------------------------------

SELECT
  COALESCE(parent.Nombre_ES, '— PADRE —') AS Padre,
  child.ID_Categoria,
  child.Slug,
  child.Nombre_ES,
  child.Nombre_CAT,
  child.Icono,
  child.Color_Hex,
  child.Orden
FROM `CATEGORIAS` child
LEFT JOIN `CATEGORIAS` parent ON parent.ID_Categoria = child.ID_Categoria_Padre
ORDER BY
  COALESCE(parent.Orden, child.Orden),
  child.ID_Categoria_Padre IS NOT NULL,
  child.Orden;
