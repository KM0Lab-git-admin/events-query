"""
Subida de imágenes de ingesta hacia el servidor (ops).

Protegido por X-Ingest-Secret (= INGEST_UPLOAD_SECRET o DB_PASSWORD).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Request, status

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingest", tags=["Ingest"])

STATIC_IMAGES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "static" / "images"

EVENT_ID_RE = re.compile(r"^[a-f0-9]{64}$")
FILENAME_RE = re.compile(r"^\d{2}_[a-f0-9]{12}\.(jpg|jpeg|png|webp)$", re.IGNORECASE)
MAX_FILE_BYTES = 20 * 1024 * 1024


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
            detail="Upload de imágenes no configurado en el servidor",
        )
    if not header or header.strip() != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Secret de ingesta inválido",
        )


@router.put("/images/{event_id}/{filename}")
async def upload_event_image(
    event_id: str,
    filename: str,
    request: Request,
    x_ingest_secret: str | None = Header(default=None, alias="X-Ingest-Secret"),
):
    """Recibe bytes de una imagen y la guarda en static/images/{event_id}/{filename}."""
    _verify_secret(x_ingest_secret)

    if not EVENT_ID_RE.match(event_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ID de evento inválido")
    if not FILENAME_RE.match(filename):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nombre de archivo inválido")

    content = await request.body()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cuerpo vacío")
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Archivo demasiado grande")

    dest_dir = STATIC_IMAGES_DIR / event_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / filename
    dest_path.write_bytes(content)

    logger.info("Imagen de ingesta guardada: %s (%d bytes)", dest_path.relative_to(STATIC_IMAGES_DIR.parent), len(content))

    return {
        "ok": True,
        "path": f"/static/images/{event_id}/{filename}",
        "bytes": len(content),
    }
