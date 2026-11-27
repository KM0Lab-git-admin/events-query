"""
Sube static/images/ a Railway.

Por defecto escribe en MySQL público (IMAGENES_BLOB) con RAILWAY_DB_*.
El API hidrata el disco del contenedor desde esa tabla en cada GET / arranque.

Uso:
    python scripts/upload_images_railway.py
    python scripts/upload_images_railway.py --via-http
    python scripts/upload_images_railway.py --base-url https://eventquery.uat.km0lab.com
    python scripts/upload_images_railway.py --dry-run
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import httpx

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

ROOT = Path(__file__).resolve().parent.parent
IMAGES_DIR = ROOT / "static" / "images"
DEFAULT_BASE_URL = "https://eventquery.uat.km0lab.com"


def load_env():
    if load_dotenv:
        load_dotenv(ROOT / ".env")


def resolve_secret() -> str:
    explicit = (os.getenv("INGEST_UPLOAD_SECRET") or "").strip()
    if explicit:
        return explicit
    for key in ("RAILWAY_DB_PASSWORD", "DB_PASSWORD"):
        val = (os.getenv(key) or "").strip()
        if val:
            return val
    sys.exit("Define INGEST_UPLOAD_SECRET o RAILWAY_DB_PASSWORD/DB_PASSWORD en .env")


def iter_local_images():
    if not IMAGES_DIR.is_dir():
        sys.exit(f"No existe {IMAGES_DIR}")
    for event_dir in sorted(IMAGES_DIR.iterdir()):
        if not event_dir.is_dir():
            continue
        event_id = event_dir.name
        for path in sorted(event_dir.iterdir()):
            if path.is_file():
                yield event_id, path.name, path


def _env(name: str, default: str = "") -> str:
    val = (os.getenv(name) or default).strip()
    if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
        val = val[1:-1].strip()
    return val


def upload_via_db(files: list) -> tuple[int, int]:
    """Upsert LONGBLOB en el MySQL público de Railway (mismo camino que ingest_all)."""
    import mimetypes

    import pymysql

    host = _env("RAILWAY_DB_HOST")
    port = int(_env("RAILWAY_DB_PORT", "3306") or "3306")
    user = _env("RAILWAY_DB_USER")
    password = _env("RAILWAY_DB_PASSWORD")
    name = _env("RAILWAY_DB_NAME")
    if not all([host, user, password, name]):
        sys.exit("Faltan RAILWAY_DB_HOST/USER/PASSWORD/NAME en .env")
    if host.endswith(".railway.internal") or host in ("mysql", "mysql.railway.internal"):
        sys.exit("RAILWAY_DB_HOST debe ser el host público, no mysql.railway.internal")

    create_sql = """
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
    upsert_sql = """
    INSERT INTO IMAGENES_BLOB (ID_Unico, Nombre_Archivo, Contenido, Content_Type, Bytes)
    VALUES (%s, %s, UNHEX(%s), %s, %s) AS incoming
    ON DUPLICATE KEY UPDATE
      Contenido = incoming.Contenido,
      Content_Type = incoming.Content_Type,
      Bytes = incoming.Bytes
    """

    def ctype(filename: str) -> str:
        guessed, _ = mimetypes.guess_type(filename)
        return guessed or "application/octet-stream"

    print(f"Destino MySQL: {host}:{port}/{name}")
    ok, failed = 0, 0
    conn = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=name,
        charset="utf8mb4",
        autocommit=False,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(create_sql)
            for i, (event_id, filename, path) in enumerate(files, 1):
                data = path.read_bytes()
                try:
                    cur.execute(
                        upsert_sql,
                        (event_id, filename, data.hex(), ctype(filename), len(data)),
                    )
                    ok += 1
                except Exception as exc:
                    failed += 1
                    print(f"  ERROR {event_id}/{filename}: {exc}")
                if i % 20 == 0 or i == len(files):
                    conn.commit()
                    print(f"  Progreso: {i}/{len(files)} (ok={ok}, fail={failed})")
        conn.commit()
    finally:
        conn.close()
    return ok, failed


def upload_via_http(files: list, base: str, timeout: float) -> tuple[int, int, int]:
    secret = resolve_secret()
    ok, skipped, failed = 0, 0, 0
    headers = {"X-Ingest-Secret": secret, "Content-Type": "application/octet-stream"}
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        for i, (event_id, filename, path) in enumerate(files, 1):
            url = f"{base}/api/v1/ingest/images/{event_id}/{filename}"
            data = path.read_bytes()
            try:
                r = client.put(url, content=data, headers=headers)
                if r.status_code == 200:
                    ok += 1
                elif r.status_code == 409:
                    skipped += 1
                else:
                    failed += 1
                    print(f"  ERROR {r.status_code} {event_id}/{filename}: {r.text[:200]}")
            except httpx.HTTPError as exc:
                failed += 1
                print(f"  ERROR {event_id}/{filename}: {exc}")
            if i % 20 == 0 or i == len(files):
                print(f"  Progreso: {i}/{len(files)} (ok={ok}, fail={failed})")
    return ok, skipped, failed


def main():
    load_env()
    ap = argparse.ArgumentParser(description="Sube imágenes locales a Railway/producción.")
    ap.add_argument("--base-url", default=os.getenv("EVENTS_API_BASE_URL", DEFAULT_BASE_URL))
    ap.add_argument("--via-http", action="store_true", help="PUT al API en vez de MySQL directo")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--timeout", type=float, default=120.0)
    args = ap.parse_args()

    files = list(iter_local_images())
    if not files:
        sys.exit("No hay imágenes en static/images/")

    total_bytes = sum(p.stat().st_size for _, _, p in files)
    print(f"Archivos: {len(files)} ({total_bytes / (1024 * 1024):.1f} MB)")

    if args.dry_run:
        for eid, fname, path in files[:5]:
            print(f"  {eid}/{fname} ({path.stat().st_size} bytes)")
        if len(files) > 5:
            print(f"  ... y {len(files) - 5} más")
        return

    if args.via_http:
        base = args.base_url.rstrip("/")
        print(f"Destino HTTP: {base}")
        ok, skipped, failed = upload_via_http(files, base, args.timeout)
        print(f"Listo: {ok} subidas, {skipped} omitidas, {failed} fallidas")
    else:
        ok, failed = upload_via_db(files)
        skipped = 0
        print(f"Listo: {ok} subidas, {failed} fallidas")

    if failed:
        sys.exit(1)

    sample_eid, sample_fn, _ = files[0]
    check_url = f"{args.base_url.rstrip('/')}/static/images/{sample_eid}/{sample_fn}"
    try:
        r = httpx.get(check_url, timeout=30.0, follow_redirects=True)
        print(f"Verificación {check_url}: HTTP {r.status_code}")
    except httpx.HTTPError as exc:
        print(f"Verificación fallida: {exc}")


if __name__ == "__main__":
    main()
