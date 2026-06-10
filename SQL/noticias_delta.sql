-- ============================================================================
-- noticias_delta.sql
-- ============================================================================
-- Añade el modelo de NOTICIAS al esquema: contenido informativo de los
-- municipios (comunicados, avisos, noticias de webs oficiales, radio local,
-- redes sociales) que NO es un evento con fecha/horario/recinto.
--
-- Decisión de diseño: tabla separada de EVENTOS_MASTER. Una noticia no tiene
-- horarios ni recinto, y su ciclo de vida es distinto (caduca por antigüedad
-- vía Fecha_Caducidad = Fecha_Publicacion + TTL, no por fecha de celebración).
--
-- Tablas:
--   - NOTICIAS_MASTER: la noticia (bilingüe CA/ES, tags, vigencia).
--   - NOTICIA_BINARIOS: imágenes de la noticia. Espejo de BINARIOS_STORAGE
--     (que tiene FK a EVENTOS_MASTER y no se puede reutilizar) con FK a
--     NOTICIAS_MASTER ON DELETE CASCADE.
--
-- Idempotente: CREATE TABLE IF NOT EXISTS. Re-ejecutable sin efectos.
-- ============================================================================

SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- BLOQUE 1: NOTICIAS_MASTER
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS `NOTICIAS_MASTER` (
  `ID_Unico_Noticia` CHAR(64) PRIMARY KEY
    COMMENT 'SHA-256 de poblacion|titulo normalizado (mismo patrón que ID_Unico_Evento)',
  `ID_Ciudad` INT NOT NULL,
  `ID_Fuente` INT NULL
    COMMENT 'FK a BIBLIOTECA_FUENTES: fuente principal de la noticia',
  `Fuente_URL_Original` VARCHAR(2048) NULL,
  `Titulo_CAT` VARCHAR(255) NOT NULL,
  `Titulo_ES` VARCHAR(255) NOT NULL,
  `Cuerpo_CAT` TEXT NULL,
  `Cuerpo_ES` TEXT NULL,
  `Tags_CAT` JSON NULL,
  `Tags_ES` JSON NULL,
  `Fecha_Publicacion` DATE NOT NULL,
  `Fecha_Caducidad` DATE NULL
    COMMENT 'Calculada en ingesta: Fecha_Publicacion + NEWS_TTL_DIAS (default 45)',
  `Estado` ENUM('ACTIVA','ARCHIVADA') NOT NULL DEFAULT 'ACTIVA',
  `Imagen_Principal_URL` VARCHAR(2048) NULL,
  `Idioma_Origen` CHAR(2) NOT NULL DEFAULT 'ca',
  `Fecha_Creacion` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT `FK_NOTICIA_CIUDAD` FOREIGN KEY (`ID_Ciudad`)
    REFERENCES `CIUDADES`(`ID_Ciudad`) ON DELETE RESTRICT,
  CONSTRAINT `FK_NOTICIA_FUENTE` FOREIGN KEY (`ID_Fuente`)
    REFERENCES `BIBLIOTECA_FUENTES`(`ID_Fuente`) ON DELETE SET NULL,
  INDEX `IDX_NOTICIA_CIUDAD_ESTADO` (`ID_Ciudad`, `Estado`, `Fecha_Publicacion`),
  INDEX `IDX_NOTICIA_CADUCIDAD` (`Estado`, `Fecha_Caducidad`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- BLOQUE 2: NOTICIA_BINARIOS (imágenes de noticias)
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS `NOTICIA_BINARIOS` (
  `ID_Binario` INT AUTO_INCREMENT PRIMARY KEY,
  `ID_Unico_Noticia` CHAR(64) NOT NULL,
  `Nombre_Archivo` VARCHAR(255) NOT NULL,
  `Tipo_Archivo` ENUM('JPG','JPEG','PNG','WEBP') NOT NULL,
  `URL_Almacenamiento_Nube` VARCHAR(2048) NOT NULL,
  `Es_Principal` TINYINT(1) NOT NULL DEFAULT 0,
  `Orden` INT NOT NULL DEFAULT 0,
  `Ancho_Px` INT NULL,
  `Alto_Px` INT NULL,
  `Orientacion` ENUM('horizontal','vertical','cuadrada') NULL,
  `URL_Original_Externa` VARCHAR(2048) NULL,
  `Checksum_SHA256` CHAR(64) NULL,
  `Fecha_Sincronizacion` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY `IDX_NBINARIO_NOTICIA` (`ID_Unico_Noticia`),
  CONSTRAINT `FK_NBINARIO_NOTICIA` FOREIGN KEY (`ID_Unico_Noticia`)
    REFERENCES `NOTICIAS_MASTER`(`ID_Unico_Noticia`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- VERIFICACIÓN
-- ----------------------------------------------------------------------------

SHOW COLUMNS FROM `NOTICIAS_MASTER`;
SHOW COLUMNS FROM `NOTICIA_BINARIOS`;
