-- ============================================================================
-- seed_taxonomia.sql — El Viajero Animalista
-- ============================================================================
-- Catálogos cerrados de temas y animales (docs/VIAJERO-ANIMALISTA-DISENO.md §3.3).
-- Los tipos de contenido y los ámbitos son ENUM en CONTENIDOS, no tablas.
-- Idempotente: ON DUPLICATE KEY UPDATE sobre la PK Slug.
-- ============================================================================

USE animalista_db;
SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

INSERT INTO CAT_TEMAS (Slug, Nombre, Descripcion, Orden, Activo) VALUES
  ('adopcion-proteccion',   'Adopción y protección',   'Adopciones, acogidas, abandono, rescates, maltrato, protectoras', 10, 1),
  ('bienestar-salud',       'Bienestar y salud',       'Veterinaria, nutrición, comportamiento, cuidados', 20, 1),
  ('legislacion',           'Legislación y normativa', 'Leyes, ordenanzas, multas, sanciones, trámites, sentencias', 30, 1),
  ('turismo-viajes',        'Turismo y viajes',        'Viajar con animales, destinos, transporte, alojamientos', 40, 1),
  ('espacios-convivencia',  'Espacios y convivencia',  'Playas, parques, zonas caninas, acceso a locales y edificios, transporte urbano, vecindad', 50, 1),
  ('ocio-deporte',          'Ocio y deporte',          'Agility, canicross, paseos, exposiciones, concursos, ferias', 60, 1),
  ('educacion-divulgacion', 'Educación y divulgación', 'Charlas, talleres, campañas de sensibilización', 70, 1),
  ('fauna-conservacion',    'Fauna y conservación',    'Fauna silvestre, especies protegidas, centros de recuperación', 80, 1),
  ('sociedad-tendencias',   'Sociedad y tendencias',   'Datos, estudios, consumo, vivienda, trabajo, curiosidades', 90, 1)
ON DUPLICATE KEY UPDATE
  Nombre = VALUES(Nombre), Descripcion = VALUES(Descripcion), Orden = VALUES(Orden), Activo = VALUES(Activo);

INSERT INTO CAT_ANIMALES (Slug, Nombre, Grupo, Orden, Activo) VALUES
  ('perros',             'Perros',                        'prioritario',      10, 1),
  ('gatos',              'Gatos',                         'prioritario',      20, 1),
  ('pequenos-mamiferos', 'Conejos y pequeños mamíferos',  'otros domésticos', 30, 1),
  ('aves',               'Aves',                          'otros domésticos', 40, 1),
  ('exoticos',           'Exóticos y reptiles',           'otros domésticos', 50, 1),
  ('caballos',           'Caballos y équidos',            'otros',            60, 1),
  ('granja',             'Animales de granja',            'otros',            70, 1),
  ('fauna-silvestre',    'Fauna silvestre',               'otros',            80, 1),
  ('general',            'Animales en general',           'transversal',      90, 1)
ON DUPLICATE KEY UPDATE
  Nombre = VALUES(Nombre), Grupo = VALUES(Grupo), Orden = VALUES(Orden), Activo = VALUES(Activo);

SELECT COUNT(*) AS temas FROM CAT_TEMAS;
SELECT COUNT(*) AS animales FROM CAT_ANIMALES;
