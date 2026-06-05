-- ============================================================================
-- Limpieza SOLO de eventos en EVENTOS_MASTER (y tablas ligadas por CASCADE)
-- ============================================================================
-- Borra todas las filas de EVENTOS_MASTER. MySQL elimina en cascada (según esquema en
-- scripts/schema.sql y SQL/SCHEMA_SQL_FINAL.sql):
--   EVENTO_HORARIOS
--   EVENTO_CATEGORIAS
--   BINARIOS_STORAGE
--   EVENTO_FUENTES
--
-- NO borra:
--   CATEGORIAS, RECINTOS, CIUDADES, CODIGOS_POSTALES,
--   BIBLIOTECA_FUENTES, SCRAPING_TARGETS, etc.
-- Si quieres vaciar también cola/fuentes de ingesta → usa SQL/CLEAR_EVENT_DATA.sql
--
-- Archivos locales: las rutas tipo static/images/<ID_Unico_Evento>/ no están en BD;
-- bórralos manualmente si quieres disco limpio:
--   .\static\images\  (solo carpetas huérfanas tras el DELETE)
--
-- Uso desde PowerShell contra Docker típico (events-user / events-password):
--   Get-Content .\SQL\CLEAR_EVENTOS_MASTER.sql -Raw | docker exec -i events-mysql `
--     mysql -u events_user -pevents_password events_db
-- ============================================================================

USE events_db;

SET NAMES utf8mb4;

START TRANSACTION;

DELETE FROM EVENTOS_MASTER;

COMMIT;

-- Opcional: reiniciar AUTO_INCREMENT en tablas con filas en cascada
ALTER TABLE EVENTO_HORARIOS AUTO_INCREMENT = 1;
ALTER TABLE BINARIOS_STORAGE AUTO_INCREMENT = 1;
ALTER TABLE EVENTO_FUENTES AUTO_INCREMENT = 1;
