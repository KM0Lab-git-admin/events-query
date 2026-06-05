-- ============================================================================
-- Migración: elimina tablas auxiliares retiradas del esquema
-- ============================================================================
-- DROP (si existen): AUDITORIA_SCRAPING, CAPTURAS_RAW, COVERAGE_METRICS,
--   EVENTO_EMBEDDINGS, FUENTES_FAMILIA, PHASH_IMAGENES, RECINTO_ALIASES
--
-- Con FOREIGN_KEY_CHECKS=0 el DROP de tablas padre suele funcionar aunque
-- queden FKs declaradas en tablas que no se borran (p. ej. EVENTO_FUENTES → CAPTURAS_RAW).
-- Tras el DROP, revisa EVENTO_FUENTES: si sigue existiendo la columna ID_Captura,
-- descomenta el bloque «Limpieza EVENTO_FUENTES» del final y ejecútalo.
--
-- Si EVENTOS_MASTER tenía ID_Familia / FK_EVENTO_FAMILIA y el DROP de FUENTES_FAMILIA
-- falla, descomenta el bloque «Limpieza EVENTOS_MASTER» antes de repetir este script.
--
-- Uso (Docker, ejemplo):
--   Get-Content .\SQL\migrate_drop_aux_tables.sql -Raw | docker exec -i events-mysql `
--     mysql -u events_user -pevents_password events_db
-- ============================================================================

USE events_db;

SET NAMES utf8mb4;

SET FOREIGN_KEY_CHECKS = 0;

DROP TABLE IF EXISTS `AUDITORIA_SCRAPING`;

DROP TABLE IF EXISTS `EVENTO_EMBEDDINGS`;

DROP TABLE IF EXISTS `PHASH_IMAGENES`;

DROP TABLE IF EXISTS `CAPTURAS_RAW`;

DROP TABLE IF EXISTS `COVERAGE_METRICS`;

DROP TABLE IF EXISTS `FUENTES_FAMILIA`;

DROP TABLE IF EXISTS `RECINTO_ALIASES`;

SET FOREIGN_KEY_CHECKS = 1;

-- ---------------------------------------------------------------------------
-- Limpieza EVENTOS_MASTER (solo si ves error al DROP FUENTES_FAMILIA o quedó la columna)
-- ---------------------------------------------------------------------------

-- ALTER TABLE `EVENTOS_MASTER` DROP FOREIGN KEY `FK_EVENTO_FAMILIA`;
-- ALTER TABLE `EVENTOS_MASTER` DROP COLUMN `ID_Familia`;

-- ---------------------------------------------------------------------------
-- Limpieza EVENTO_FUENTES (solo si tras los DROP anterior sigue habiendo ID_Captura)
-- ---------------------------------------------------------------------------

-- ALTER TABLE `EVENTO_FUENTES` DROP FOREIGN KEY `FK_EF_CAPTURA`;
-- ALTER TABLE `EVENTO_FUENTES` DROP INDEX `IDX_EF_CAPTURA`;
-- ALTER TABLE `EVENTO_FUENTES` DROP COLUMN `ID_Captura`;

-- FIN
