"""Descarga los últimos N eventos publicados de Railway a la BD local.

Flujo Railway -> local (NUNCA escribe en Railway). Pensado para probar en
local con datos reales de UAT.

Qué copia, por cada evento descargado:
  - EVENTOS_MASTER (remapeando ID_Ciudad / ID_Recinto a los IDs locales)
  - EVENTO_HORARIOS, EVENTO_CATEGORIAS, EVENTO_FUENTES, BINARIOS_STORAGE
  - Maestras referenciadas (CIUDADES, CODIGOS_POSTALES, CATEGORIAS, RECINTOS,
    BIBLIOTECA_FUENTES) con upsert por clave natural y remapeo de IDs
  - IMAGENES_BLOB + ficheros en static/images/ (salvo --sin-imagenes)

La sustitución es por ID de evento: si el evento ya existía en local, se
borran sus filas (hijas primero) y se reinsertan con el contenido de Railway.
No toca ningún otro evento local.

Uso:
    python scripts/pull_events_from_railway.py --dry-run        # solo lee y resume
    python scripts/pull_events_from_railway.py --yes            # 100 últimos
    python scripts/pull_events_from_railway.py --limit 50 --poblacion "Malgrat de Mar" --yes
    python scripts/pull_events_from_railway.py --estado TODOS --sin-imagenes --yes

Requiere en .env: DB_* (local, destino) y RAILWAY_DB_* (origen, solo lectura).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Permite ejecutar: python scripts/pull_events_from_railway.py ...
sys.path.insert(0, str(Path(__file__).resolve().parent))

import ingest_all as ia

IMAGES_DIR = Path("static") / "images"

# DDL idéntico al de ingest_all._upsert_imagen_blob (por si la BD local aún
# no tiene la tabla).
IMAGENES_BLOB_DDL = """
    CREATE TABLE IF NOT EXISTS `IMAGENES_BLOB` (
      `ID_Unico` CHAR(64) NOT NULL,
      `Nombre_Archivo` VARCHAR(255) NOT NULL,
      `Contenido` LONGBLOB NOT NULL,
      `Content_Type` VARCHAR(64) NULL,
      `Bytes` INT NOT NULL,
      `Actualizado` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
      PRIMARY KEY (`ID_Unico`, `Nombre_Archivo`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

HOSTS_LOCALES = {"localhost", "127.0.0.1", "mysql"}


# ---------------------------------------------------------------------------
# Helpers de lectura
# ---------------------------------------------------------------------------

def fetch_all(cur, sql: str, params=()) -> list[dict]:
    cur.execute(sql, params)
    return cur.fetchall()


def fetch_map(cur, sql: str, params=()) -> dict:
    """SELECT ... -> {primera_columna: fila}."""
    rows = fetch_all(cur, sql, params)
    if not rows:
        return {}
    key = next(iter(rows[0].keys()))
    return {r[key]: r for r in rows}


# ---------------------------------------------------------------------------
# Upsert de maestras con remapeo de IDs (railway_id -> local_id)
# ---------------------------------------------------------------------------

def remap_ciudades(src, dst, ids: set[int]) -> dict[int, int]:
    if not ids:
        return {}
    marks = ",".join(["%s"] * len(ids))
    rows = fetch_all(src, f"SELECT * FROM CIUDADES WHERE ID_Ciudad IN ({marks})",
                     tuple(ids))
    mapping: dict[int, int] = {}
    for r in rows:
        local = fetch_all(dst, "SELECT ID_Ciudad FROM CIUDADES WHERE Nombre=%s",
                          (r["Nombre"],))
        if local:
            mapping[r["ID_Ciudad"]] = local[0]["ID_Ciudad"]
            continue
        cols = [c for c in r.keys() if c != "ID_Ciudad"]
        sql = (f"INSERT INTO CIUDADES ({', '.join(cols)}) "
               f"VALUES ({', '.join(['%s'] * len(cols))})")
        dst.execute(sql, tuple(r[c] for c in cols))
        mapping[r["ID_Ciudad"]] = dst.lastrowid
    return mapping


def upsert_codigos_postales(src, dst, cps: set[str], map_ciud: dict[int, int]) -> None:
    if not cps:
        return
    marks = ",".join(["%s"] * len(cps))
    rows = fetch_all(src, f"SELECT * FROM CODIGOS_POSTALES WHERE CP IN ({marks})",
                     tuple(cps))
    for r in rows:
        id_ciudad = map_ciud.get(r["ID_Ciudad"], r["ID_Ciudad"])
        dst.execute(
            """INSERT INTO CODIGOS_POSTALES (CP, ID_Ciudad, Latitud, Longitud, Barrio_Distrito)
               VALUES (%s,%s,%s,%s,%s)
               ON DUPLICATE KEY UPDATE ID_Ciudad=VALUES(ID_Ciudad),
                 Latitud=VALUES(Latitud), Longitud=VALUES(Longitud),
                 Barrio_Distrito=VALUES(Barrio_Distrito)""",
            (r["CP"], id_ciudad, r["Latitud"], r["Longitud"], r.get("Barrio_Distrito")),
        )


def remap_categorias(src, dst, ids: set[int]) -> dict[int, int]:
    if not ids:
        return {}
    marks = ",".join(["%s"] * len(ids))
    rows = fetch_all(src, f"SELECT * FROM CATEGORIAS WHERE ID_Categoria IN ({marks})",
                     tuple(ids))
    mapping: dict[int, int] = {}
    for r in rows:
        local = fetch_all(dst, "SELECT ID_Categoria FROM CATEGORIAS WHERE Slug=%s",
                          (r["Slug"],))
        if local:
            mapping[r["ID_Categoria"]] = local[0]["ID_Categoria"]
            continue
        cols = [c for c in r.keys() if c != "ID_Categoria"]
        sql = (f"INSERT INTO CATEGORIAS ({', '.join(cols)}) "
               f"VALUES ({', '.join(['%s'] * len(cols))})")
        dst.execute(sql, tuple(r[c] for c in cols))
        mapping[r["ID_Categoria"]] = dst.lastrowid
    return mapping


def remap_recintos(src, dst, ids: set[int], map_ciud: dict[int, int]) -> dict[int, int]:
    if not ids:
        return {}
    marks = ",".join(["%s"] * len(ids))
    rows = fetch_all(src, f"SELECT * FROM RECINTOS WHERE ID_Recinto IN ({marks})",
                     tuple(ids))
    mapping: dict[int, int] = {}
    for r in rows:
        id_ciudad = map_ciud.get(r["ID_Ciudad"], r["ID_Ciudad"])
        local = fetch_all(
            dst,
            """SELECT ID_Recinto FROM RECINTOS
               WHERE ID_Ciudad=%s AND Nombre_Canonico=%s
                 AND COALESCE(Direccion_Fisica,'')=COALESCE(%s,'')""",
            (id_ciudad, r["Nombre_Canonico"], r.get("Direccion_Fisica")),
        )
        if local:
            mapping[r["ID_Recinto"]] = local[0]["ID_Recinto"]
            continue
        cols = [c for c in r.keys() if c not in ("ID_Recinto",)]
        vals = [id_ciudad if c == "ID_Ciudad" else r[c] for c in cols]
        sql = (f"INSERT INTO RECINTOS ({', '.join(cols)}) "
               f"VALUES ({', '.join(['%s'] * len(cols))})")
        dst.execute(sql, tuple(vals))
        mapping[r["ID_Recinto"]] = dst.lastrowid
    return mapping


def remap_fuentes(src, dst, ids: set[int], map_ciud: dict[int, int]) -> dict[int, int]:
    if not ids:
        return {}
    marks = ",".join(["%s"] * len(ids))
    rows = fetch_all(src,
                     f"SELECT * FROM BIBLIOTECA_FUENTES WHERE ID_Fuente IN ({marks})",
                     tuple(ids))
    mapping: dict[int, int] = {}
    for r in rows:
        id_ciudad = map_ciud.get(r["ID_Ciudad"], r["ID_Ciudad"])
        local = fetch_all(
            dst,
            "SELECT ID_Fuente FROM BIBLIOTECA_FUENTES WHERE ID_Ciudad=%s AND URL_Base=%s",
            (id_ciudad, r["URL_Base"]),
        )
        if local:
            mapping[r["ID_Fuente"]] = local[0]["ID_Fuente"]
            continue
        cols = [c for c in r.keys() if c != "ID_Fuente"]
        vals = [id_ciudad if c == "ID_Ciudad" else r[c] for c in cols]
        sql = (f"INSERT INTO BIBLIOTECA_FUENTES ({', '.join(cols)}) "
               f"VALUES ({', '.join(['%s'] * len(cols))})")
        dst.execute(sql, tuple(vals))
        mapping[r["ID_Fuente"]] = dst.lastrowid
    return mapping


# ---------------------------------------------------------------------------
# Copia de eventos
# ---------------------------------------------------------------------------

def insert_row(cur, table: str, row: dict) -> None:
    cols = list(row.keys())
    sql = (f"INSERT INTO `{table}` ({', '.join(f'`{c}`' for c in cols)}) "
           f"VALUES ({', '.join(['%s'] * len(cols))})")
    cur.execute(sql, tuple(row[c] for c in cols))


def pull(args) -> None:
    railway = ia.resolve_ingest_target("railway")
    local = ia.resolve_ingest_target("local")

    if local.db_host not in HOSTS_LOCALES:
        sys.exit(f"Destino local no es local ({local.db_host}). Abortando: "
                 "este script NUNCA escribe fuera de tu MySQL local.")
    if (railway.db_host, railway.db_port, railway.db_name) == \
       (local.db_host, local.db_port, local.db_name):
        sys.exit("Origen y destino son la misma BD. Abortando.")

    print(f"Origen (solo lectura): {railway.db_user}@{railway.db_host}:{railway.db_port}/{railway.db_name}")
    print(f"Destino (escritura):   {local.db_user}@{local.db_host}:{local.db_port}/{local.db_name}")

    conn_r = ia.get_connection(railway)
    conn_l = ia.get_connection(local)
    try:
        with conn_r.cursor() as src:
            where, params = [], []
            if args.estado.upper() != "TODOS":
                where.append("Estado = %s")
                params.append(args.estado)
            if args.poblacion:
                where.append("Poblacion_Nombre = %s")
                params.append(args.poblacion)
            sql_where = f"WHERE {' AND '.join(where)}" if where else ""
            eventos = fetch_all(
                src,
                f"""SELECT * FROM EVENTOS_MASTER {sql_where}
                    ORDER BY Fecha_Creacion DESC LIMIT {int(args.limit)}""",
                tuple(params),
            )
            if not eventos:
                print("No hay eventos que cumplan el filtro en Railway.")
                return
            ev_ids = [e["ID_Unico_Evento"] for e in eventos]
            marks = ",".join(["%s"] * len(ev_ids))
            print(f"Eventos a descargar: {len(ev_ids)} "
                  f"(población: {args.poblacion or 'todas'}, estado: {args.estado})")

            horarios = fetch_all(src, f"SELECT * FROM EVENTO_HORARIOS WHERE ID_Unico_Evento IN ({marks})", tuple(ev_ids))
            cats = fetch_all(src, f"SELECT * FROM EVENTO_CATEGORIAS WHERE ID_Unico_Evento IN ({marks})", tuple(ev_ids))
            fuentes = fetch_all(src, f"SELECT * FROM EVENTO_FUENTES WHERE ID_Unico_Evento IN ({marks})", tuple(ev_ids))
            binarios = fetch_all(src, f"SELECT * FROM BINARIOS_STORAGE WHERE ID_Unico_Evento IN ({marks})", tuple(ev_ids))

            blobs = []
            if not args.sin_imagenes:
                try:
                    blobs = fetch_all(src, f"SELECT * FROM IMAGENES_BLOB WHERE ID_Unico IN ({marks})", tuple(ev_ids))
                except Exception as exc:
                    print(f"Aviso: no se pudo leer IMAGENES_BLOB en origen ({exc}); se omiten imágenes")

        print(f"  · horarios={len(horarios)} categorías={len(cats)} "
              f"fuentes={len(fuentes)} binarios={len(binarios)} blobs={len(blobs)}")

        if args.dry_run:
            print("DRY-RUN: no se escribe nada en local.")
            return

        if not args.yes:
            resp = input("Escribe 'si' para volcar estos eventos en tu BD local: ").strip().lower()
            if resp not in {"si", "sí", "y", "yes"}:
                sys.exit("Cancelado.")

        with conn_r.cursor() as src, conn_l.cursor() as dst:
            # 1. Maestras con remapeo de IDs
            map_ciud = remap_ciudades(src, dst,
                                      {e["ID_Ciudad"] for e in eventos if e["ID_Ciudad"]})
            upsert_codigos_postales(src, dst,
                                    {e["CP_Evento"] for e in eventos if e["CP_Evento"]},
                                    map_ciud)
            map_cat = remap_categorias(src, dst,
                                       {c["ID_Categoria"] for c in cats})
            map_rec = remap_recintos(src, dst,
                                     {e["ID_Recinto"] for e in eventos if e["ID_Recinto"]},
                                     map_ciud)
            map_fue = remap_fuentes(src, dst,
                                    {f["ID_Fuente"] for f in fuentes},
                                    map_ciud)

            # 2. Sustitución por ID: borrar hijas + master de esos eventos
            for tabla in ("EVENTO_FUENTES", "EVENTO_CATEGORIAS",
                          "EVENTO_HORARIOS", "BINARIOS_STORAGE"):
                dst.execute(f"DELETE FROM {tabla} WHERE ID_Unico_Evento IN ({marks})",
                            tuple(ev_ids))
            dst.execute(f"DELETE FROM EVENTOS_MASTER WHERE ID_Unico_Evento IN ({marks})",
                        tuple(ev_ids))

            # 3. Insertar master con IDs remapeados
            for e in eventos:
                row = dict(e)
                if row.get("ID_Ciudad") in map_ciud:
                    row["ID_Ciudad"] = map_ciud[row["ID_Ciudad"]]
                if row.get("ID_Recinto") in map_rec:
                    row["ID_Recinto"] = map_rec[row["ID_Recinto"]]
                insert_row(dst, "EVENTOS_MASTER", row)

            # 4. Hijas
            for h in horarios:
                insert_row(dst, "EVENTO_HORARIOS",
                           {k: v for k, v in h.items() if k != "ID_Horario"})
            for c in cats:
                row = dict(c)
                if row["ID_Categoria"] in map_cat:
                    row["ID_Categoria"] = map_cat[row["ID_Categoria"]]
                insert_row(dst, "EVENTO_CATEGORIAS", row)
            for f in fuentes:
                row = {k: v for k, v in f.items() if k != "ID_Evento_Fuente"}
                if row["ID_Fuente"] in map_fue:
                    row["ID_Fuente"] = map_fue[row["ID_Fuente"]]
                insert_row(dst, "EVENTO_FUENTES", row)
            for b in binarios:
                insert_row(dst, "BINARIOS_STORAGE",
                           {k: v for k, v in b.items() if k != "ID_Binario"})

            # 5. Imágenes: blob en BD + fichero en static/images
            if blobs:
                dst.execute(IMAGENES_BLOB_DDL)
                for bl in blobs:
                    dst.execute(
                        """INSERT INTO IMAGENES_BLOB
                             (ID_Unico, Nombre_Archivo, Contenido, Content_Type, Bytes)
                           VALUES (%s,%s,%s,%s,%s)
                           ON DUPLICATE KEY UPDATE Contenido=VALUES(Contenido),
                             Content_Type=VALUES(Content_Type), Bytes=VALUES(Bytes)""",
                        (bl["ID_Unico"], bl["Nombre_Archivo"], bl["Contenido"],
                         bl.get("Content_Type"), bl["Bytes"]),
                    )
                    ev_dir = IMAGES_DIR / bl["ID_Unico"]
                    ev_dir.mkdir(parents=True, exist_ok=True)
                    (ev_dir / bl["Nombre_Archivo"]).write_bytes(bl["Contenido"])

        conn_l.commit()
        extra = f" (+{len(blobs)} imágenes)" if blobs else ""
        print(f"OK: {len(ev_ids)} eventos volcados en local{extra}")
    except Exception:
        conn_l.rollback()
        raise
    finally:
        conn_r.close()
        conn_l.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=100,
                    help="Número de eventos a descargar (default 100)")
    ap.add_argument("--poblacion", default=None,
                    help="Filtra por Poblacion_Nombre (ej. 'Malgrat de Mar')")
    ap.add_argument("--estado", default="ACTIVO",
                    help="Estado de los eventos (default ACTIVO; 'TODOS' desactiva el filtro)")
    ap.add_argument("--sin-imagenes", action="store_true",
                    help="No copiar IMAGENES_BLOB ni ficheros de static/images")
    ap.add_argument("--dry-run", action="store_true",
                    help="Solo lee de Railway y muestra conteos; no escribe en local")
    ap.add_argument("--yes", action="store_true", help="No pedir confirmación")
    args = ap.parse_args()
    pull(args)


if __name__ == "__main__":
    main()
