-- ============================================================================
-- fix_categorias_utf8.sql
-- ============================================================================
-- Repara texto en CATEGORIAS dañado por doble codificación UTF-8 (ej.
-- "FormaciÃ³n") y sustituye pérdidas tipo "M??sica".
--
-- Idempotente razonable: filas ya correctas no suelen coincidir WHERE.
-- Ejecutar con cliente en UTF-8, ej.: mysql ... --default-character-set=utf8mb4
-- ============================================================================

USE events_db;

SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Doble UTF-8 típico (patrón UTF-8 de ó/í codificado dos veces).
UPDATE `CATEGORIAS`
SET
  `Nombre_ES` = CONVERT(CAST(CONVERT(`Nombre_ES` USING latin1) AS BINARY) USING utf8mb4),
  `Nombre_CAT` = CONVERT(CAST(CONVERT(`Nombre_CAT` USING latin1) AS BINARY) USING utf8mb4)
WHERE HEX(`Nombre_ES`) LIKE '%C383C2%'
   OR HEX(`Nombre_CAT`) LIKE '%C383C2%';

-- Fila semilla "musica" si quedó con ??. (ajusta ID si tu catálogo difiere.)
UPDATE `CATEGORIAS`
SET `Nombre_ES` = 'Música', `Nombre_CAT` = 'Música'
WHERE `Slug` = 'musica'
  AND (`Nombre_ES` LIKE '%?%' OR `Nombre_CAT` LIKE '%?%');
