-- ============================================================================
-- SCHEMA_INGESTION_DELTA.sql
-- ============================================================================
-- Delta incremental (KM0 / esquema 3.x sin tablas de ingesta).
-- Para base nueva: usar SQL/SCHEMA_SQL_FINAL.sql v4+ (unificado con ingesta).
--
-- Delta sobre KM0_Events.sql para soportar el módulo de ingesta.
--
-- Este fichero NO reemplaza KM0_Events.sql. Se aplica a continuación, asumiendo
-- que las tablas existentes (BIBLIOTECA_FUENTES, SCRAPING_TARGETS, EVENTOS_MASTER,
-- BINARIOS_STORAGE, AUDITORIA_SCRAPING, etc.) ya están creadas.
--
-- Contenido:
--   1. Tablas nuevas
--      - CAPTURAS_RAW
--      - EVENTO_FUENTES
--      - EVENTO_EMBEDDINGS
--      - PHASH_IMAGENES
--      - COVERAGE_METRICS
--   2. Modificaciones a tablas existentes
--      - SCRAPING_TARGETS: define enum Tipo_Target, añade campos de scheduling
--                          adaptativo
--      - AUDITORIA_SCRAPING: permite ID_Unico_Evento NULL (capturas que no
--                            producen evento), añade FK a CAPTURAS_RAW
--      - BIBLIOTECA_FUENTES: añade campos para configuración por tipo de fuente
--   3. Índices nuevos
--   4. Foreign keys nuevas
--
-- Cross-reference: ver INGESTION_DATA_MODEL.md para el detalle del modelo y
-- las decisiones de diseño que motivan estas tablas.
-- ============================================================================


-- ============================================================================
-- 1. TABLAS NUEVAS
-- ============================================================================

-- ----------------------------------------------------------------------------
-- CAPTURAS_RAW
-- ----------------------------------------------------------------------------
-- Almacena el payload crudo de cada captura externa (HTML completo, JSON de API,
-- lote de posts sociales) ANTES de cualquier procesamiento.
--
-- Una captura puede generar 0, 1 o N eventos:
--   - 0 si todos los candidatos extraídos se descartan (filtro temporal, gate, etc).
--   - 1 si la captura representa un solo evento (caso típico web).
--   - N si la captura agrupa varios (listado HTML, lote de posts, JSON de agregador).
--
-- La relación con EVENTOS_MASTER se establece vía EVENTO_FUENTES, no directamente.
-- Esto permite que la captura sea inmutable y "fuente de verdad" independiente.
-- ----------------------------------------------------------------------------

CREATE TABLE `CAPTURAS_RAW` (
  `ID_Captura`           BIGINT PRIMARY KEY AUTO_INCREMENT,
  `ID_Target`            INT NOT NULL                COMMENT 'FK a SCRAPING_TARGETS: qué trabajo produjo esta captura',
  `ID_Fuente`            INT NOT NULL                COMMENT 'FK a BIBLIOTECA_FUENTES: denormalizado para queries rápidos',
  `Fecha_Captura`        TIMESTAMP NOT NULL DEFAULT (CURRENT_TIMESTAMP),
  `Content_Type`         VARCHAR(64) NOT NULL        COMMENT 'application/json, text/html, image/jpeg, etc.',
  `Content_Hash_SHA256`  CHAR(64) NOT NULL           COMMENT 'Hash del payload bruto, para dedup contra capturas previas',
  `Payload_Bytes`        LONGBLOB                    COMMENT 'Payload crudo si encaja en BD. Si es > 1MB usar Payload_Storage_URL.',
  `Payload_Storage_URL`  VARCHAR(2048)               COMMENT 'URL en object storage (Cloudflare R2, S3) para payloads grandes',
  `Payload_Size_Bytes`   BIGINT NOT NULL,
  `Status`               ENUM('PENDIENTE_EXTRACCION','EXTRAIDA','ERROR_EXTRACCION','SKIPPED_SIN_CAMBIOS') NOT NULL DEFAULT 'PENDIENTE_EXTRACCION',
  `Extractor_Usado`      VARCHAR(64)                 COMMENT 'Identificador del extractor aplicado: structural_html, mapping_eventbrite, llm_text, llm_vision',
  `Extraccion_Started_At` DATETIME,
  `Extraccion_Ended_At`   DATETIME,
  `Coste_Estimado_USD`   DECIMAL(10,6) DEFAULT 0    COMMENT 'Coste de la captura+extracción (Apify + tokens LLM). 0 para rutas gratis.'
);


