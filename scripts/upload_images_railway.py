"""
Sube static/images/ al servidor Events Query en Railway (o local).

Usa PUT /api/v1/ingest/images/{event_id}/{filename}
Autenticación: header X-Ingest-Secret (= INGEST_UPLOAD_SECRET o RAILWAY_DB_PASSWORD / DB_PASSWORD).

Uso:
    python scripts/upload_images_railway.py
    python scripts/upload_images_railway.py --base-url https://eventquery.km0lab.com
    python scripts/upload_images_railway.py --dry-run
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import httpx

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

ROOT = Path(__file__).resolve().parent.parent
IMAGES_DIR = ROOT / "static" / "images"
DEFAULT_BASE_URL = "https://eventquery.km0lab.com"


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


def main():
    load_env()
    ap = argparse.ArgumentParser(description="Sube imágenes locales a Railway/producción.")
    ap.add_argument("--base-url", default=os.getenv("EVENTS_API_BASE_URL", DEFAULT_BASE_URL))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--timeout", type=float, default=120.0)
    args = ap.parse_args()

    base = args.base_url.rstrip("/")
    secret = resolve_secret()
    files = list(iter_local_images())
    if not files:
        sys.exit("No hay imágenes en static/images/")

    total_bytes = sum(p.stat().st_size for _, _, p in files)
    print(f"Destino: {base}")
    print(f"Archivos: {len(files)} ({total_bytes / (1024 * 1024):.1f} MB)")

    if args.dry_run:
        for eid, fname, path in files[:5]:
            print(f"  {eid}/{fname} ({path.stat().st_size} bytes)")
        if len(files) > 5:
            print(f"  ... y {len(files) - 5} más")
        return

    ok, skipped, failed = 0, 0, 0
    headers = {"X-Ingest-Secret": secret, "Content-Type": "application/octet-stream"}

    with httpx.Client(timeout=args.timeout, follow_redirects=True) as client:
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

    print(f"Listo: {ok} subidas, {skipped} omitidas, {failed} fallidas")
    if failed:
        sys.exit(1)

    # Verificación rápida de una imagen
    sample_eid, sample_fn, _ = files[0]
    check_url = f"{base}/static/images/{sample_eid}/{sample_fn}"
    try:
        r = httpx.get(check_url, timeout=30.0, follow_redirects=True)
        print(f"Verificación {check_url}: HTTP {r.status_code}")
    except httpx.HTTPError as exc:
        print(f"Verificación fallida: {exc}")


if __name__ == "__main__":
    main()
