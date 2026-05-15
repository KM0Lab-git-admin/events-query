-- ============================================================================
-- ESQUEMA DE BASE DE DATOS — Events Query API + módulo de ingesta
-- ============================================================================
-- Versión: 4.0 UNIFICADA (API final + tablas y FKs de SCHEMA_INGESTION_DELTA)
-- Fecha: Mayo 2026
--
-- Incluye:
--   - Modelo API: Tags_EMBEDDING_* y categorías en EVENTOS_MASTER (docs DATA_MODEL)
--   - Ingesta: BIBLIOTECA_FUENTES, SCRAPING_TARGETS, CAPTURAS_RAW, EVENTO_FUENTES,
--     EVENTO_EMBEDDINGS (versionado / JOIN opcional), PHASH_IMAGENES, COVERAGE_METRICS
--
-- EVENTO_EMBEDDINGS coexiste con Tags_Embedding_ES / Tags_Embedding_CAT: la API puede
-- seguir usando las columnas en EVENTOS_MASTER; el pipeline de ingesta puede usar la
-- tabla aparte para versiones de modelo (ver docs/INGESTION_DATA_MODEL.md).
--
-- Greenfield: aplicar solo este fichero. Migración desde BD antigua: ver
-- SQL/SCHEMA_INGESTION_DELTA.sql como referencia de ALTERs incremental.
-- ============================================================================

CREATE DATABASE IF NOT EXISTS events_db 
CHARACTER SET utf8mb4 
COLLATE utf8mb4_unicode_ci;

USE events_db;

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

INSERT INTO `CATEGORIAS` (`ID_Categoria`, `Nombre_ES`, `Nombre_CAT`, `Slug`, `Icono`, `Color_Hex`, `Orden`, `Activo`) VALUES
(1, 'Cultura', 'Cultura', 'cultura', 'palette', '#9C27B0', 1, 1),
(2, 'Deportes', 'Esports', 'deportes', 'sports_soccer', '#4CAF50', 2, 1),
(3, 'Ocio', 'Oci', 'ocio', 'celebration', '#FF9800', 3, 1),
(4, 'Infantil', 'Infantil', 'infantil', 'child_care', '#2196F3', 4, 1),
(5, 'Formación', 'Formació', 'formacion', 'school', '#607D8B', 5, 1),
(6, 'Gastronomía', 'Gastronomia', 'gastronomia', 'restaurant', '#F44336', 6, 1),
(7, 'Música', 'Música', 'musica', 'music_note', '#E91E63', 7, 1),
(8, 'Naturaleza', 'Naturalesa', 'naturaleza', 'park', '#8BC34A', 8, 1);

