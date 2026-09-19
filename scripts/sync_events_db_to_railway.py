"""Copia la BD events_db local a Railway (esquema + datos) con pymysql.

DESTRUCTIVO en el destino: borra todas las tablas de la BD Railway de
events-query y las recrea con el contenido local. La BD local NO se modifica.

Origen : BD local según .env (DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME).
Destino: BD Railway según .env (RAILWAY_DB_HOST/.../RAILWAY_DB_NAME).

Uso:
    python scripts/sync_events_db_to_railway.py --dry-run   # solo compara
    python scripts/sync_events_db_to_railway.py --yes       # sobrescribe Railway

Tras el sync, subir las imágenes con:
    python scripts/upload_images_railway.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Permite ejecutar: python scripts/sync_events_db_to_railway.py ...
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pymysql

import ingest_all as ia

# Tablas de historial operativo que NO se copian (se recrean vacías en destino
# con el esquema local; conservar historiales de ambos entornos no es posible
# en una sobrescritura y el de Railway se pierde igualmente al dropear).
SKIP_DATA_TABLES: set[str] = set()


def list_tables(cur) -> list[str]:
    cur.execute("SHOW FULL TABLES WHERE Table_type = 'BASE TABLE'")
    return [list(row.values())[0] for row in cur.fetchall()]


def dump_create_table(cur, table: str) -> str:
    cur.execute(f"SHOW CREATE TABLE `{table}`")
    return list(cur.fetchone().values())[1]


def column_names(cur, table: str) -> list[str]:
    cur.execute(f"SHOW COLUMNS FROM `{table}`")
    return [row["Field"] for row in cur.fetchall()]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--yes", action="store_true", help="confirmar sobrescritura")
    ap.add_argument("--dry-run", action="store_true", help="solo leer y mostrar conteos")
    args = ap.parse_args()

    local = ia.resolve_ingest_target("local")
    railway = ia.resolve_ingest_target("railway")

    if railway.db_host in {"localhost", "127.0.0.1", "mysql"}:
        sys.exit("El destino Railway resuelve a un host local. Revisa RAILWAY_DB_* en .env.")

    print(f"Origen : {local.db_user}@{local.db_host}:{local.db_port}/{local.db_name}")
    print(f"Destino: {railway.db_user}@{railway.db_host}:{railway.db_port}/{railway.db_name}")

    print("\nLeyendo tablas locales...")
    payloads: list[tuple[str, str, list[str], list[tuple]]] = []
    with ia.get_connection(local) as src, src.cursor() as scur:
        tables = list_tables(scur)
        print(f"  {len(tables)} tablas: {', '.join(tables)}")
        for table in tables:
            create_sql = dump_create_table(scur, table)
            cols = column_names(scur, table)
            if table in SKIP_DATA_TABLES:
                rows: list[tuple] = []
            else:
                scur.execute(f"SELECT * FROM `{table}`")
                rows = [tuple(row[c] for c in cols) for row in scur.fetchall()]
            payloads.append((table, create_sql, cols, rows))
            print(f"  · {table}: {len(rows)} filas")

    if args.dry_run:
        print("\nDry-run: no se escribe nada en Railway.")
        return

    if not args.yes:
        print("\nEsto BORRA y reemplaza TODAS las tablas del destino (Railway).")
        if input("Escribe 'si' para continuar: ").strip().lower() not in {"si", "sí", "y", "yes"}:
            sys.exit("Cancelado.")

    print("\nEscribiendo en Railway (reemplaza tablas existentes)...")
    with ia.get_connection(railway) as dst, dst.cursor() as dcur:
        dcur.execute("SET FOREIGN_KEY_CHECKS=0")
        remote_tables = list_tables(dcur)
        for table in remote_tables:
            dcur.execute(f"DROP TABLE IF EXISTS `{table}`")
            print(f"  - drop {table}")
        dst.commit()

        for table, create_sql, cols, rows in payloads:
            dcur.execute(create_sql)
            if rows:
                placeholders = ", ".join(["%s"] * len(cols))
                col_list = ", ".join(f"`{c}`" for c in cols)
                dcur.executemany(
                    f"INSERT INTO `{table}` ({col_list}) VALUES ({placeholders})", rows
                )
            print(f"  + {table} ({len(rows)} filas)")
        dcur.execute("SET FOREIGN_KEY_CHECKS=1")
        dst.commit()

    print("\nListo. Recuerda subir las imágenes: python scripts/upload_images_railway.py")


if __name__ == "__main__":
    main()