-- ----------------------------------------------------------------------------
-- EVENTO_FUENTES
-- ----------------------------------------------------------------------------
-- Relación N:M entre eventos y fuentes que los confirman.
--
-- Un evento puede tener varias fuentes (web del ajuntament + Festacat + IG del
-- organizador). Esto se usa para:
--   - Trazabilidad VAC 360
--   - Score de confianza (más fuentes independientes = más confianza)
--   - Permitir que el Gate pre-LLM registre confirmaciones sin re-extraer
--
-- EVENTOS_MASTER.Fuente_URL_Original mantiene la fuente principal (la primera o
-- la más confiable). Esta tabla guarda todas las demás, incluida la principal.
-- ----------------------------------------------------------------------------

CREATE TABLE `EVENTO_FUENTES` (
  `ID_Evento_Fuente`     BIGINT PRIMARY KEY AUTO_INCREMENT,
  `ID_Unico_Evento`      CHAR(64) NOT NULL,
  `ID_Fuente`            INT NOT NULL                COMMENT 'FK a BIBLIOTECA_FUENTES',
  `ID_Captura`           BIGINT                      COMMENT 'FK a CAPTURAS_RAW: la captura concreta. NULL si la fuente se registró sin captura asociada (caso legacy).',
  `URL_Origen`           VARCHAR(2048) NOT NULL      COMMENT 'URL específica del item dentro de la fuente (post, página de detalle)',
  `Fecha_Primera_Vez`    TIMESTAMP NOT NULL DEFAULT (CURRENT_TIMESTAMP),
  `Fecha_Ultima_Confirmacion` TIMESTAMP NOT NULL DEFAULT (CURRENT_TIMESTAMP) ON UPDATE CURRENT_TIMESTAMP,
  `Es_Fuente_Principal`  TINYINT(1) NOT NULL DEFAULT 0 COMMENT '1 si esta es la fuente cuya extracción se usó como base; las demás son confirmaciones',
  `Aporto_Extraccion`    TINYINT(1) NOT NULL DEFAULT 1 COMMENT '0 si el Gate pre-LLM la registró sin extraer (ahorro de coste)',
  `Score_Calidad`        DECIMAL(4,3)                COMMENT '0..1, calidad de los datos extraídos de esta fuente. Útil en merge.'
);


-- ----------------------------------------------------------------------------
-- EVENTO_EMBEDDINGS
-- ----------------------------------------------------------------------------
-- Embeddings separados de EVENTOS_MASTER por dos razones:
--   1. Performance: un JSON de 1536 floats por fila vuelve los SELECT lentos
--      incluso cuando no se necesita el embedding.
--   2. Versionado: permite tener varias versiones de embedding por evento
--      (al cambiar de modelo) sin migrar EVENTOS_MASTER.
--
-- En queries normales, se hace LEFT JOIN solo cuando se necesitan los vectores.
-- ----------------------------------------------------------------------------

CREATE TABLE `EVENTO_EMBEDDINGS` (
  `ID_Embedding`         BIGINT PRIMARY KEY AUTO_INCREMENT,
  `ID_Unico_Evento`      CHAR(64) NOT NULL,
  `Idioma`               CHAR(2) NOT NULL            COMMENT 'es o ca',
  `Modelo`               VARCHAR(64) NOT NULL        COMMENT 'p.ej. text-embedding-3-small. Permite múltiples versiones.',
  `Dimensiones`          INT NOT NULL                COMMENT 'p.ej. 1536',
  `Vector_JSON`          JSON NOT NULL               COMMENT 'Array de floats. Usar JSON_EXTRACT en MySQL 8 o columna VECTOR si está disponible.',
  `Fecha_Generacion`     TIMESTAMP NOT NULL DEFAULT (CURRENT_TIMESTAMP),
  `Texto_Fuente_Hash`    CHAR(64) NOT NULL           COMMENT 'Hash del texto que se embebió (tags + título). Permite saber si regenerar.'
);


