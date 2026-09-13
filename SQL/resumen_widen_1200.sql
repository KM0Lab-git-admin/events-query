-- Amplía NOTICIAS_MASTER.Resumen_* a VARCHAR(1200) para 3 párrafos cortos.
-- Idempotente.

SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

ALTER TABLE `NOTICIAS_MASTER`
  MODIFY COLUMN `Resumen_CAT` VARCHAR(1200) NULL
    COMMENT 'Resumen max 3 frases/parrafos cortos (LLM); es lo persistido',
  MODIFY COLUMN `Resumen_ES` VARCHAR(1200) NULL
    COMMENT 'Resumen max 3 frases/parrafos cortos (LLM); es lo persistido';

SHOW COLUMNS FROM `NOTICIAS_MASTER` LIKE 'Resumen%';
