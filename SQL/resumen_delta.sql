-- ============================================================================
-- resumen_delta.sql
-- ============================================================================
-- Añade resúmenes cortos pensados para lectura rápida (tarjetas del frontend):
--   - EVENTOS_MASTER.Desc_Corta_CAT / Desc_Corta_ES (2-3 frases, ~300 chars)
--   - NOTICIAS_MASTER.Resumen_CAT / Resumen_ES
-- Los genera el LLM en el enriquecimiento (misma llamada, sin coste extra).
-- La API los sirve con fallback al truncado de la descripción larga para las
-- filas antiguas que aún no los tengan.
--
-- Idempotente: protegido con INFORMATION_SCHEMA.
-- ============================================================================

SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- BLOQUE 1: EVENTOS_MASTER.Desc_Corta_CAT / Desc_Corta_ES
-- ----------------------------------------------------------------------------

SET @existe := (
  SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'EVENTOS_MASTER' AND COLUMN_NAME = 'Desc_Corta_CAT'
);
SET @sql := IF(@existe = 0,
  'ALTER TABLE `EVENTOS_MASTER`
     ADD COLUMN `Desc_Corta_CAT` VARCHAR(500) NULL
       COMMENT ''Resumen 2-3 frases para tarjetas (generado por LLM)''
       AFTER `Desc_Larga_ES`,
     ADD COLUMN `Desc_Corta_ES` VARCHAR(500) NULL
       COMMENT ''Resumen 2-3 frases para tarjetas (generado por LLM)''
       AFTER `Desc_Corta_CAT`',
  'SELECT ''Desc_Corta ya existe, sin cambios'' AS Resultado');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ----------------------------------------------------------------------------
-- BLOQUE 2: NOTICIAS_MASTER.Resumen_CAT / Resumen_ES
-- ----------------------------------------------------------------------------

SET @existe := (
  SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'NOTICIAS_MASTER' AND COLUMN_NAME = 'Resumen_CAT'
);
SET @sql := IF(@existe = 0,
  'ALTER TABLE `NOTICIAS_MASTER`
     ADD COLUMN `Resumen_CAT` VARCHAR(500) NULL
       COMMENT ''Resumen 2-3 frases para tarjetas (generado por LLM)''
       AFTER `Cuerpo_ES`,
     ADD COLUMN `Resumen_ES` VARCHAR(500) NULL
       COMMENT ''Resumen 2-3 frases para tarjetas (generado por LLM)''
       AFTER `Resumen_CAT`',
  'SELECT ''Resumen ya existe, sin cambios'' AS Resultado');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SHOW COLUMNS FROM `EVENTOS_MASTER` LIKE 'Desc_Corta%';
SHOW COLUMNS FROM `NOTICIAS_MASTER` LIKE 'Resumen%';
