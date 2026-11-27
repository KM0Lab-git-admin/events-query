"""Conexión a animalista_db para los scripts de El Viajero Animalista.

Variables de entorno (en .env):
    ANIMALISTA_DB_HOST, ANIMALISTA_DB_PORT, ANIMALISTA_DB_USER,
    ANIMALISTA_DB_PASSWORD, ANIMALISTA_DB_NAME (default: animalista_db)
Si faltan, se usan DB_HOST / DB_PORT / DB_USER / DB_PASSWORD (mismo MySQL que
events_db) con la base de datos animalista_db.

Regla de oro heredada de KM0: estos scripts nunca escriben fuera del MySQL
configurado como local; Railway se alimenta por publicación explícita.
"""

from __future__ import annotations

import argparse
import os

import pymysql
import pymysql.cursors

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # pragma: no cover
    pass


def _env(name: str, default: str | None = None) -> str | None:
    return os.getenv(f"ANIMALISTA_DB_{name}") or os.getenv(f"DB_{name}") or default


def db_params() -> dict:
    return {
        "host": _env("HOST", "127.0.0.1"),
        "port": int(_env("PORT", "3306")),
        "user": _env("USER", "events_user"),
        "password": _env("PASSWORD", ""),
        "database": os.getenv("ANIMALISTA_DB_NAME", "animalista_db"),
    }


def parse_db_args(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--db-name", default=None, help="Base de datos destino (default ANIMALISTA_DB_NAME o animalista_db)")


def connect(args: argparse.Namespace | None = None, *, dict_cursor: bool = False):
    p = db_params()
    if args is not None and getattr(args, "db_name", None):
        p["database"] = args.db_name
    return pymysql.connect(
        host=p["host"], port=p["port"], user=p["user"], password=p["password"],
        database=p["database"], charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor if dict_cursor else pymysql.cursors.Cursor,
        autocommit=False,
    )
