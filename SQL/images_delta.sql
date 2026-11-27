-- ============================================================================
-- images_delta.sql
-- ============================================================================
-- Añade columnas a BINARIOS_STORAGE para soportar múltiples imágenes por
-- evento con metadatos de orientación, dimensiones y trazabilidad de URL
-- original externa.
--
-- Cambios:
--   - Es_Principal: marca cuál es la imagen principal (única por evento).
--   - Orden: orden de aparición para galerías.
--   - Ancho_Px, Alto_Px: dimensiones en píxeles.
--   - Orientacion: derivada del ratio ancho/alto.
--   - URL_Original_Externa: la URL externa de origen (CDN del ayuntamiento,
--     CDN social, etc.) para auditoría y reproceso.
--
-- Idempotente: si las columnas ya existen, los ALTER fallarán. Comenta los
-- bloques ya aplicados.
-- ============================================================================


-- ----------------------------------------------------------------------------
-- BLOQUE 1: añadir columnas
-- ----------------------------------------------------------------------------

ALTER TABLE `BINARIOS_STORAGE`
  ADD COLUMN `Es_Principal`         TINYINT(1) NOT NULL DEFAULT 0
    COMMENT 'Solo una imagen por evento debería tener Es_Principal=1' AFTER `URL_Almacenamiento_Nube`,
  ADD COLUMN `Orden`                INT NOT NULL DEFAULT 0
    COMMENT 'Orden de aparición para galerías' AFTER `Es_Principal`,
  ADD COLUMN `Ancho_Px`             INT NULL AFTER `Orden`,
  ADD COLUMN `Alto_Px`              INT NULL AFTER `Ancho_Px`,
  ADD COLUMN `Orientacion`          ENUM('horizontal','vertical','cuadrada') NULL
    COMMENT 'Derivada del ratio ancho/alto: <0.80 vertical, >1.20 horizontal, resto cuadrada' AFTER `Alto_Px`,
  ADD COLUMN `URL_Original_Externa` VARCHAR(2048) NULL
    COMMENT 'URL externa de origen (CDN del ayuntamiento, etc.) para auditoría' AFTER `Orientacion`;


-- ----------------------------------------------------------------------------
-- BLOQUE 2: índice para consultas de imagen principal por evento
-- ----------------------------------------------------------------------------

CREATE INDEX `IDX_BINARIO_PRINCIPAL` ON `BINARIOS_STORAGE` (`ID_Unico_Evento`, `Es_Principal`);


-- ----------------------------------------------------------------------------
-- VERIFICACIÓN
-- ----------------------------------------------------------------------------

SHOW COLUMNS FROM `BINARIOS_STORAGE`;