-- ----------------------------------------------------------------------------
-- PHASH_IMAGENES
-- ----------------------------------------------------------------------------
-- Caché perceptual de imágenes para evitar re-extraer carteles idénticos.
--
-- Cuando un cartel (ej. de la Generalitat) aparece en cuentas sociales de varios
-- municipios, se evita pagar LLM-Vision varias veces:
--   1. Al capturar la imagen se calcula pHash.
--   2. Si pHash ya existe → reutilizar extracción previa, asociar al nuevo evento/fuente.
--   3. Si pHash no existe → extraer con LLM-Vision y guardar resultado.
--
-- pHash típicamente 16 bytes (hex 32 chars), tolerante a recompresión y resize.
-- ----------------------------------------------------------------------------

CREATE TABLE `PHASH_IMAGENES` (
  `ID_Phash`             BIGINT PRIMARY KEY AUTO_INCREMENT,
  `Phash_Hex`            CHAR(32) UNIQUE NOT NULL    COMMENT 'pHash perceptual en hexadecimal',
  `ID_Binario`           INT                         COMMENT 'FK a BINARIOS_STORAGE: ejemplar de la imagen guardado',
  `Extraccion_JSON`      JSON                        COMMENT 'Resultado cacheado del LLM-Vision sobre esta imagen',
  `Veces_Reutilizado`    INT NOT NULL DEFAULT 0      COMMENT 'Métrica para saber qué carteles son virales',
  `Fecha_Primera_Vez`    TIMESTAMP NOT NULL DEFAULT (CURRENT_TIMESTAMP),
  `Fecha_Ultimo_Hit`     TIMESTAMP NOT NULL DEFAULT (CURRENT_TIMESTAMP) ON UPDATE CURRENT_TIMESTAMP
);


-- ----------------------------------------------------------------------------
-- COVERAGE_METRICS
-- ----------------------------------------------------------------------------
-- Tabla materializada con métricas por (ciudad, tipo de fuente) usada para
-- scheduling adaptativo: decidir cuánta frecuencia de Apify dedicar a un
-- municipio según cuánta cobertura ya aportan las rutas gratis.
--
-- Se refresca con un job batch (típicamente diario). Ver INGESTION_OPTIMIZATION.md.
-- ----------------------------------------------------------------------------

CREATE TABLE `COVERAGE_METRICS` (
  `ID_Ciudad`                  INT NOT NULL,
  `Tipo_Fuente`                ENUM('FUENTE_OFICIAL','AGREGADOR','RED_SOCIAL_PERFIL','RED_SOCIAL_QUERY') NOT NULL,
  `Eventos_Aportados_30d`      INT NOT NULL DEFAULT 0 COMMENT 'Eventos únicos en los últimos 30 días con esta fuente como principal',
  `Eventos_Confirmados_30d`    INT NOT NULL DEFAULT 0 COMMENT 'Eventos en los últimos 30 días donde esta fuente confirma pero no es principal',
  `Capturas_Sin_Evento_30d`    INT NOT NULL DEFAULT 0 COMMENT 'Capturas que no produjeron evento útil (gate, filtro temporal, etc)',
  `Score_Eficiencia`           DECIMAL(5,4) NOT NULL DEFAULT 1.0 COMMENT 'Aportados / (Aportados + Capturas_Sin_Evento). 0..1.',
  `Frecuencia_Sugerida_Horas`  INT NOT NULL DEFAULT 24 COMMENT 'Frecuencia recalculada por el scheduling adaptativo',
  `Fecha_Calculo`              TIMESTAMP NOT NULL DEFAULT (CURRENT_TIMESTAMP) ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`ID_Ciudad`, `Tipo_Fuente`)
);


-- ============================================================================
-- 2. MODIFICACIONES A TABLAS EXISTENTES
-- ============================================================================

-- ----------------------------------------------------------------------------
-- SCRAPING_TARGETS
-- ----------------------------------------------------------------------------
-- El SQL original deja SCRAPING_TARGETS_Tipo_Target_enum como placeholder.
-- Aquí se concreta y se añaden campos de scheduling adaptativo.
-- ----------------------------------------------------------------------------

ALTER TABLE `SCRAPING_TARGETS`
  MODIFY COLUMN `Tipo_Target` ENUM(
    'WEB_LISTADO',          -- Página índice/agenda HTML del que se extraen links de detalle
    'WEB_DETALLE',          -- Página de detalle de un evento individual
    'WEB_SITEMAP',          -- sitemap.xml para descubrimiento
    'API_AGREGADOR',        -- Endpoint de API de agregador (Eventbrite, Festacat, etc.)
    'SOCIAL_PERFIL',        -- Cuenta de red social a scrapear vía Apify
    'SOCIAL_QUERY'          -- Búsqueda/hashtag en red social vía Apify
  ) NOT NULL;

