-- ============================================================================
-- fuentes_delta.sql
-- ============================================================================
-- Prepara BIBLIOTECA_FUENTES y SCRAPING_TARGETS para la ingesta multi-fuente
-- (webs oficiales + agregadores + redes sociales) con clasificación de
-- contenido evento/noticia.
--
-- Cambios:
--   1. ENUM Plataforma: + YOUTUBE, TELEGRAM (en ambas tablas). Telegram se
--      modela como Tipo_Fuente='RED_SOCIAL_PERFIL' + Plataforma='TELEGRAM'
--      con target Tipo_Target='SOCIAL_PERFIL' (no se toca el ENUM Tipo_Target).
--   2. BIBLIOTECA_FUENTES.Tipo_Contenido: hint para el clasificador LLM.
--      EVENTOS  -> ruta de eventos directa (sin clasificación, coste 0 extra)
--      NOTICIAS -> ruta de noticias con clasificación
--      MIXTO    -> el LLM clasifica cada item (evento/noticia/descartar)
--      Es un sesgo, no determinante: el LLM decide por contenido.
--
-- Idempotente: MODIFY COLUMN es re-ejecutable (deja el mismo ENUM); el ADD
-- COLUMN va protegido con INFORMATION_SCHEMA para no fallar si ya existe.
-- ============================================================================

SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- BLOQUE 1: ampliar ENUM Plataforma en BIBLIOTECA_FUENTES
-- ----------------------------------------------------------------------------

ALTER TABLE `BIBLIOTECA_FUENTES`
  MODIFY COLUMN `Plataforma`
    ENUM('INSTAGRAM','FACEBOOK','X_TWITTER','TIKTOK','YOUTUBE','TELEGRAM') NULL
    COMMENT 'Para redes: actor Apify asociado (TELEGRAM: scraping directo t.me/s)';

-- ----------------------------------------------------------------------------
-- BLOQUE 2: ampliar ENUM Plataforma en SCRAPING_TARGETS
-- ----------------------------------------------------------------------------

ALTER TABLE `SCRAPING_TARGETS`
  MODIFY COLUMN `Plataforma`
    ENUM('INSTAGRAM','FACEBOOK','X_TWITTER','TIKTOK','YOUTUBE','TELEGRAM') NULL;

-- ----------------------------------------------------------------------------
-- BLOQUE 3: BIBLIOTECA_FUENTES.Tipo_Contenido (idempotente)
-- ----------------------------------------------------------------------------

SET @existe := (
  SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'BIBLIOTECA_FUENTES'
    AND COLUMN_NAME = 'Tipo_Contenido'
);

SET @sql := IF(@existe = 0,
  'ALTER TABLE `BIBLIOTECA_FUENTES`
     ADD COLUMN `Tipo_Contenido` ENUM(''EVENTOS'',''NOTICIAS'',''MIXTO'')
       NOT NULL DEFAULT ''MIXTO''
       COMMENT ''Hint para el clasificador: qué suele contener la fuente''
       AFTER `Tipo_Fuente`',
  'SELECT ''Tipo_Contenido ya existe, sin cambios'' AS Resultado');

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ----------------------------------------------------------------------------
-- VERIFICACIÓN
-- ----------------------------------------------------------------------------

SHOW COLUMNS FROM `BIBLIOTECA_FUENTES`;
SHOW COLUMNS FROM `SCRAPING_TARGETS`;
