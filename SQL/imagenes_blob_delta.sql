-- ============================================================================
-- imagenes_blob_delta.sql
-- ============================================================================
-- Persistencia durable de bytes de imagen (eventos/noticias) para que
-- sobrevivan a deploys en Railway (disco efímero del contenedor).
--
-- Idempotente vía CREATE TABLE IF NOT EXISTS.
-- ============================================================================

CREATE TABLE IF NOT EXISTS `IMAGENES_BLOB` (
  `ID_Unico` CHAR(64) NOT NULL
    COMMENT 'ID_Unico_Evento o ID_Unico_Noticia',
  `Nombre_Archivo` VARCHAR(255) NOT NULL,
  `Contenido` LONGBLOB NOT NULL,
  `Content_Type` VARCHAR(64) NULL,
  `Bytes` INT NOT NULL,
  `Actualizado` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`ID_Unico`, `Nombre_Archivo`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
