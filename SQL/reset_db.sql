-- =============================================================================
-- reset_db.sql
-- =============================================================================
-- Deja la base de datos lista para una ingesta limpia con ingest_all.py.
--
-- VACÍA (todo esto lo repuebla el pipeline a partir del JSON de entrada + webs):
--   - EVENTOS_MASTER y sus tablas hijas (horarios, categorías-evento, fuentes-evento, binarios)
--   - RECINTOS
--   - BIBLIOTECA_FUENTES y SCRAPING_TARGETS (si las usas para ingesta programada)
--   - CODIGOS_POSTALES
--   - CIUDADES
--
-- NO TOCA (es configuración tuya, no datos derivados):
--   - CATEGORIAS  ← las 15 categorías con jerarquía, iconos y colores
--   - PERFIL_USUARIO (si lo usas)
--
-- ⚠ Tras ejecutar esto, borra también las imágenes en disco:
--      Windows PowerShell:  Remove-Item -Recurse -Force static\images\*
--      Linux/Mac:           rm -rf static/images/*
--
-- ⚠ Las CATEGORIAS deben estar pobladas ANTES de correr ingest_all.py.
--   Si no lo están, ejecuta antes reset_catalogo_categorias.sql.
-- =============================================================================

USE events_db;

-- Desactivar comprobación de FKs durante el borrado para no pelearnos con el
-- orden. Se reactiva al final. Esto permite vaciar sin importar dependencias.
SET FOREIGN_KEY_CHECKS = 0;

-- -----------------------------------------------------------------------------
-- Tablas hijas de EVENTOS_MASTER
-- -----------------------------------------------------------------------------
DELETE FROM `EVENTO_HORARIOS`;
DELETE FROM `EVENTO_CATEGORIAS`;
DELETE FROM `BINARIOS_STORAGE`;

DELETE FROM `EVENTO_FUENTES`;

-- -----------------------------------------------------------------------------
-- Tabla principal de eventos
-- -----------------------------------------------------------------------------
DELETE FROM `EVENTOS_MASTER`;

-- -----------------------------------------------------------------------------
-- Catálogos geográficos y de fuentes (los repuebla el pipeline)
-- -----------------------------------------------------------------------------
DELETE FROM `RECINTOS`;

DELETE FROM `SCRAPING_TARGETS`;
DELETE FROM `BIBLIOTECA_FUENTES`;

DELETE FROM `CODIGOS_POSTALES`;
DELETE FROM `CIUDADES`;

-- -----------------------------------------------------------------------------
-- Reiniciar los AUTO_INCREMENT para que los IDs empiecen limpios en 1
-- -----------------------------------------------------------------------------
ALTER TABLE `SCRAPING_TARGETS`       AUTO_INCREMENT = 1;
ALTER TABLE `EVENTO_HORARIOS`     AUTO_INCREMENT = 1;
ALTER TABLE `BINARIOS_STORAGE`    AUTO_INCREMENT = 1;
ALTER TABLE `RECINTOS`            AUTO_INCREMENT = 1;
ALTER TABLE `BIBLIOTECA_FUENTES`  AUTO_INCREMENT = 1;
ALTER TABLE `CIUDADES`            AUTO_INCREMENT = 1;
-- EVENTO_FUENTES si existe:
ALTER TABLE `EVENTO_FUENTES`      AUTO_INCREMENT = 1;

-- Reactivar comprobación de FKs
SET FOREIGN_KEY_CHECKS = 1;

-- -----------------------------------------------------------------------------
-- Verificación: todo a 0 excepto CATEGORIAS
-- -----------------------------------------------------------------------------
SELECT 'CIUDADES'           AS Tabla, COUNT(*) AS Filas FROM `CIUDADES`
UNION ALL SELECT 'CODIGOS_POSTALES',   COUNT(*) FROM `CODIGOS_POSTALES`
UNION ALL SELECT 'RECINTOS',           COUNT(*) FROM `RECINTOS`
UNION ALL SELECT 'SCRAPING_TARGETS',   COUNT(*) FROM `SCRAPING_TARGETS`
UNION ALL SELECT 'BIBLIOTECA_FUENTES', COUNT(*) FROM `BIBLIOTECA_FUENTES`
UNION ALL SELECT 'EVENTOS_MASTER',     COUNT(*) FROM `EVENTOS_MASTER`
UNION ALL SELECT 'EVENTO_HORARIOS',    COUNT(*) FROM `EVENTO_HORARIOS`
UNION ALL SELECT 'EVENTO_CATEGORIAS',  COUNT(*) FROM `EVENTO_CATEGORIAS`
UNION ALL SELECT 'BINARIOS_STORAGE',   COUNT(*) FROM `BINARIOS_STORAGE`
UNION ALL SELECT 'CATEGORIAS (intacta)', COUNT(*) FROM `CATEGORIAS`;
