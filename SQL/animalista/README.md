# animalista_db — esquema y semillas

Base de datos separada de `events_db`. Diseño: `docs/VIAJERO-ANIMALISTA-DISENO.md`.

## Aplicar en local (MySQL de docker-compose)

Orden obligatorio. Todos los ficheros son idempotentes.

```powershell
Get-Content .\SQL\animalista\schema.sql -Raw         | docker exec -i events-mysql mysql -u root -prootpassword
Get-Content .\SQL\animalista\grant_local.sql -Raw    | docker exec -i events-mysql mysql -u root -prootpassword
Get-Content .\SQL\animalista\seed_geo.sql -Raw       | docker exec -i events-mysql mysql -u root -prootpassword
Get-Content .\SQL\animalista\seed_taxonomia.sql -Raw | docker exec -i events-mysql mysql -u root -prootpassword
python scripts\animalista\load_geo_ine.py             # municipios desde el INE (~8.100)
```

En un volumen nuevo, `docker compose up` aplica `schema.sql` automáticamente
(montado en `docker-entrypoint-initdb.d`); las semillas y los municipios se
cargan a mano con los comandos de arriba.

## Verificar

```sql
USE animalista_db;
SELECT COUNT(*) FROM GEO_CCAA;        -- 19
SELECT COUNT(*) FROM GEO_PROVINCIAS;  -- 52
SELECT COUNT(*) FROM GEO_MUNICIPIOS;  -- ~8.130
SELECT COUNT(*) FROM CAT_TEMAS;       -- 9
SELECT COUNT(*) FROM CAT_ANIMALES;    -- 9
```

## Variables de entorno

Los scripts usan `ANIMALISTA_DB_*` si existen y, si no, `DB_*` del `.env`
con la base de datos `animalista_db`. En Railway, `animalista_db` será un
segundo servicio MySQL con sus propias variables.
