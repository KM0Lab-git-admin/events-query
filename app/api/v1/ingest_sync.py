"""
Subida de imágenes de ingesta hacia el servidor (ops).

Protegido por X-Ingest-Secret (= INGEST_UPLOAD_SECRET o DB_PASSWORD).

Persiste en disco (caché) y en IMAGENES_BLOB (MySQL) para sobrevivir deploys.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Header, HTTPException, Request, status

from app.config import settings
from app.services import db_service
from app.services import image_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingest", tags=["Ingest"])

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
    """Recibe bytes de una imagen y la guarda en disco + IMAGENES_BLOB."""
    _verify_secret(x_ingest_secret)

    err = image_store.validate_ids(event_id, filename)
    if err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)

    content = await request.body()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cuerpo vacío")
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Archivo demasiado grande",
        )

    await image_store.ensure_blob_table(db_service)
    public_path = await image_store.save_image(db_service, event_id, filename, content)
    logger.info("Imagen de ingesta guardada: %s (%d bytes)", public_path, len(content))

    return {"ok": True, "path": public_path, "bytes": len(content)}


@router.delete("/images/{event_id}")
async def delete_event_images(
    event_id: str,
    x_ingest_secret: str | None = Header(default=None, alias="X-Ingest-Secret"),
):
    """Elimina imágenes del id en disco y en IMAGENES_BLOB."""
    _verify_secret(x_ingest_secret)

    if not image_store.EVENT_ID_RE.match(event_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="ID de evento inválido"
        )

    await image_store.ensure_blob_table(db_service)
    removed = await image_store.delete_images(db_service, event_id)
    return {"ok": True, "event_id": event_id, "removed": removed}
