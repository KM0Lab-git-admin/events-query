-- ============================================================================
-- ESQUEMA DE BASE DE DATOS — Events Query API + módulo de ingesta
-- ============================================================================
-- Versión: 4.0 UNIFICADA (API + ingesta + RECINTOS; fuente única de DDL)
-- Fecha: Mayo 2026
--
-- Incluye:
--   - Modelo API: Tags_EMBEDDING_* y categorías en EVENTOS_MASTER (docs DATA_MODEL)
--   - Ingesta: BIBLIOTECA_FUENTES, SCRAPING_TARGETS, EVENTO_FUENTES
--   - Recintos: RECINTOS, EVENTOS_MASTER.ID_Recinto
--
-- Embeddings en columnas Tags_Embedding_* en EVENTOS_MASTER (sin tabla aparte).
--
-- Greenfield: aplicar solo este fichero. MySQL en Docker usa la copia en scripts/schema.sql.
-- ============================================================================

CREATE DATABASE IF NOT EXISTS events_db 
CHARACTER SET utf8mb4 
COLLATE utf8mb4_unicode_ci;

USE events_db;

-- Sesión UTF-8 para literales del script (evita mojibake al importar).
SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

-- ============================================================================
-- TABLAS DE CATÁLOGO
-- ============================================================================