ALTER TABLE `SCRAPING_TARGETS`
  ADD COLUMN `Frecuencia_Base_Horas` INT NOT NULL DEFAULT 24
    COMMENT 'Frecuencia configurada manualmente. Frecuencia_Horas es la efectiva tras scheduling adaptativo.' AFTER `Frecuencia_Horas`,
  ADD COLUMN `Coverage_Score` DECIMAL(5,4) DEFAULT NULL
    COMMENT 'Snapshot del score de COVERAGE_METRICS aplicado al calcular Next_Run_At. NULL hasta primer ciclo.' AFTER `Frecuencia_Base_Horas`,
  ADD COLUMN `Capturas_Utiles_Consecutivas` INT NOT NULL DEFAULT 0
    COMMENT 'Para backoff: cuenta capturas que aportaron al menos un evento. Se resetea al fallar.',
  ADD COLUMN `Capturas_Vacias_Consecutivas` INT NOT NULL DEFAULT 0
    COMMENT 'Para backoff: cuenta capturas sin evento útil. Aumenta frecuencia cuando supera umbral.';


-- ----------------------------------------------------------------------------
-- AUDITORIA_SCRAPING
-- ----------------------------------------------------------------------------
-- Permitir que la auditoría exista sin evento asociado (captura skipped por
-- gate, fallo de extracción, etc) y añadir FK a CAPTURAS_RAW.
-- ----------------------------------------------------------------------------

ALTER TABLE `AUDITORIA_SCRAPING`
  MODIFY COLUMN `ID_Unico_Evento` CHAR(64) NULL COMMENT 'NULL si la captura no produjo evento (skipped por gate, filtro temporal, etc)';

ALTER TABLE `AUDITORIA_SCRAPING`
  ADD COLUMN `ID_Captura` BIGINT NULL COMMENT 'FK a CAPTURAS_RAW' AFTER `ID_Unico_Evento`,
  ADD COLUMN `Motivo_Skip` ENUM(
    'GATE_DUPLICADO',       -- El Gate pre-LLM identificó match con evento conocido
    'FILTRO_TEMPORAL',      -- Evento con fecha pasada
    'SIN_FECHA_DETECTADA',  -- Extracción no pudo determinar fecha del evento
    'CONTENIDO_NO_EVENTO',  -- Captura no contenía info de evento (post promocional, etc)
    'ERROR_EXTRACCION',     -- Fallo del extractor
    'NA'                    -- No aplica: la captura sí produjo evento
  ) NOT NULL DEFAULT 'NA';


-- ----------------------------------------------------------------------------
-- BIBLIOTECA_FUENTES
-- ----------------------------------------------------------------------------
-- Campos adicionales para configurar comportamiento por fuente.
-- ----------------------------------------------------------------------------

ALTER TABLE `BIBLIOTECA_FUENTES`
  ADD COLUMN `Config_JSON` JSON DEFAULT NULL
    COMMENT 'Configuración específica del conector. P.ej. selectores CSS para FUENTE_OFICIAL, actor de Apify para RED_SOCIAL, schema mapping para AGREGADOR.',
  ADD COLUMN `Notas` TEXT DEFAULT NULL
    COMMENT 'Notas operativas: razones de inclusión, contactos, particularidades de mantenimiento.',
  ADD COLUMN `Fecha_Alta` TIMESTAMP NOT NULL DEFAULT (CURRENT_TIMESTAMP),
  ADD COLUMN `Fecha_Modificacion` TIMESTAMP NOT NULL DEFAULT (CURRENT_TIMESTAMP) ON UPDATE CURRENT_TIMESTAMP;


-- ============================================================================
-- 3. ÍNDICES NUEVOS
-- ============================================================================

