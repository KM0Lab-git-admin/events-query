-- ============================================================================
-- seed_geo.sql — El Viajero Animalista
-- ============================================================================
-- Maestro geográfico de nivel comunidad autónoma y provincia, con códigos INE.
-- Los municipios (~8.100) se cargan con scripts/animalista/load_geo_ine.py
-- desde el fichero oficial del INE (diccionarioAA.xlsx).
-- Idempotente: ON DUPLICATE KEY UPDATE.
-- ============================================================================

USE animalista_db;
SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

INSERT INTO GEO_CCAA (Codigo_INE, Nombre, Nombre_Norm) VALUES
  ('01', 'Andalucía',            'andalucia'),
  ('02', 'Aragón',               'aragon'),
  ('03', 'Principado de Asturias', 'asturias'),
  ('04', 'Illes Balears',        'illes balears'),
  ('05', 'Canarias',             'canarias'),
  ('06', 'Cantabria',            'cantabria'),
  ('07', 'Castilla y León',      'castilla y leon'),
  ('08', 'Castilla-La Mancha',   'castilla la mancha'),
  ('09', 'Cataluña',             'cataluna'),
  ('10', 'Comunitat Valenciana', 'comunitat valenciana'),
  ('11', 'Extremadura',          'extremadura'),
  ('12', 'Galicia',              'galicia'),
  ('13', 'Comunidad de Madrid',  'madrid'),
  ('14', 'Región de Murcia',     'murcia'),
  ('15', 'Comunidad Foral de Navarra', 'navarra'),
  ('16', 'País Vasco',           'pais vasco'),
  ('17', 'La Rioja',             'la rioja'),
  ('18', 'Ceuta',                'ceuta'),
  ('19', 'Melilla',              'melilla')
ON DUPLICATE KEY UPDATE Nombre = VALUES(Nombre), Nombre_Norm = VALUES(Nombre_Norm);

INSERT INTO GEO_PROVINCIAS (Codigo_INE, Nombre, Nombre_Norm, Codigo_CCAA) VALUES
  ('01', 'Araba/Álava',            'alava',                  '16'),
  ('02', 'Albacete',               'albacete',               '08'),
  ('03', 'Alicante/Alacant',       'alicante',               '10'),
  ('04', 'Almería',                'almeria',                '01'),
  ('05', 'Ávila',                  'avila',                  '07'),
  ('06', 'Badajoz',                'badajoz',                '11'),
  ('07', 'Illes Balears',          'illes balears',          '04'),
  ('08', 'Barcelona',              'barcelona',              '09'),
  ('09', 'Burgos',                 'burgos',                 '07'),
  ('10', 'Cáceres',                'caceres',                '11'),
  ('11', 'Cádiz',                  'cadiz',                  '01'),
  ('12', 'Castellón/Castelló',     'castellon',              '10'),
  ('13', 'Ciudad Real',            'ciudad real',            '08'),
  ('14', 'Córdoba',                'cordoba',                '01'),
  ('15', 'A Coruña',               'a coruna',               '12'),
  ('16', 'Cuenca',                 'cuenca',                 '08'),
  ('17', 'Girona',                 'girona',                 '09'),
  ('18', 'Granada',                'granada',                '01'),
  ('19', 'Guadalajara',            'guadalajara',            '08'),
  ('20', 'Gipuzkoa',               'gipuzkoa',               '16'),
  ('21', 'Huelva',                 'huelva',                 '01'),
  ('22', 'Huesca',                 'huesca',                 '02'),
  ('23', 'Jaén',                   'jaen',                   '01'),
  ('24', 'León',                   'leon',                   '07'),
  ('25', 'Lleida',                 'lleida',                 '09'),
  ('26', 'La Rioja',               'la rioja',               '17'),
  ('27', 'Lugo',                   'lugo',                   '12'),
  ('28', 'Madrid',                 'madrid',                 '13'),
  ('29', 'Málaga',                 'malaga',                 '01'),
  ('30', 'Murcia',                 'murcia',                 '14'),
  ('31', 'Navarra',                'navarra',                '15'),
  ('32', 'Ourense',                'ourense',                '12'),
  ('33', 'Asturias',               'asturias',               '03'),
  ('34', 'Palencia',               'palencia',               '07'),
  ('35', 'Las Palmas',             'las palmas',             '05'),
  ('36', 'Pontevedra',             'pontevedra',             '12'),
  ('37', 'Salamanca',              'salamanca',              '07'),
  ('38', 'Santa Cruz de Tenerife', 'santa cruz de tenerife', '05'),
  ('39', 'Cantabria',              'cantabria',              '06'),
  ('40', 'Segovia',                'segovia',                '07'),
  ('41', 'Sevilla',                'sevilla',                '01'),
  ('42', 'Soria',                  'soria',                  '07'),
  ('43', 'Tarragona',              'tarragona',              '09'),
  ('44', 'Teruel',                 'teruel',                 '02'),
  ('45', 'Toledo',                 'toledo',                 '08'),
  ('46', 'Valencia/València',      'valencia',               '10'),
  ('47', 'Valladolid',             'valladolid',             '07'),
  ('48', 'Bizkaia',                'bizkaia',                '16'),
  ('49', 'Zamora',                 'zamora',                 '07'),
  ('50', 'Zaragoza',               'zaragoza',               '02'),
  ('51', 'Ceuta',                  'ceuta',                  '18'),
  ('52', 'Melilla',                'melilla',                '19')
ON DUPLICATE KEY UPDATE Nombre = VALUES(Nombre), Nombre_Norm = VALUES(Nombre_Norm), Codigo_CCAA = VALUES(Codigo_CCAA);

-- Alias habituales para la resolución geográfica (nombres que aparecen en prensa)
INSERT INTO GEO_ALIAS (Alias_Norm, Nivel, Codigo_INE) VALUES
  ('alava', 'PROVINCIA', '01'), ('vitoria', 'PROVINCIA', '01'),
  ('alacant', 'PROVINCIA', '03'), ('castello', 'PROVINCIA', '12'), ('valencia', 'PROVINCIA', '46'),
  ('la coruna', 'PROVINCIA', '15'), ('coruna', 'PROVINCIA', '15'), ('orense', 'PROVINCIA', '32'),
  ('guipuzcoa', 'PROVINCIA', '20'), ('vizcaya', 'PROVINCIA', '48'),
  ('gerona', 'PROVINCIA', '17'), ('lerida', 'PROVINCIA', '25'),
  ('baleares', 'PROVINCIA', '07'), ('mallorca', 'PROVINCIA', '07'), ('menorca', 'PROVINCIA', '07'), ('ibiza', 'PROVINCIA', '07'),
  ('tenerife', 'PROVINCIA', '38'), ('gran canaria', 'PROVINCIA', '35'), ('lanzarote', 'PROVINCIA', '35'), ('fuerteventura', 'PROVINCIA', '35'),
  ('catalunya', 'CCAA', '09'), ('euskadi', 'CCAA', '16'), ('comunidad valenciana', 'CCAA', '10'), ('baleares', 'CCAA', '04'),
  ('comunidad de madrid', 'CCAA', '13'), ('region de murcia', 'CCAA', '14'), ('castilla-la mancha', 'CCAA', '08'), ('principado de asturias', 'CCAA', '03'), ('comunidad foral de navarra', 'CCAA', '15')
ON DUPLICATE KEY UPDATE Codigo_INE = VALUES(Codigo_INE);

SELECT COUNT(*) AS ccaa FROM GEO_CCAA;
SELECT COUNT(*) AS provincias FROM GEO_PROVINCIAS;
