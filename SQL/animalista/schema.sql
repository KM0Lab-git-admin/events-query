-- ============================================================================
-- schema.sql — El Viajero Animalista (animalista_db)
-- ============================================================================
-- Base de datos SEPARADA de events_db (KM0 LAB). Comparte código con el
-- pipeline de KM0 pero no tablas ni prompts. Diseño en
-- docs/VIAJERO-ANIMALISTA-DISENO.md §3.
--
-- Idempotente: CREATE ... IF NOT EXISTS. Orden de aplicación:
--   1. schema.sql            (este fichero)
--   2. seed_geo.sql          (CCAA + provincias + alias)
--   3. seed_taxonomia.sql    (temas + animales)
--   4. python scripts/animalista/load_geo_ine.py   (municipios desde el INE)
--
-- Docker (MySQL de docker-compose, usuario root):
--   Get-Content .\SQL\animalista\schema.sql -Raw | docker exec -i events-mysql mysql -u root -prootpassword
-- ============================================================================

CREATE DATABASE IF NOT EXISTS `animalista_db`
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Permisos del usuario de aplicación: SQL/animalista/grant_local.sql (solo docker).
-- En Railway el usuario y los permisos los da el servicio MySQL.

USE `animalista_db`;
SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- MAESTROS GEOGRÁFICOS (INE)
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS `GEO_CCAA` (
  `Codigo_INE` CHAR(2) PRIMARY KEY,
  `Nombre` VARCHAR(80) NOT NULL,
  `Nombre_Norm` VARCHAR(80) NOT NULL COMMENT 'minúsculas, sin acentos',
  UNIQUE INDEX `UQ_CCAA_NORM` (`Nombre_Norm`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `GEO_PROVINCIAS` (
  `Codigo_INE` CHAR(2) PRIMARY KEY,
  `Nombre` VARCHAR(80) NOT NULL,
  `Nombre_Norm` VARCHAR(80) NOT NULL,
  `Codigo_CCAA` CHAR(2) NOT NULL,
  CONSTRAINT `FK_PROV_CCAA` FOREIGN KEY (`Codigo_CCAA`) REFERENCES `GEO_CCAA`(`Codigo_INE`),
  INDEX `IDX_PROV_NORM` (`Nombre_Norm`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `GEO_MUNICIPIOS` (
  `Codigo_INE` CHAR(5) PRIMARY KEY COMMENT 'CPRO + CMUN',
  `Nombre` VARCHAR(120) NOT NULL COMMENT 'Con artículo delante: A Coruña',
  `Nombre_Norm` VARCHAR(120) NOT NULL,
  `Nombre_INE` VARCHAR(120) NOT NULL COMMENT 'Tal como lo publica el INE: Coruña, A',
  `Codigo_Provincia` CHAR(2) NOT NULL,
  `Poblacion` INT NULL,
  `Lat` DECIMAL(10,7) NULL COMMENT 'Fase posterior (mapa)',
  `Lng` DECIMAL(10,7) NULL,
  CONSTRAINT `FK_MUN_PROV` FOREIGN KEY (`Codigo_Provincia`) REFERENCES `GEO_PROVINCIAS`(`Codigo_INE`),
  INDEX `IDX_MUN_NORM` (`Nombre_Norm`),
  INDEX `IDX_MUN_PROV` (`Codigo_Provincia`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Nombres alternativos que aparecen en prensa (Vizcaya, Catalunya, Mallorca…)
CREATE TABLE IF NOT EXISTS `GEO_ALIAS` (
  `Alias_Norm` VARCHAR(120) NOT NULL,
  `Nivel` ENUM('CCAA','PROVINCIA','MUNICIPIO') NOT NULL,
  `Codigo_INE` VARCHAR(5) NOT NULL,
  PRIMARY KEY (`Alias_Norm`, `Nivel`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- TAXONOMÍA (catálogos cerrados; los tipos y ámbitos son ENUM)
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS `CAT_TEMAS` (
  `Slug` VARCHAR(40) PRIMARY KEY,
  `Nombre` VARCHAR(80) NOT NULL,
  `Descripcion` VARCHAR(255) NULL,
  `Orden` INT NOT NULL DEFAULT 100,
  `Activo` TINYINT(1) NOT NULL DEFAULT 1
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `CAT_ANIMALES` (
  `Slug` VARCHAR(40) PRIMARY KEY,
  `Nombre` VARCHAR(80) NOT NULL,
  `Grupo` VARCHAR(40) NOT NULL COMMENT 'prioritario | otros domésticos | otros | transversal',
  `Orden` INT NOT NULL DEFAULT 100,
  `Activo` TINYINT(1) NOT NULL DEFAULT 1
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- FUENTES Y TARGETS (mismo patrón que BIBLIOTECA_FUENTES / SCRAPING_TARGETS
-- de KM0, sin ID_Ciudad: la geografía es un sesgo opcional de la fuente)
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS `FUENTES` (
  `ID_Fuente` INT AUTO_INCREMENT PRIMARY KEY,
  `Nombre` VARCHAR(160) NOT NULL,
  `Tipo_Fuente` ENUM('OFICIAL','MEDIO','PORTAL','ASOCIACION','AGREGADOR','RED_SOCIAL','FEED_CONSULTA') NOT NULL,
  `Tipo_Contenido` ENUM('NOTICIAS','EVENTOS','MIXTO') NOT NULL DEFAULT 'MIXTO'
    COMMENT 'Hint para el clasificador',
  `URL_Base` VARCHAR(2048) NOT NULL,
  `URL_Hash` CHAR(64) NOT NULL COMMENT 'sha256(URL_Base), lo calcula el script; clave de upsert',
  `Plataforma` ENUM('TELEGRAM','INSTAGRAM','FACEBOOK','X_TWITTER','YOUTUBE') NULL,
  `Handle` VARCHAR(255) NULL,
  `Ambito_Default` ENUM('NACIONAL','CCAA','PROVINCIA','MUNICIPIO') NULL
    COMMENT 'Sesgo geográfico de la fuente (un ayuntamiento ya dice el municipio)',
  `Codigo_Geo_Default` VARCHAR(5) NULL,
  `Imagenes_Permitidas` TINYINT(1) NOT NULL DEFAULT 0
    COMMENT '1 = se descargan imágenes de esta fuente; 0 = portada IA o sin imagen',
  `Activa` TINYINT(1) NOT NULL DEFAULT 1,
  `Prioridad` INT NOT NULL DEFAULT 100,
  `Config_JSON` JSON NULL,
  `Notas` TEXT NULL,
  `Fecha_Alta` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `Fecha_Modificacion` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE INDEX `UQ_FUENTE_URL` (`URL_Hash`),
  INDEX `IDX_FUENTE_TIPO_ACTIVA` (`Tipo_Fuente`, `Activa`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `TARGETS` (
  `ID_Target` INT AUTO_INCREMENT PRIMARY KEY,
  `ID_Fuente` INT NOT NULL,
  `Tipo_Target` ENUM('RSS','WEB_LISTADO','WEB_DETALLE','API','SOCIAL_PERFIL') NOT NULL,
  `URL_Target` VARCHAR(2048) NOT NULL,
  `Origen_Tabla` VARCHAR(64) NOT NULL DEFAULT 'semilla',
  `Origen_ID` VARCHAR(255) NOT NULL,
  `Estado` ENUM('PENDIENTE','PROCESANDO','OK','ERROR','PAUSADO') NOT NULL DEFAULT 'PENDIENTE',
  `Capturas_Utiles_Consecutivas` INT NOT NULL DEFAULT 0,
  `Capturas_Vacias_Consecutivas` INT NOT NULL DEFAULT 0,
  `Last_Run_At` DATETIME NULL,
  `Intentos` INT NOT NULL DEFAULT 0,
  `Last_Error` TEXT NULL,
  `Http_ETag` VARCHAR(255) NULL,
  `Http_LastModified` VARCHAR(255) NULL,
  `Content_Fingerprint` CHAR(64) NULL,
  `Last_Changed_At` DATETIME NULL,
  CONSTRAINT `FK_ATARGET_FUENTE` FOREIGN KEY (`ID_Fuente`) REFERENCES `FUENTES`(`ID_Fuente`) ON DELETE CASCADE,
  UNIQUE INDEX `UQ_ATARGET_ORIGEN` (`Origen_Tabla`, `Origen_ID`),
  INDEX `IDX_ATARGET_ESTADO` (`Estado`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- CONTENIDOS (una tabla para todos los tipos; cinco dimensiones separadas)
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS `CONTENIDOS` (
  `ID_Contenido` CHAR(64) PRIMARY KEY COMMENT 'sha256(tipo|titulo_norm|fecha_clave)',
  `Tipo_Contenido` ENUM('NOTICIA','EVENTO','INICIATIVA','RECURSO','ALOJAMIENTO','PROMOCION') NOT NULL,
  `Estado` ENUM('ACTIVO','PASADO','RETIRADO') NOT NULL DEFAULT 'ACTIVO',
  `Titulo` VARCHAR(255) NOT NULL,
  `Resumen` VARCHAR(1200) NULL COMMENT 'Generado, 3 frases máx. Nunca el artículo entero',
  `Idioma_Origen` CHAR(2) NOT NULL DEFAULT 'es',
  `Fecha_Publicacion` DATE NOT NULL,
  `Fecha_Caducidad` DATE NULL COMMENT 'NOTICIA/INICIATIVA: publicación + TTL; RECURSO: al retirarse de la fuente',
  `Fecha_Inicio` DATE NULL COMMENT 'EVENTO',
  `Fecha_Fin` DATE NULL,
  `Hora_Inicio` TIME NULL,
  `Hora_Fin` TIME NULL,
  `Lugar_Nombre` VARCHAR(255) NULL,
  `Direccion` VARCHAR(255) NULL,
  `Es_Gratuito` TINYINT(1) NULL,
  `Precio_Euros` DECIMAL(10,2) NULL,
  `Requiere_Inscripcion` TINYINT(1) NULL,
  `URL_Inscripcion` VARCHAR(2048) NULL,
  `Entidad_Nombre` VARCHAR(255) NULL,
  `Entidad_Tipo` ENUM('PUBLICA','ASOCIACION','EMPRESA','MEDIO','PARTICULAR') NULL,
  `Ambito` ENUM('NACIONAL','CCAA','PROVINCIA','MUNICIPIO','MULTI') NOT NULL DEFAULT 'NACIONAL',
  `Tema_Principal` VARCHAR(40) NULL,
  `Relevancia` DECIMAL(3,2) NOT NULL DEFAULT 0.00 COMMENT '0..1 del clasificador',
  `Tags` JSON NULL COMMENT '5-10 tags genéricos en castellano',
  `Embedding` JSON NULL COMMENT 'text-embedding-3-small de título + resumen',
  `Embedding_Hash` CHAR(64) NULL COMMENT 'sha256 del texto embebido, para regenerar solo si cambia',
  `Imagen_Principal_URL` VARCHAR(2048) NULL,
  `Imagen_Origen` ENUM('FUENTE','IA','NINGUNA') NOT NULL DEFAULT 'NINGUNA',
  `Procedencia` JSON NULL COMMENT '{"campo": "extraido|inferido|generado|maestro|fuente"}',
  `Nota_Calidad` VARCHAR(500) NULL,
  `Fuente_Principal_ID` INT NULL,
  `Fuente_URL_Original` VARCHAR(2048) NULL,
  `Fecha_Creacion` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `Fecha_Actualizacion` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT `FK_CONT_TEMA` FOREIGN KEY (`Tema_Principal`) REFERENCES `CAT_TEMAS`(`Slug`) ON DELETE SET NULL,
  CONSTRAINT `FK_CONT_FUENTE` FOREIGN KEY (`Fuente_Principal_ID`) REFERENCES `FUENTES`(`ID_Fuente`) ON DELETE SET NULL,
  INDEX `IDX_CONT_TIPO_ESTADO` (`Tipo_Contenido`, `Estado`, `Fecha_Publicacion`),
  INDEX `IDX_CONT_CADUCIDAD` (`Estado`, `Fecha_Caducidad`),
  INDEX `IDX_CONT_EVENTO` (`Tipo_Contenido`, `Fecha_Inicio`),
  INDEX `IDX_CONT_AMBITO` (`Ambito`),
  INDEX `IDX_CONT_RELEVANCIA` (`Relevancia`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `CONTENIDO_GEO` (
  `ID_Contenido` CHAR(64) NOT NULL,
  `Nivel` ENUM('CCAA','PROVINCIA','MUNICIPIO') NOT NULL,
  `Codigo_INE` VARCHAR(5) NOT NULL,
  `Es_Principal` TINYINT(1) NOT NULL DEFAULT 0,
  `Nombre_Detectado` VARCHAR(120) NULL COMMENT 'Texto original del que se resolvió',
  PRIMARY KEY (`ID_Contenido`, `Nivel`, `Codigo_INE`),
  CONSTRAINT `FK_CGEO_CONT` FOREIGN KEY (`ID_Contenido`) REFERENCES `CONTENIDOS`(`ID_Contenido`) ON DELETE CASCADE,
  INDEX `IDX_CGEO_CODIGO` (`Nivel`, `Codigo_INE`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `CONTENIDO_ANIMALES` (
  `ID_Contenido` CHAR(64) NOT NULL,
  `Slug_Animal` VARCHAR(40) NOT NULL,
  `Es_Principal` TINYINT(1) NOT NULL DEFAULT 0,
  PRIMARY KEY (`ID_Contenido`, `Slug_Animal`),
  CONSTRAINT `FK_CANI_CONT` FOREIGN KEY (`ID_Contenido`) REFERENCES `CONTENIDOS`(`ID_Contenido`) ON DELETE CASCADE,
  CONSTRAINT `FK_CANI_ANIMAL` FOREIGN KEY (`Slug_Animal`) REFERENCES `CAT_ANIMALES`(`Slug`),
  INDEX `IDX_CANI_ANIMAL` (`Slug_Animal`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `CONTENIDO_TEMAS` (
  `ID_Contenido` CHAR(64) NOT NULL,
  `Slug_Tema` VARCHAR(40) NOT NULL,
  `Score` DECIMAL(3,2) NOT NULL DEFAULT 1.00,
  PRIMARY KEY (`ID_Contenido`, `Slug_Tema`),
  CONSTRAINT `FK_CTEM_CONT` FOREIGN KEY (`ID_Contenido`) REFERENCES `CONTENIDOS`(`ID_Contenido`) ON DELETE CASCADE,
  CONSTRAINT `FK_CTEM_TEMA` FOREIGN KEY (`Slug_Tema`) REFERENCES `CAT_TEMAS`(`Slug`),
  INDEX `IDX_CTEM_TEMA` (`Slug_Tema`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Multi-fuente sin borrado: la misma noticia en tres medios = 1 contenido, 3 filas
CREATE TABLE IF NOT EXISTS `CONTENIDO_FUENTES` (
  `ID_Contenido` CHAR(64) NOT NULL,
  `ID_Fuente` INT NOT NULL,
  `URL_Origen` VARCHAR(2048) NOT NULL,
  `URL_Hash` CHAR(64) NOT NULL COMMENT 'sha256(URL_Origen), lo calcula el persister',
  `Medio` VARCHAR(160) NULL COMMENT 'Medio real cuando la fuente es un feed de consulta',
  `Es_Principal` TINYINT(1) NOT NULL DEFAULT 0,
  `Aporto_Extraccion` TINYINT(1) NOT NULL DEFAULT 1,
  `Score_Calidad` DECIMAL(3,2) NULL,
  `Fecha_Publicacion` DATE NULL,
  `Fecha_Registro` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`ID_Contenido`, `URL_Hash`),
  CONSTRAINT `FK_CFUE_CONT` FOREIGN KEY (`ID_Contenido`) REFERENCES `CONTENIDOS`(`ID_Contenido`) ON DELETE CASCADE,
  CONSTRAINT `FK_CFUE_FUENTE` FOREIGN KEY (`ID_Fuente`) REFERENCES `FUENTES`(`ID_Fuente`) ON DELETE RESTRICT,
  INDEX `IDX_CFUE_FUENTE` (`ID_Fuente`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- IMÁGENES (espejo de NOTICIA_BINARIOS + IMAGENES_BLOB de KM0)
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS `CONTENIDO_BINARIOS` (
  `ID_Binario` INT AUTO_INCREMENT PRIMARY KEY,
  `ID_Contenido` CHAR(64) NOT NULL,
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
  KEY `IDX_CBIN_CONT` (`ID_Contenido`),
  CONSTRAINT `FK_CBIN_CONT` FOREIGN KEY (`ID_Contenido`) REFERENCES `CONTENIDOS`(`ID_Contenido`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `IMAGENES_BLOB` (
  `ID_Unico` CHAR(64) NOT NULL,
  `Nombre_Archivo` VARCHAR(255) NOT NULL,
  `Contenido` LONGBLOB NOT NULL,
  `Content_Type` VARCHAR(64) NULL,
  `Bytes` INT NOT NULL,
  `Actualizado` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`ID_Unico`, `Nombre_Archivo`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- EJECUCIONES, COSTES Y DESCARTES (INGESTA_RUNS/COSTES iguales que KM0 para
-- reutilizar CostTracker; la columna Poblacion guarda el nombre de la fuente)
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS `INGESTA_RUNS` (
  `ID_Run` INT AUTO_INCREMENT PRIMARY KEY,
  `Inicio` DATETIME NOT NULL,
  `Fin` DATETIME NOT NULL,
  `Target` VARCHAR(20) NOT NULL COMMENT 'local | railway | manual-ui',
  `Modelo` VARCHAR(50) NOT NULL,
  `Parametros` VARCHAR(255) NULL,
  `Llamadas` INT NOT NULL DEFAULT 0,
  `Tokens_In` BIGINT NOT NULL DEFAULT 0,
  `Tokens_Cached` BIGINT NOT NULL DEFAULT 0,
  `Tokens_Out` BIGINT NOT NULL DEFAULT 0,
  `Coste_USD` DECIMAL(10,4) NOT NULL DEFAULT 0,
  `Imagenes` INT NOT NULL DEFAULT 0,
  `Eventos_Persistidos` INT NOT NULL DEFAULT 0 COMMENT 'Contenidos tipo EVENTO',
  `Noticias_Persistidas` INT NOT NULL DEFAULT 0 COMMENT 'Resto de contenidos',
  `Targets_OK` INT NOT NULL DEFAULT 0,
  `Targets_Skip` INT NOT NULL DEFAULT 0,
  `Targets_Error` INT NOT NULL DEFAULT 0,
  INDEX `IDX_ARUN_INICIO` (`Inicio`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `INGESTA_COSTES` (
  `ID` INT AUTO_INCREMENT PRIMARY KEY,
  `ID_Run` INT NOT NULL,
  `Poblacion` VARCHAR(255) NOT NULL COMMENT 'Aquí: nombre de la fuente',
  `Operacion` VARCHAR(50) NOT NULL,
  `Llamadas` INT NOT NULL DEFAULT 0,
  `Tokens_In` BIGINT NOT NULL DEFAULT 0,
  `Tokens_Cached` BIGINT NOT NULL DEFAULT 0,
  `Tokens_Out` BIGINT NOT NULL DEFAULT 0,
  `Coste_USD` DECIMAL(10,4) NOT NULL DEFAULT 0,
  CONSTRAINT `FK_ACOSTE_RUN` FOREIGN KEY (`ID_Run`) REFERENCES `INGESTA_RUNS`(`ID_Run`) ON DELETE CASCADE,
  INDEX `IDX_ACOSTE_RUN` (`ID_Run`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Responde a "¿por qué no salió este contenido?" sin releer logs
CREATE TABLE IF NOT EXISTS `INGESTA_DESCARTES` (
  `ID` INT AUTO_INCREMENT PRIMARY KEY,
  `ID_Run` INT NOT NULL,
  `ID_Fuente` INT NULL,
  `Motivo` ENUM('NO_RELEVANTE','NO_RELEVANTE_GEO','SIN_FECHA','CADUCADO','EVENTO_PASADO',
                'DUPLICADO','ERROR_EXTRACCION','HTTP_ERROR','ROBOTS','SIN_CAMBIOS') NOT NULL,
  `Cantidad` INT NOT NULL DEFAULT 1,
  `Muestra_JSON` JSON NULL COMMENT 'Hasta 5 ejemplos: {titulo, url, medio, relevancia}',
  CONSTRAINT `FK_ADESC_RUN` FOREIGN KEY (`ID_Run`) REFERENCES `INGESTA_RUNS`(`ID_Run`) ON DELETE CASCADE,
  CONSTRAINT `FK_ADESC_FUENTE` FOREIGN KEY (`ID_Fuente`) REFERENCES `FUENTES`(`ID_Fuente`) ON DELETE SET NULL,
  UNIQUE INDEX `UQ_ADESC` (`ID_Run`, `ID_Fuente`, `Motivo`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- VISTA DE CONSULTA (lo que sirve la API en listados)
-- ----------------------------------------------------------------------------

CREATE OR REPLACE VIEW `V_CONTENIDOS_ACTIVOS` AS
SELECT
  c.*,
  t.Nombre AS Tema_Principal_Nombre,
  f.Nombre AS Fuente_Principal_Nombre,
  (SELECT COUNT(*) FROM CONTENIDO_FUENTES cf WHERE cf.ID_Contenido = c.ID_Contenido) AS Num_Fuentes,
  (SELECT GROUP_CONCAT(ca.Slug_Animal ORDER BY ca.Es_Principal DESC, ca.Slug_Animal SEPARATOR ',')
     FROM CONTENIDO_ANIMALES ca WHERE ca.ID_Contenido = c.ID_Contenido) AS Animales,
  (SELECT GROUP_CONCAT(ct.Slug_Tema ORDER BY ct.Score DESC SEPARATOR ',')
     FROM CONTENIDO_TEMAS ct WHERE ct.ID_Contenido = c.ID_Contenido) AS Temas
FROM CONTENIDOS c
LEFT JOIN CAT_TEMAS t ON t.Slug = c.Tema_Principal
LEFT JOIN FUENTES f ON f.ID_Fuente = c.Fuente_Principal_ID
WHERE c.Estado = 'ACTIVO';

SELECT 'animalista_db schema OK' AS Resultado;
