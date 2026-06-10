-- ============================================================================
-- familia_delta.sql
-- ============================================================================
-- Asegura la columna EVENTOS_MASTER.ID_Familia, usada por la deduplicación
-- semántica (scripts/dedupe_events.py) para AGRUPAR eventos relacionados sin
-- fusionarlos: las actividades de un evento paraguas (p.ej. los talleres del
-- Festival Libèl·lula) apuntan al ID del evento principal (cabeza de familia).
-- La cabeza de familia también lleva su propio id en ID_Familia.
--
-- Nota: algunas BDs ya tienen la columna (estaba en schemas antiguos y
-- migrate_drop_aux_tables.sql dejó su DROP comentado); por eso el ALTER va
-- protegido con INFORMATION_SCHEMA. Idempotente.
-- ============================================================================

SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

SET @existe := (
  SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'EVENTOS_MASTER'
    AND COLUMN_NAME = 'ID_Familia'
);

SET @sql := IF(@existe = 0,
  'ALTER TABLE `EVENTOS_MASTER`
     ADD COLUMN `ID_Familia` CHAR(64) NULL
       COMMENT ''ID del evento cabeza de familia (agrupación, no fusión)''
       AFTER `Coordenadas_JSON`',
  'SELECT ''ID_Familia ya existe, sin cambios'' AS Resultado');

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Índice para listar familias (idempotente)
SET @idx := (
  SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'EVENTOS_MASTER'
    AND INDEX_NAME = 'IDX_EVENTO_FAMILIA'
);

SET @sql := IF(@idx = 0,
  'CREATE INDEX `IDX_EVENTO_FAMILIA` ON `EVENTOS_MASTER` (`ID_Familia`)',
  'SELECT ''IDX_EVENTO_FAMILIA ya existe'' AS Resultado');

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SHOW COLUMNS FROM `EVENTOS_MASTER` LIKE 'ID_Familia';