-- CAPTURAS_RAW
CREATE INDEX `IDX_CAPTURA_TARGET`           ON `CAPTURAS_RAW` (`ID_Target`);
CREATE INDEX `IDX_CAPTURA_FUENTE`           ON `CAPTURAS_RAW` (`ID_Fuente`);
CREATE INDEX `IDX_CAPTURA_STATUS_FECHA`     ON `CAPTURAS_RAW` (`Status`, `Fecha_Captura`);
CREATE INDEX `IDX_CAPTURA_CONTENT_HASH`     ON `CAPTURAS_RAW` (`Content_Hash_SHA256`);

-- EVENTO_FUENTES
CREATE UNIQUE INDEX `UQ_EVENTO_FUENTE_URL`  ON `EVENTO_FUENTES` (`ID_Unico_Evento`, `URL_Origen`(255));
CREATE INDEX `IDX_EF_EVENTO`                ON `EVENTO_FUENTES` (`ID_Unico_Evento`);
CREATE INDEX `IDX_EF_FUENTE`                ON `EVENTO_FUENTES` (`ID_Fuente`);
CREATE INDEX `IDX_EF_CAPTURA`               ON `EVENTO_FUENTES` (`ID_Captura`);

-- EVENTO_EMBEDDINGS
CREATE UNIQUE INDEX `UQ_EMB_EVENTO_IDIOMA_MODELO` ON `EVENTO_EMBEDDINGS` (`ID_Unico_Evento`, `Idioma`, `Modelo`);
CREATE INDEX `IDX_EMB_EVENTO`               ON `EVENTO_EMBEDDINGS` (`ID_Unico_Evento`);

-- PHASH_IMAGENES
CREATE INDEX `IDX_PHASH_BINARIO`            ON `PHASH_IMAGENES` (`ID_Binario`);

-- COVERAGE_METRICS
CREATE INDEX `IDX_COV_TIPO`                 ON `COVERAGE_METRICS` (`Tipo_Fuente`);

-- SCRAPING_TARGETS adicionales
CREATE INDEX `IDX_TARGET_COVERAGE`          ON `SCRAPING_TARGETS` (`Coverage_Score`);


-- ============================================================================
-- 4. FOREIGN KEYS NUEVAS
-- ============================================================================

ALTER TABLE `CAPTURAS_RAW`
  ADD CONSTRAINT `FK_CAPTURA_TARGET` FOREIGN KEY (`ID_Target`) REFERENCES `SCRAPING_TARGETS` (`ID_Target`),
  ADD CONSTRAINT `FK_CAPTURA_FUENTE` FOREIGN KEY (`ID_Fuente`) REFERENCES `BIBLIOTECA_FUENTES` (`ID_Fuente`);

ALTER TABLE `EVENTO_FUENTES`
  ADD CONSTRAINT `FK_EF_EVENTO`  FOREIGN KEY (`ID_Unico_Evento`) REFERENCES `EVENTOS_MASTER` (`ID_Unico_Evento`) ON DELETE CASCADE,
  ADD CONSTRAINT `FK_EF_FUENTE`  FOREIGN KEY (`ID_Fuente`)       REFERENCES `BIBLIOTECA_FUENTES` (`ID_Fuente`),
  ADD CONSTRAINT `FK_EF_CAPTURA` FOREIGN KEY (`ID_Captura`)      REFERENCES `CAPTURAS_RAW` (`ID_Captura`) ON DELETE SET NULL;

ALTER TABLE `EVENTO_EMBEDDINGS`
  ADD CONSTRAINT `FK_EMB_EVENTO` FOREIGN KEY (`ID_Unico_Evento`) REFERENCES `EVENTOS_MASTER` (`ID_Unico_Evento`) ON DELETE CASCADE;

ALTER TABLE `PHASH_IMAGENES`
  ADD CONSTRAINT `FK_PHASH_BINARIO` FOREIGN KEY (`ID_Binario`) REFERENCES `BINARIOS_STORAGE` (`ID_Binario`) ON DELETE SET NULL;

ALTER TABLE `COVERAGE_METRICS`
  ADD CONSTRAINT `FK_COV_CIUDAD` FOREIGN KEY (`ID_Ciudad`) REFERENCES `CIUDADES` (`ID_Ciudad`);

ALTER TABLE `AUDITORIA_SCRAPING`
  ADD CONSTRAINT `FK_AUDIT_CAPTURA` FOREIGN KEY (`ID_Captura`) REFERENCES `CAPTURAS_RAW` (`ID_Captura`) ON DELETE SET NULL;


-- ============================================================================
-- FIN
-- ============================================================================
