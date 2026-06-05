-- ============================================================================
-- Limpieza: eventos + datos operativos de ingesta (Docker, Railway, local)
-- ============================================================================
-- Conserva por defecto:
--   CATEGORIAS (catálogo), CIUDADES, CODIGOS_POSTALES
-- Elimina:
--   EVENTOS_MASTER y tablas ligadas por CASCADE (horarios, categorías-evento,
--   binarios, evento-fuentes),
--   SCRAPING_TARGETS, BIBLIOTECA_FUENTES
--
-- Docker (PowerShell, desde la raíz del repo; ajusta usuario/clave si cambiaste):
--   Get-Content .\SQL\CLEAR_EVENT_DATA.sql -Raw | docker exec -i events-mysql mysql -u events_user -pevents_password events_db
--
-- Railway / DBeaver: ejecuta este fichero completo contra la base events_db
-- (haz backup o export si la BD es producción).
-- ============================================================================

USE events_db;

SET NAMES utf8mb4;

START TRANSACTION;

-- Eventos (CASCADE: EVENTO_HORARIOS, EVENTO_CATEGORIAS, BINARIOS_STORAGE, EVENTO_FUENTES).
DELETE FROM EVENTOS_MASTER;

-- Cola de fuentes (sin CAPTURAS_RAW / auditoría: tablas retiradas del esquema)
DELETE FROM SCRAPING_TARGETS;
DELETE FROM BIBLIOTECA_FUENTES;

-- Opcional: vaciar también geografía creada por seeds/fake (descomenta si lo necesitas)
-- DELETE FROM CODIGOS_POSTALES;
-- DELETE FROM CIUDADES;

COMMIT;

-- Reinicia contadores AUTO_INCREMENT (IDs más legibles en ingesta nueva)
ALTER TABLE SCRAPING_TARGETS AUTO_INCREMENT = 1;
ALTER TABLE BIBLIOTECA_FUENTES AUTO_INCREMENT = 1;
ALTER TABLE EVENTO_HORARIOS AUTO_INCREMENT = 1;
ALTER TABLE BINARIOS_STORAGE AUTO_INCREMENT = 1;
ALTER TABLE EVENTO_FUENTES AUTO_INCREMENT = 1;