CREATE TABLE IF NOT EXISTS `FUENTES_FAMILIA` (
  `ID_Familia` VARCHAR(255) PRIMARY KEY,
  `ID_Ciudad` INT NOT NULL,
  `Nombre_Entidad` VARCHAR(255) NOT NULL,
  `URL_Raiz_Global` VARCHAR(2048) NOT NULL,
  CONSTRAINT `FK_FUENTE_CIUDAD` FOREIGN KEY (`ID_Ciudad`) 
    REFERENCES `CIUDADES`(`ID_Ciudad`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- BIBLIOTECA_FUENTES + SCRAPING_TARGETS (ingesta)
-- ============================================================================

CREATE TABLE IF NOT EXISTS `BIBLIOTECA_FUENTES` (
  `ID_Fuente` INT AUTO_INCREMENT PRIMARY KEY,
  `ID_Ciudad` INT NOT NULL,
  `Tipo_Fuente` ENUM('FUENTE_OFICIAL','AGREGADOR','RED_SOCIAL_PERFIL','RED_SOCIAL_QUERY') NOT NULL,
  `Plataforma` ENUM('INSTAGRAM','FACEBOOK','X_TWITTER','TIKTOK') NULL
    COMMENT 'Para redes: actor Apify asociado',
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
  `Plataforma` ENUM('INSTAGRAM','FACEBOOK','X_TWITTER','TIKTOK') NULL,
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
    COMMENT 'Snapshot COVERAGE_METRICS al calcular Next_Run_At',
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

CREATE TABLE IF NOT EXISTS `COVERAGE_METRICS` (
  `ID_Ciudad` INT NOT NULL,
  `Tipo_Fuente` ENUM('FUENTE_OFICIAL','AGREGADOR','RED_SOCIAL_PERFIL','RED_SOCIAL_QUERY') NOT NULL,
  `Eventos_Aportados_30d` INT NOT NULL DEFAULT 0,
  `Eventos_Confirmados_30d` INT NOT NULL DEFAULT 0,
  `Capturas_Sin_Evento_30d` INT NOT NULL DEFAULT 0,
  `Score_Eficiencia` DECIMAL(5,4) NOT NULL DEFAULT 1.0,
  `Frecuencia_Sugerida_Horas` INT NOT NULL DEFAULT 24,
  `Fecha_Calculo` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`ID_Ciudad`, `Tipo_Fuente`),
  INDEX `IDX_COV_TIPO` (`Tipo_Fuente`),
  CONSTRAINT `FK_COV_CIUDAD` FOREIGN KEY (`ID_Ciudad`)
    REFERENCES `CIUDADES`(`ID_Ciudad`) ON DELETE RESTRICT
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
  `CP_Evento` VARCHAR(5) NOT NULL COMMENT 'Campo principal de filtrado geográfico',
  `Poblacion_Nombre` VARCHAR(255) NOT NULL,
  `Lugar_Nombre` VARCHAR(255) NOT NULL,
  `Direccion_Fisica` VARCHAR(255) NULL,
  `Coordenadas_JSON` JSON NULL COMMENT '{"lat": float, "lng": float}',
  `ID_Familia` VARCHAR(255) NULL,
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
  CONSTRAINT `FK_EVENTO_FAMILIA` FOREIGN KEY (`ID_Familia`) 
    REFERENCES `FUENTES_FAMILIA`(`ID_Familia`) ON DELETE RESTRICT
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
-- CAPTURAS_RAW (ingesta: payload inmutable)
-- ============================================================================
CREATE TABLE IF NOT EXISTS `CAPTURAS_RAW` (
  `ID_Captura` BIGINT PRIMARY KEY AUTO_INCREMENT,
  `ID_Target` INT NOT NULL,
  `ID_Fuente` INT NOT NULL,
  `Fecha_Captura` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `Content_Type` VARCHAR(64) NOT NULL,
  `Content_Hash_SHA256` CHAR(64) NOT NULL,
  `Payload_Bytes` LONGBLOB NULL,
  `Payload_Storage_URL` VARCHAR(2048) NULL,
  `Payload_Size_Bytes` BIGINT NOT NULL,
  `Status` ENUM('PENDIENTE_EXTRACCION','EXTRAIDA','ERROR_EXTRACCION','SKIPPED_SIN_CAMBIOS') NOT NULL DEFAULT 'PENDIENTE_EXTRACCION',
  `Extractor_Usado` VARCHAR(64) NULL,
  `Extraccion_Started_At` DATETIME NULL,
  `Extraccion_Ended_At` DATETIME NULL,
  `Coste_Estimado_USD` DECIMAL(10,6) DEFAULT 0,
  INDEX `IDX_CAPTURA_TARGET` (`ID_Target`),
  INDEX `IDX_CAPTURA_FUENTE` (`ID_Fuente`),
  INDEX `IDX_CAPTURA_STATUS_FECHA` (`Status`, `Fecha_Captura`),
  INDEX `IDX_CAPTURA_CONTENT_HASH` (`Content_Hash_SHA256`),
  CONSTRAINT `FK_CAPTURA_TARGET` FOREIGN KEY (`ID_Target`) REFERENCES `SCRAPING_TARGETS` (`ID_Target`),
  CONSTRAINT `FK_CAPTURA_FUENTE` FOREIGN KEY (`ID_Fuente`) REFERENCES `BIBLIOTECA_FUENTES` (`ID_Fuente`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- AUDITORIA_SCRAPING: trazabilidad (con captura y motivo de skip)
-- ============================================================================
CREATE TABLE IF NOT EXISTS `AUDITORIA_SCRAPING` (
  `ID_Auditoria` INT AUTO_INCREMENT PRIMARY KEY,
  `ID_Unico_Evento` CHAR(64) NULL,
  `ID_Captura` BIGINT NULL,
  `Motivo_Skip` ENUM(
    'GATE_DUPLICADO',
    'FILTRO_TEMPORAL',
    'SIN_FECHA_DETECTADA',
    'CONTENIDO_NO_EVENTO',
    'ERROR_EXTRACCION',
    'NA'
  ) NOT NULL DEFAULT 'NA',
  `URL_Procesada` VARCHAR(2048) NULL,
  `Metodo_Usado` VARCHAR(255) NULL,
  `Resultado` ENUM('OK','WARNING','ERROR') NOT NULL DEFAULT 'OK',
  `Detalle` TEXT NULL,
  `Texto_Bruto_Caption` TEXT NULL,
  `Texto_Bruto_OCR` TEXT NULL,
  `Payload_Extra` JSON NULL,
  `Fecha_Ejecucion` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY `IDX_AUDIT_EVENTO` (`ID_Unico_Evento`),
  KEY `IDX_AUDIT_CAPTURA` (`ID_Captura`),
  KEY `IDX_AUDIT_RESULTADO` (`Resultado`),
  KEY `IDX_AUDIT_FECHA` (`Fecha_Ejecucion`),
  CONSTRAINT `FK_AUDIT_EVENTO` FOREIGN KEY (`ID_Unico_Evento`) 
    REFERENCES `EVENTOS_MASTER`(`ID_Unico_Evento`) ON DELETE SET NULL,
  CONSTRAINT `FK_AUDIT_CAPTURA` FOREIGN KEY (`ID_Captura`) 
    REFERENCES `CAPTURAS_RAW`(`ID_Captura`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `EVENTO_FUENTES` (
  `ID_Evento_Fuente` BIGINT PRIMARY KEY AUTO_INCREMENT,
  `ID_Unico_Evento` CHAR(64) NOT NULL,
  `ID_Fuente` INT NOT NULL,
  `ID_Captura` BIGINT NULL,
  `URL_Origen` VARCHAR(2048) NOT NULL,
  `Fecha_Primera_Vez` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `Fecha_Ultima_Confirmacion` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `Es_Fuente_Principal` TINYINT(1) NOT NULL DEFAULT 0,
  `Aporto_Extraccion` TINYINT(1) NOT NULL DEFAULT 1,
  `Score_Calidad` DECIMAL(4,3) NULL,
  UNIQUE INDEX `UQ_EVENTO_FUENTE_URL` (`ID_Unico_Evento`, `URL_Origen`(255)),
  INDEX `IDX_EF_EVENTO` (`ID_Unico_Evento`),
  INDEX `IDX_EF_FUENTE` (`ID_Fuente`),
  INDEX `IDX_EF_CAPTURA` (`ID_Captura`),
  CONSTRAINT `FK_EF_EVENTO` FOREIGN KEY (`ID_Unico_Evento`) REFERENCES `EVENTOS_MASTER` (`ID_Unico_Evento`) ON DELETE CASCADE,
  CONSTRAINT `FK_EF_FUENTE` FOREIGN KEY (`ID_Fuente`) REFERENCES `BIBLIOTECA_FUENTES` (`ID_Fuente`),
  CONSTRAINT `FK_EF_CAPTURA` FOREIGN KEY (`ID_Captura`) REFERENCES `CAPTURAS_RAW` (`ID_Captura`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `EVENTO_EMBEDDINGS` (
  `ID_Embedding` BIGINT PRIMARY KEY AUTO_INCREMENT,
  `ID_Unico_Evento` CHAR(64) NOT NULL,
  `Idioma` CHAR(2) NOT NULL,
  `Modelo` VARCHAR(64) NOT NULL,
  `Dimensiones` INT NOT NULL,
  `Vector_JSON` JSON NOT NULL,
  `Fecha_Generacion` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `Texto_Fuente_Hash` CHAR(64) NOT NULL,
  UNIQUE INDEX `UQ_EMB_EVENTO_IDIOMA_MODELO` (`ID_Unico_Evento`, `Idioma`, `Modelo`),
  INDEX `IDX_EMB_EVENTO` (`ID_Unico_Evento`),
  CONSTRAINT `FK_EMB_EVENTO` FOREIGN KEY (`ID_Unico_Evento`) REFERENCES `EVENTOS_MASTER` (`ID_Unico_Evento`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `PHASH_IMAGENES` (
  `ID_Phash` BIGINT PRIMARY KEY AUTO_INCREMENT,
  `Phash_Hex` CHAR(32) UNIQUE NOT NULL,
  `ID_Binario` INT NULL,
  `Extraccion_JSON` JSON NULL,
  `Veces_Reutilizado` INT NOT NULL DEFAULT 0,
  `Fecha_Primera_Vez` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `Fecha_Ultimo_Hit` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX `IDX_PHASH_BINARIO` (`ID_Binario`),
  CONSTRAINT `FK_PHASH_BINARIO` FOREIGN KEY (`ID_Binario`) REFERENCES `BINARIOS_STORAGE` (`ID_Binario`) ON DELETE SET NULL
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
  GROUP_CONCAT(DISTINCT c.Nombre_ES SEPARATOR ', ') AS Categorias_ES,
  GROUP_CONCAT(DISTINCT c.Nombre_CAT SEPARATOR ', ') AS Categorias_CAT,
  GROUP_CONCAT(DISTINCT c.Slug SEPARATOR ',') AS Categorias_Slugs
FROM EVENTOS_MASTER em
JOIN EVENTO_HORARIOS eh ON em.ID_Unico_Evento = eh.ID_Unico_Evento
JOIN CODIGOS_POSTALES cp ON em.CP_Evento = cp.CP
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
2. Capturar → CAPTURAS_RAW; extraer → EVENTOS_MASTER + EVENTO_FUENTES
3. Embeddings: Tags_Embedding_* en EVENTOS_MASTER y/o filas en EVENTO_EMBEDDINGS
4. Imágenes: BINARIOS_STORAGE + PHASH_IMAGENES para cache LLM-Vision

FLUJO DE BÚSQUEDA (API):
Pre-filtrado SQL + similitud sobre Tags_Embedding_ES o Tags_Embedding_CAT según idioma.
*/

-- FIN DEL ESQUEMA
