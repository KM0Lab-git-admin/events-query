-- ============================================================================
-- costes_delta.sql
-- ============================================================================
-- Persistencia del gasto de OpenAI por ejecución del pipeline de ingesta,
-- para consultarlo desde la API (/api/v1/costs/*) y la pestaña Costes del front.
--
--   - INGESTA_RUNS: una fila por ejecución (totales del run: tokens, coste,
--     eventos/noticias persistidos, estado de targets).
--   - INGESTA_COSTES: desglose población × operación (listado, detalle,
--     clasificacion, enriquecimiento, cartel, telegram, dedupe_juez,
--     embeddings, geocoding...).
--
-- Las escribe CostTracker.persistir_run() al final de cada run (no en dry-run),
-- en todos los destinos (--target both incluido).
--
-- Idempotente: CREATE TABLE IF NOT EXISTS.
-- ============================================================================

SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `INGESTA_RUNS` (
  `ID_Run` INT AUTO_INCREMENT PRIMARY KEY,
  `Inicio` DATETIME NOT NULL,
  `Fin` DATETIME NOT NULL,
  `Target` VARCHAR(20) NOT NULL COMMENT 'local | railway',
  `Modelo` VARCHAR(50) NOT NULL,
  `Parametros` VARCHAR(255) NULL COMMENT 'Flags del run (refresh, hard-reset, max-items...)',
  `Llamadas` INT NOT NULL DEFAULT 0,
  `Tokens_In` BIGINT NOT NULL DEFAULT 0,
  `Tokens_Cached` BIGINT NOT NULL DEFAULT 0,
  `Tokens_Out` BIGINT NOT NULL DEFAULT 0,
  `Coste_USD` DECIMAL(10,4) NOT NULL DEFAULT 0,
  `Imagenes` INT NOT NULL DEFAULT 0,
  `Eventos_Persistidos` INT NOT NULL DEFAULT 0,
  `Noticias_Persistidas` INT NOT NULL DEFAULT 0,
  `Targets_OK` INT NOT NULL DEFAULT 0,
  `Targets_Skip` INT NOT NULL DEFAULT 0,
  `Targets_Error` INT NOT NULL DEFAULT 0,
  INDEX `IDX_RUN_INICIO` (`Inicio`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `INGESTA_COSTES` (
  `ID` INT AUTO_INCREMENT PRIMARY KEY,
  `ID_Run` INT NOT NULL,
  `Poblacion` VARCHAR(255) NOT NULL,
  `Operacion` VARCHAR(50) NOT NULL,
  `Llamadas` INT NOT NULL DEFAULT 0,
  `Tokens_In` BIGINT NOT NULL DEFAULT 0,
  `Tokens_Cached` BIGINT NOT NULL DEFAULT 0,
  `Tokens_Out` BIGINT NOT NULL DEFAULT 0,
  `Coste_USD` DECIMAL(10,4) NOT NULL DEFAULT 0,
  CONSTRAINT `FK_COSTE_RUN` FOREIGN KEY (`ID_Run`)
    REFERENCES `INGESTA_RUNS`(`ID_Run`) ON DELETE CASCADE,
  INDEX `IDX_COSTE_RUN` (`ID_Run`),
  INDEX `IDX_COSTE_POBLACION` (`Poblacion`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SHOW COLUMNS FROM `INGESTA_RUNS`;
SHOW COLUMNS FROM `INGESTA_COSTES`;
