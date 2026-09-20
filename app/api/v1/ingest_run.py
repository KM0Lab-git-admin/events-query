"""
Lanzamiento manual de la ingesta dentro del propio servicio (ops).

Protegido por X-Ingest-Secret (= INGEST_UPLOAD_SECRET o DB_PASSWORD), igual
que la subida de imágenes de ingest_sync.py.

POST /api/v1/ingest/run    -> lanza `python scripts/ingest_all.py --config
                              <INGEST_CRON_CONFIG> --target local --images-via-api`
                              como subproceso en background (202 Accepted).
                              409 si ya hay una ejecución en marcha (lock-file).
GET  /api/v1/ingest/status -> estado del lock y último run en INGESTA_RUNS.

Pensado para Railway: el subproceso usa las DB_* internas del servicio
(--target local) y sube las imágenes a la propia API vía loopback
(--images-via-api), de modo que queden en disco + IMAGENES_BLOB y sobrevivan
a los redeploys.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, status

from app.config import settings
from app.services import db_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingest", tags=["Ingest"])

# Raíz del repo (…/app/api/v1/ingest_run.py -> parents[3])
_REPO_ROOT = Path(__file__).resolve().parents[3]
_LOCK_FILE = _REPO_ROOT / "scripts" / ".ingest.lock"
_LOCK_MAX_AGE_HORAS = 6  # coherente con ingest_all.LOCK_MAX_AGE_HORAS
_LOGS_DIR = _REPO_ROOT / "logs"


def _expected_secret() -> str:
    explicit = (getattr(settings, "ingest_upload_secret", None) or "").strip()
    if explicit:
        return explicit
    return (settings.db_password or "").strip()


def _verify_secret(header: str | None) -> None:
    expected = _expected_secret()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ingesta remota no configurada en el servidor",
        )
    if not header or header.strip() != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Secret de ingesta inválido",
        )


def _lock_info() -> dict:
    """Estado del lock-file del pipeline (mismo fichero que usa ingest_all)."""
    if not _LOCK_FILE.exists():
        return {"running": False}
    try:
        edad_h = (time.time() - _LOCK_FILE.stat().st_mtime) / 3600
        contenido = _LOCK_FILE.read_text(encoding="utf-8", errors="ignore").strip()
    except OSError:
        return {"running": False}
    if edad_h >= _LOCK_MAX_AGE_HORAS:
        return {"running": False, "stale_lock": True,
                "lock_age_hours": round(edad_h, 2), "lock_content": contenido}
    return {"running": True, "lock_age_hours": round(edad_h, 2),
            "lock_content": contenido}


def _cron_config_path() -> Path:
    cfg = (os.getenv("INGEST_CRON_CONFIG") or "scripts/ingest_cron.json").strip()
    p = Path(cfg)
    return p if p.is_absolute() else _REPO_ROOT / p


@router.post("/run", status_code=status.HTTP_202_ACCEPTED)
async def run_ingestion(
    x_ingest_secret: str | None = Header(default=None, alias="X-Ingest-Secret"),
):
    """Lanza la ingesta en background dentro de este servicio."""
    _verify_secret(x_ingest_secret)

    lock = _lock_info()
    if lock.get("running"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya hay una ingesta en marcha ({lock.get('lock_content')})",
        )

    config_path = _cron_config_path()
    if not config_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Config de cron no encontrada: {config_path}",
        )

    env = os.environ.copy()
    # Imágenes vía API (disco del servicio + IMAGENES_BLOB), no al disco del
    # subproceso: así sobreviven a los redeploys.
    env["INGEST_IMAGES_VIA_API"] = "1"
    # Loopback a esta misma API para la subida de imágenes.
    env.setdefault("EVENTS_API_BASE_URL", f"http://127.0.0.1:{settings.api_port}")
    # Marca el origen del run en INGESTA_RUNS.Target (visible en la pestaña
    # Costes del front de ops).
    env.setdefault("INGEST_RUN_ORIGIN", "endpoint-railway")

    _LOGS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = _LOGS_DIR / f"ingest_run_{stamp}.log"

    cmd = [
        sys.executable,
        "scripts/ingest_all.py",
        "--config", str(config_path),
        "--target", "local",
        "--images-via-api",
    ]
    try:
        log_fh = open(log_path, "a", encoding="utf-8")
        proc = subprocess.Popen(  # noqa: S603
            cmd,
            cwd=str(_REPO_ROOT),
            env=env,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
        )
    except OSError as exc:
        logger.exception("No se pudo lanzar la ingesta")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"No se pudo lanzar el subproceso: {exc}",
        )

    logger.info("Ingesta lanzada vía endpoint: pid=%s log=%s", proc.pid, log_path)
    return {
        "ok": True,
        "pid": proc.pid,
        "command": cmd,
        "config": str(config_path),
        "log": str(log_path),
        "started_at": datetime.now().isoformat(timespec="seconds"),
    }


@router.get("/status")
async def ingest_status(
    x_ingest_secret: str | None = Header(default=None, alias="X-Ingest-Secret"),
):
    """Estado del lock (¿run en marcha?) y último run persistido."""
    _verify_secret(x_ingest_secret)

    status_payload: dict = {"lock": _lock_info(), "last_run": None}
    try:
        async with db_service.get_connection() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """
                    SELECT ID_Run, Inicio, Fin, Target, Modelo, Coste_USD,
                           Eventos_Persistidos, Noticias_Persistidas,
                           Targets_OK, Targets_Skip, Targets_Error
                    FROM INGESTA_RUNS
                    ORDER BY Inicio DESC
                    LIMIT 1
                    """
                )
                row = await cursor.fetchone()
        if row:
            status_payload["last_run"] = {
                "id_run": row[0],
                "inicio": row[1].isoformat() if row[1] else None,
                "fin": row[2].isoformat() if row[2] else None,
                "target": row[3],
                "modelo": row[4],
                "coste_usd": float(row[5]) if row[5] is not None else 0.0,
                "eventos": row[6],
                "noticias": row[7],
                "targets_ok": row[8],
                "targets_skip": row[9],
                "targets_error": row[10],
            }
    except Exception as exc:
        # p.ej. INGESTA_RUNS aún no creada (falta SQL/costes_delta.sql)
        logger.warning("No se pudo leer INGESTA_RUNS: %s", exc)
        status_payload["last_run_error"] = str(exc)

    return status_payload