CREATE TABLE IF NOT EXISTS `CIUDADES` (
  `ID_Ciudad` INT AUTO_INCREMENT PRIMARY KEY,
  `Nombre` VARCHAR(255) UNIQUE NOT NULL,
  `Provincia` VARCHAR(255) NULL,
  `Latitud` DECIMAL(10,8) NULL,
  `Longitud` DECIMAL(11,8) NULL,
  INDEX `idx_ciudad_coords` (`Latitud`, `Longitud`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `CODIGOS_POSTALES` (
  `CP` VARCHAR(5) PRIMARY KEY,
  `ID_Ciudad` INT NULL,
  `Latitud` DECIMAL(10,8) NOT NULL,
  `Longitud` DECIMAL(11,8) NOT NULL,
  `Barrio_Distrito` VARCHAR(255) NULL,
  CONSTRAINT `FK_CP_CIUDAD` FOREIGN KEY (`ID_Ciudad`) 
    REFERENCES `CIUDADES`(`ID_Ciudad`) ON DELETE RESTRICT,
  INDEX `idx_cp_coords` (`Latitud`, `Longitud`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- CATEGORIAS: Catálogo cerrado de categorías
-- ============================================================================
CREATE TABLE IF NOT EXISTS `CATEGORIAS` (
  `ID_Categoria` INT AUTO_INCREMENT PRIMARY KEY,
  `Nombre_ES` VARCHAR(100) NOT NULL,
  `Nombre_CAT` VARCHAR(100) NOT NULL,
  `Slug` VARCHAR(100) UNIQUE NOT NULL,
  `Descripcion_ES` TEXT NULL,
  `Descripcion_CAT` TEXT NULL,
  `Icono` VARCHAR(50) NULL,
  `Color_Hex` CHAR(7) NULL,
  `Orden` INT NOT NULL DEFAULT 0,
  `Activo` TINYINT(1) NOT NULL DEFAULT 1,
  INDEX `idx_categoria_slug` (`Slug`),
  INDEX `idx_categoria_activo` (`Activo`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================================
-- BIBLIOTECA_FUENTES + SCRAPING_TARGETS (ingesta)
-- ============================================================================

CREATE TABLE IF NOT EXISTS `BIBLIOTECA_FUENTES` (
  `ID_Fuente` INT AUTO_INCREMENT PRIMARY KEY,
  `ID_Ciudad` INT NOT NULL,
  `Tipo_Fuente` ENUM('FUENTE_OFICIAL','AGREGADOR','RED_SOCIAL_PERFIL','RED_SOCIAL_QUERY') NOT NULL,
  `Tipo_Contenido` ENUM('EVENTOS','NOTICIAS','MIXTO') NOT NULL DEFAULT 'MIXTO'
    COMMENT 'Hint para el clasificador: qué suele contener la fuente',
  `Plataforma` ENUM('INSTAGRAM','FACEBOOK','X_TWITTER','TIKTOK','YOUTUBE','TELEGRAM') NULL
    COMMENT 'Para redes: actor Apify asociado (TELEGRAM: scraping directo t.me/s)',
  `Handle` VARCHAR(255) NULL COMMENT 'Cuenta para RED_SOCIAL_PERFIL',
  `Query_Default` VARCHAR(512) NULL COMMENT 'Búsqueda por defecto para RED_SOCIAL_QUERY',
  `Hashtags_JSON` JSON NULL,
  `URL_Base` VARCHAR(2048) NOT NULL COMMENT 'URL canónica del sitio o cuenta',
  `Activa` TINYINT(1) NOT NULL DEFAULT 1,
  `Prioridad` INT NOT NULL DEFAULT 100 COMMENT 'Menor = más prioritario en scheduler',
  `Config_JSON` JSON DEFAULT NULL
    COMMENT 'Selectores CSS, actor Apify, mapping de API, etc.',
  `Notas` TEXT NULL,
  `Fecha_Alta` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `Fecha_Modificacion` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT `FK_BF_CIUDAD` FOREIGN KEY (`ID_Ciudad`)
    REFERENCES `CIUDADES`(`ID_Ciudad`) ON DELETE RESTRICT,
  INDEX `IDX_BF_CIUDAD` (`ID_Ciudad`),
  INDEX `IDX_BF_TIPO_ACTIVA` (`Tipo_Fuente`, `Activa`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `SCRAPING_TARGETS` (
  `ID_Target` INT AUTO_INCREMENT PRIMARY KEY,
  `ID_Fuente` INT NOT NULL COMMENT 'FK a BIBLIOTECA_FUENTES (ver docs/INGESTION_DATA_MODEL.md)',
  `ID_Ciudad` INT NOT NULL,
  `Tipo_Target` ENUM(
    'WEB_LISTADO',
    'WEB_DETALLE',
    'WEB_SITEMAP',
    'API_AGREGADOR',
    'SOCIAL_PERFIL',
    'SOCIAL_QUERY'
  ) NOT NULL,
  `Plataforma` ENUM('INSTAGRAM','FACEBOOK','X_TWITTER','TIKTOK','YOUTUBE','TELEGRAM') NULL,
  `URL_Target` VARCHAR(2048) NULL,
  `Query_Target` VARCHAR(255) NULL,
  `Origen_Tabla` VARCHAR(64) NOT NULL,
  `Origen_ID` VARCHAR(255) NOT NULL,
  `Estado` ENUM('PENDIENTE','PROCESANDO','OK','ERROR','PAUSADO') NOT NULL DEFAULT 'PENDIENTE',
  `Frecuencia_Horas` INT NOT NULL DEFAULT 24
    COMMENT 'Frecuencia efectiva tras scheduling adaptativo',
  `Frecuencia_Base_Horas` INT NOT NULL DEFAULT 24
    COMMENT 'Frecuencia configurada manualmente',
  `Coverage_Score` DECIMAL(5,4) NULL
    COMMENT 'Métrica opcional de scheduling (sin tabla propia)',
  `Capturas_Utiles_Consecutivas` INT NOT NULL DEFAULT 0,
  `Capturas_Vacias_Consecutivas` INT NOT NULL DEFAULT 0,
  `Next_Run_At` DATETIME NULL,
  `Last_Run_At` DATETIME NULL,
  `Intentos` INT NOT NULL DEFAULT 0,
  `Last_Error` TEXT NULL,
  `Http_ETag` VARCHAR(255) NULL,
  `Http_LastModified` VARCHAR(255) NULL,
  `Content_Fingerprint` CHAR(64) NULL,
  `Last_Changed_At` DATETIME NULL,
  CONSTRAINT `FK_TARGET_FUENTE` FOREIGN KEY (`ID_Fuente`)
    REFERENCES `BIBLIOTECA_FUENTES`(`ID_Fuente`) ON DELETE RESTRICT,
  CONSTRAINT `FK_TARGET_CIUDAD` FOREIGN KEY (`ID_Ciudad`)
    REFERENCES `CIUDADES`(`ID_Ciudad`) ON DELETE RESTRICT,
  UNIQUE INDEX `UQ_TARGET_ORIGEN` (`Origen_Tabla`, `Origen_ID`),
  INDEX `IDX_TARGET_NEXT` (`Estado`, `Next_Run_At`),
  INDEX `IDX_TARGET_COVERAGE` (`Coverage_Score`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- RECINTOS: lugares canónicos (CSV / ingesta)
-- ============================================================================
CREATE TABLE IF NOT EXISTS `RECINTOS` (
  `ID_Recinto` INT AUTO_INCREMENT PRIMARY KEY,
  `ID_Ciudad` INT NOT NULL,
  `CP` VARCHAR(5) NOT NULL,
  `Nombre_Canonico` VARCHAR(255) NOT NULL,
  `Tipo` ENUM('BIBLIOTECA','CENTRO_CULTURAL','TEATRO','PARQUE','OTRO') NOT NULL DEFAULT 'OTRO',
  `Direccion_Fisica` VARCHAR(255) NULL,
  `Coordenadas_JSON` JSON NULL,
  `Notas` TEXT NULL,
  `Fuente_Datos` VARCHAR(255) NULL COMMENT 'p.ej. import_csv, manual',
  `Fecha_Alta` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT `FK_RECINTO_CIUDAD` FOREIGN KEY (`ID_Ciudad`)
    REFERENCES `CIUDADES`(`ID_Ciudad`) ON DELETE RESTRICT,
  CONSTRAINT `FK_RECINTO_CP` FOREIGN KEY (`CP`)
    REFERENCES `CODIGOS_POSTALES`(`CP`) ON DELETE RESTRICT,
  INDEX `IDX_RECINTO_CIUDAD` (`ID_Ciudad`),
  INDEX `IDX_RECINTO_CP` (`CP`),
  UNIQUE KEY `UQ_RECINTO_CIUDAD_DIRECCION` (`ID_Ciudad`, `Direccion_Fisica`(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- EVENTOS_MASTER: Tabla principal con TAGS SEPARADOS POR IDIOMA
-- ============================================================================
CREATE TABLE IF NOT EXISTS `EVENTOS_MASTER` (
  `ID_Unico_Evento` CHAR(64) PRIMARY KEY COMMENT 'Hash SHA-256 único',
  `Metodo_Ingesta` ENUM('SCRAPING','MANUAL') NOT NULL,
  `ID_Usuario_Carga` VARCHAR(255) NOT NULL,
  `Fuente_ID` ENUM('URL_ESTRUCTURAL','SOCIAL_VISUAL','SOCIAL_SEMANTICA') NOT NULL,
  `Fuente_URL_Original` VARCHAR(2048) NULL,
  `Estado` ENUM('ACTIVO','CANCELADO','APLAZADO') NOT NULL DEFAULT 'ACTIVO',
  `Fecha_Creacion` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `ID_Ciudad` INT NULL,
  `ID_Recinto` INT NULL COMMENT 'Lugar canónico; Lugar_Nombre/Direccion siguen rellenos para API',
  `CP_Evento` VARCHAR(5) NOT NULL COMMENT 'Campo principal de filtrado geográfico',
  `Poblacion_Nombre` VARCHAR(255) NOT NULL,
  `Lugar_Nombre` VARCHAR(255) NOT NULL,
  `Direccion_Fisica` VARCHAR(255) NULL,
  `Coordenadas_JSON` JSON NULL COMMENT '{"lat": float, "lng": float}',
  `ID_Familia` CHAR(64) NULL COMMENT 'ID del evento cabeza de familia (agrupación, no fusión)',
  `Tipo_Organizador` ENUM('PUBLICO','PRIVADO','ASOCIACION') NULL,
  `Organizador_Nombre` VARCHAR(255) NULL,
  `Organizador_Web` VARCHAR(2048) NULL,
  `Es_Patrocinado` TINYINT(1) NOT NULL DEFAULT 0,
  `Idioma_Origen` CHAR(2) NOT NULL COMMENT 'ca o es',
  `Titulo_CAT` VARCHAR(255) NOT NULL,
  `Titulo_ES` VARCHAR(255) NOT NULL,
  `Desc_Larga_CAT` TEXT NULL,
  `Desc_Larga_ES` TEXT NULL,
  `Tags_ES` JSON NULL,
  `Tags_CAT` JSON NULL,
  `Tags_Embedding_ES` JSON NULL COMMENT 'Vector embedding de Tags_ES',
  `Tags_Embedding_CAT` JSON NULL COMMENT 'Vector embedding de Tags_CAT',
  `Es_Gratuito` TINYINT(1) NOT NULL,
  `Precio_Euros` DECIMAL(10,2) NULL,
  `Requiere_Inscripcion` TINYINT(1) NOT NULL,
  `Aforo_Maximo` INT NULL,
  `Plazas_Disponibles` INT NULL,
  `Link_Entradas_Inscripcion` VARCHAR(2048) NULL,
  `Imagen_Principal_URL` VARCHAR(2048) NULL,
  KEY `IDX_EVENTO_CP_ESTADO` (`CP_Evento`, `Estado`),
  KEY `IDX_EVENTO_CIUDAD` (`ID_Ciudad`),
  KEY `IDX_EVENTO_GRATUITO` (`Es_Gratuito`),
  CONSTRAINT `FK_EVENTO_CP` FOREIGN KEY (`CP_Evento`) 
    REFERENCES `CODIGOS_POSTALES`(`CP`) ON DELETE RESTRICT,
  CONSTRAINT `FK_EVENTO_CIUDAD` FOREIGN KEY (`ID_Ciudad`) 
    REFERENCES `CIUDADES`(`ID_Ciudad`) ON DELETE RESTRICT,
  CONSTRAINT `FK_EVENTO_RECINTO` FOREIGN KEY (`ID_Recinto`)
    REFERENCES `RECINTOS`(`ID_Recinto`) ON DELETE SET NULL,
  INDEX `IDX_EVENTO_RECINTO` (`ID_Recinto`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Tabla principal con tags y embeddings separados por idioma';

CREATE TABLE IF NOT EXISTS `EVENTO_CATEGORIAS` (
  `ID_Unico_Evento` CHAR(64) NOT NULL,
  `ID_Categoria` INT NOT NULL,
  PRIMARY KEY (`ID_Unico_Evento`, `ID_Categoria`),
  CONSTRAINT `FK_EVCAT_EVENTO` FOREIGN KEY (`ID_Unico_Evento`) 
    REFERENCES `EVENTOS_MASTER`(`ID_Unico_Evento`) ON DELETE CASCADE,
  CONSTRAINT `FK_EVCAT_CATEGORIA` FOREIGN KEY (`ID_Categoria`) 
    REFERENCES `CATEGORIAS`(`ID_Categoria`) ON DELETE RESTRICT,
  INDEX `idx_evento_categoria` (`ID_Categoria`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `EVENTO_HORARIOS` (
  `ID_Horario` INT AUTO_INCREMENT PRIMARY KEY,
  `ID_Unico_Evento` CHAR(64) NOT NULL,
  `Fecha_Inicio` DATE NOT NULL,
  `Fecha_Fin` DATE NULL,
  `Hora_Inicio` TIME NULL,
  `Hora_Fin` TIME NULL,
  `Es_Recurrente` TINYINT(1) NOT NULL DEFAULT 0,
  `Recurrencia_JSON` JSON NULL,
  `Horario_Texto_ES` VARCHAR(255) NULL,
  CONSTRAINT `FK_HORARIO_EVENTO` FOREIGN KEY (`ID_Unico_Evento`) 
    REFERENCES `EVENTOS_MASTER`(`ID_Unico_Evento`) ON DELETE CASCADE,
  INDEX `idx_horario_fecha` (`Fecha_Inicio`),
  INDEX `idx_horario_evento_fecha` (`ID_Unico_Evento`, `Fecha_Inicio`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `BINARIOS_STORAGE` (
  `ID_Binario` INT AUTO_INCREMENT PRIMARY KEY,
  `ID_Unico_Evento` CHAR(64) NOT NULL,
  `Nombre_Archivo` VARCHAR(255) NOT NULL,
  `Tipo_Archivo` ENUM('PDF','JPG','JPEG','PNG','WEBP','DOCX') NOT NULL,
  `URL_Almacenamiento_Nube` VARCHAR(2048) NOT NULL,
  `Checksum_SHA256` CHAR(64) NULL,
  `Fecha_Sincronizacion` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY `IDX_BINARIO_EVENTO` (`ID_Unico_Evento`),
  CONSTRAINT `FK_BINARIO_EVENTO` FOREIGN KEY (`ID_Unico_Evento`) 
    REFERENCES `EVENTOS_MASTER`(`ID_Unico_Evento`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- EVENTO_FUENTES (trazabilidad URL por evento → BIBLIOTECA_FUENTES)
-- ============================================================================
CREATE TABLE IF NOT EXISTS `EVENTO_FUENTES` (
  `ID_Evento_Fuente` BIGINT PRIMARY KEY AUTO_INCREMENT,
  `ID_Unico_Evento` CHAR(64) NOT NULL,
  `ID_Fuente` INT NOT NULL,
  `URL_Origen` VARCHAR(2048) NOT NULL,
  `Fecha_Primera_Vez` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `Fecha_Ultima_Confirmacion` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `Es_Fuente_Principal` TINYINT(1) NOT NULL DEFAULT 0,
  `Aporto_Extraccion` TINYINT(1) NOT NULL DEFAULT 1,
  `Score_Calidad` DECIMAL(4,3) NULL,
  UNIQUE INDEX `UQ_EVENTO_FUENTE_URL` (`ID_Unico_Evento`, `URL_Origen`(255)),
  INDEX `IDX_EF_EVENTO` (`ID_Unico_Evento`),
  INDEX `IDX_EF_FUENTE` (`ID_Fuente`),
  CONSTRAINT `FK_EF_EVENTO` FOREIGN KEY (`ID_Unico_Evento`) REFERENCES `EVENTOS_MASTER` (`ID_Unico_Evento`) ON DELETE CASCADE,
  CONSTRAINT `FK_EF_FUENTE` FOREIGN KEY (`ID_Fuente`) REFERENCES `BIBLIOTECA_FUENTES` (`ID_Fuente`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- NOTICIAS: contenido informativo municipal (sin horarios ni recinto)
-- ============================================================================
-- Tabla separada de EVENTOS_MASTER: ciclo de vida distinto (caduca por
-- antigüedad vía Fecha_Caducidad, no por fecha de celebración).

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

-- ============================================================================
-- VISTAS ÚTILES
-- ============================================================================

CREATE OR REPLACE VIEW `V_EVENTOS_COMPLETOS` AS
SELECT 
  em.*,
  eh.Fecha_Inicio,
  eh.Fecha_Fin,
  eh.Hora_Inicio,
  eh.Hora_Fin,
  cp.Latitud AS CP_Latitud,
  cp.Longitud AS CP_Longitud,
  MAX(r.Nombre_Canonico) AS Recinto_Nombre_Canonico,
  MAX(r.Tipo) AS Recinto_Tipo,
  MAX(r.Direccion_Fisica) AS Recinto_Direccion_Fisica,
  GROUP_CONCAT(DISTINCT c.Nombre_ES SEPARATOR ', ') AS Categorias_ES,
  GROUP_CONCAT(DISTINCT c.Nombre_CAT SEPARATOR ', ') AS Categorias_CAT,
  GROUP_CONCAT(DISTINCT c.Slug SEPARATOR ',') AS Categorias_Slugs
FROM EVENTOS_MASTER em
JOIN EVENTO_HORARIOS eh ON em.ID_Unico_Evento = eh.ID_Unico_Evento
JOIN CODIGOS_POSTALES cp ON em.CP_Evento = cp.CP
LEFT JOIN RECINTOS r ON em.ID_Recinto = r.ID_Recinto
LEFT JOIN EVENTO_CATEGORIAS ec ON em.ID_Unico_Evento = ec.ID_Unico_Evento
LEFT JOIN CATEGORIAS c ON ec.ID_Categoria = c.ID_Categoria
WHERE em.Estado = 'ACTIVO'
GROUP BY em.ID_Unico_Evento, eh.ID_Horario;

-- ============================================================================
-- NOTAS
-- ============================================================================

/*
FLUJO DE INGESTA (IA externa):
1. Registrar BIBLIOTECA_FUENTES y SCRAPING_TARGETS
2. Extraer → EVENTOS_MASTER + EVENTO_FUENTES (+ EVENTO_HORARIOS / categorías según extractor)
3. Embeddings opcionales: columnas Tags_Embedding_* en EVENTOS_MASTER
4. Imágenes: BINARIOS_STORAGE

FLUJO DE BÚSQUEDA (API):
Pre-filtrado SQL + similitud sobre Tags_Embedding_ES o Tags_Embedding_CAT según idioma.
*/

-- FIN DEL ESQUEMA
