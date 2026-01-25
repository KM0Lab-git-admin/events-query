-- ============================================================================
-- ESQUEMA DE BASE DE DATOS FINAL - Events Query API
-- ============================================================================
-- Versión: 3.0 FINAL
-- Fecha: Enero 2026
-- 
-- DECISIÓN CLAVE: Tags y Embeddings Separados por Idioma
-- - Tags_ES + Tags_Embedding_ES (español)
-- - Tags_CAT + Tags_Embedding_CAT (catalán)
-- 
-- Ventajas:
-- ✅ Performance optimizada (solo consulta un idioma)
-- ✅ Mayor precisión en búsqueda semántica
-- ✅ Escalable a más idiomas
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

-- Insertar categorías predefinidas
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
-- EVENTOS_MASTER: Tabla principal con TAGS SEPARADOS POR IDIOMA
-- ============================================================================
CREATE TABLE IF NOT EXISTS `EVENTOS_MASTER` (
  -- Identificación
  `ID_Unico_Evento` CHAR(64) PRIMARY KEY COMMENT 'Hash SHA-256 único',
  `Metodo_Ingesta` ENUM('SCRAPING','MANUAL') NOT NULL,
  `ID_Usuario_Carga` VARCHAR(255) NOT NULL,
  `Fuente_ID` ENUM('URL_ESTRUCTURAL','SOCIAL_VISUAL','SOCIAL_SEMANTICA') NOT NULL,
  `Fuente_URL_Original` VARCHAR(2048) NULL,
  `Estado` ENUM('ACTIVO','CANCELADO','APLAZADO') NOT NULL DEFAULT 'ACTIVO',
  `Fecha_Creacion` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  
  -- Localización
  `ID_Ciudad` INT NULL,
  `CP_Evento` VARCHAR(5) NOT NULL COMMENT 'Campo principal de filtrado geográfico',
  `Poblacion_Nombre` VARCHAR(255) NOT NULL,
  `Lugar_Nombre` VARCHAR(255) NOT NULL,
  `Direccion_Fisica` VARCHAR(255) NULL,
  `Coordenadas_JSON` JSON NULL COMMENT '{"lat": float, "lng": float}',
  
  -- Organizador
  `ID_Familia` VARCHAR(255) NULL,
  `Tipo_Organizador` ENUM('PUBLICO','PRIVADO','ASOCIACION') NULL,
  `Organizador_Nombre` VARCHAR(255) NULL,
  `Organizador_Web` VARCHAR(2048) NULL,
  `Es_Patrocinado` TINYINT(1) NOT NULL DEFAULT 0,
  
  -- Contenido bilingüe
  `Idioma_Origen` CHAR(2) NOT NULL COMMENT 'ca o es',
  `Titulo_CAT` VARCHAR(255) NOT NULL,
  `Titulo_ES` VARCHAR(255) NOT NULL,
  `Desc_Larga_CAT` TEXT NULL,
  `Desc_Larga_ES` TEXT NULL,
  
  -- ⭐ TAGS SEPARADOS POR IDIOMA (DECISIÓN FINAL) ⭐
  `Tags_ES` JSON NULL COMMENT 'Array tags español: ["#infantil", "#niños", "#aire_libre"]',
  `Tags_CAT` JSON NULL COMMENT 'Array tags catalán: ["#infantil", "#nens", "#a_l_aire_lliure"]',
  
  -- ⭐ EMBEDDINGS SEPARADOS POR IDIOMA (DECISIÓN FINAL) ⭐
  `Tags_Embedding_ES` JSON NULL COMMENT 'Vector embedding de Tags_ES (1536 dimensiones)',
  `Tags_Embedding_CAT` JSON NULL COMMENT 'Vector embedding de Tags_CAT (1536 dimensiones)',
  
  -- Economía
  `Es_Gratuito` TINYINT(1) NOT NULL,
  `Precio_Euros` DECIMAL(10,2) NULL,
  `Requiere_Inscripcion` TINYINT(1) NOT NULL,
  `Aforo_Maximo` INT NULL,
  `Plazas_Disponibles` INT NULL,
  `Link_Entradas_Inscripcion` VARCHAR(2048) NULL,
  
  -- Multimedia
  `Imagen_Principal_URL` VARCHAR(2048) NULL,
  
  -- Índices
  KEY `IDX_EVENTO_CP_ESTADO` (`CP_Evento`, `Estado`),
  KEY `IDX_EVENTO_CIUDAD` (`ID_Ciudad`),
  KEY `IDX_EVENTO_GRATUITO` (`Es_Gratuito`),
  
  -- Claves foráneas
  CONSTRAINT `FK_EVENTO_CP` FOREIGN KEY (`CP_Evento`) 
    REFERENCES `CODIGOS_POSTALES`(`CP`) ON DELETE RESTRICT,
  CONSTRAINT `FK_EVENTO_CIUDAD` FOREIGN KEY (`ID_Ciudad`) 
    REFERENCES `CIUDADES`(`ID_Ciudad`) ON DELETE RESTRICT,
  CONSTRAINT `FK_EVENTO_FAMILIA` FOREIGN KEY (`ID_Familia`) 
    REFERENCES `FUENTES_FAMILIA`(`ID_Familia`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Tabla principal con tags y embeddings separados por idioma';

-- ============================================================================
-- EVENTO_CATEGORIAS: Relación N:M entre eventos y categorías
-- ============================================================================
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

-- ============================================================================
-- EVENTO_HORARIOS: Fechas y horarios
-- ============================================================================
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

-- ============================================================================
-- BINARIOS_STORAGE: Multimedia
-- ============================================================================
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
-- AUDITORIA_SCRAPING: Trazabilidad
-- ============================================================================
CREATE TABLE IF NOT EXISTS `AUDITORIA_SCRAPING` (
  `ID_Auditoria` INT AUTO_INCREMENT PRIMARY KEY,
  `ID_Unico_Evento` CHAR(64) NULL,
  `URL_Procesada` VARCHAR(2048) NULL,
  `Metodo_Usado` VARCHAR(255) NULL,
  `Resultado` ENUM('OK','WARNING','ERROR') NOT NULL DEFAULT 'OK',
  `Detalle` TEXT NULL,
  `Texto_Bruto_Caption` TEXT NULL,
  `Texto_Bruto_OCR` TEXT NULL,
  `Payload_Extra` JSON NULL,
  `Fecha_Ejecucion` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY `IDX_AUDIT_EVENTO` (`ID_Unico_Evento`),
  KEY `IDX_AUDIT_RESULTADO` (`Resultado`),
  KEY `IDX_AUDIT_FECHA` (`Fecha_Ejecucion`),
  CONSTRAINT `FK_AUDIT_EVENTO` FOREIGN KEY (`ID_Unico_Evento`) 
    REFERENCES `EVENTOS_MASTER`(`ID_Unico_Evento`) ON DELETE SET NULL
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
-- NOTAS FINALES
-- ============================================================================

/*
FLUJO DE INGESTA (IA externa, NO parte de este proyecto):
1. IA lee evento de web/red social
2. Genera Tags_ES: ["#infantil", "#niños", "#aire_libre"]
3. Genera Tags_CAT: ["#infantil", "#nens", "#a_l_aire_lliure"]
4. Genera Tags_Embedding_ES (vector de Tags_ES)
5. Genera Tags_Embedding_CAT (vector de Tags_CAT)
6. Relaciona con categorías predefinidas
7. Inserta en BD

FLUJO DE BÚSQUEDA (este proyecto):
1. Usuario pregunta en lenguaje natural
2. IA detecta idioma ("es" o "ca")
3. Pre-filtrado SQL (CP, fecha, categoría) → reduce a ~15 eventos
4. Generar embedding de conceptos del usuario
5. SI idioma="es": comparar con Tags_Embedding_ES
   SI idioma="ca": comparar con Tags_Embedding_CAT
6. Filtrar por similitud > 0.6
7. Ordenar por similitud DESC
8. Devolver resultados

PERFORMANCE ESPERADA:
- Pre-filtrado SQL: ~150ms
- Generar embedding: ~100ms
- Calcular similitud (15 eventos): ~30ms
- Total búsqueda: ~280ms
- TOTAL COMPLETO: ~1.5 segundos ✅ < 3 segundos

EJEMPLO DE DATOS:
{
  "Tags_ES": ["#infantil", "#niños", "#aire_libre", "#parque"],
  "Tags_CAT": ["#infantil", "#nens", "#a_l_aire_lliure", "#parc"],
  "Tags_Embedding_ES": [0.123, -0.456, 0.789, ...],  // 1536 números
  "Tags_Embedding_CAT": [0.125, -0.450, 0.792, ...]   // 1536 números
}
*/

-- FIN DEL ESQUEMA
