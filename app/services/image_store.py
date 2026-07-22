"""
Rutas y persistencia de imágenes de eventos/noticias.

Problema: en Railway el filesystem del contenedor es efímero; cada deploy
borra static/images/ y las URLs /static/images/... pasan a 404.

Solución: además del disco (caché local / volumen opcional), guardar los
bytes en la tabla IMAGENES_BLOB (MySQL). Al arrancar y ante un miss en disco
se rehidrata desde la BD.
"""

from __future__ import annotations

import logging
import mimetypes
import os
import re
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

EVENT_ID_RE = re.compile(r"^[a-f0-9]{64}$")
FILENAME_RE = re.compile(r"^\d{2}_[a-f0-9]{12}\.(jpg|jpeg|png|webp)$", re.IGNORECASE)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS `IMAGENES_BLOB` (
  `ID_Unico` CHAR(64) NOT NULL
    COMMENT 'ID_Unico_Evento o ID_Unico_Noticia',
  `Nombre_Archivo` VARCHAR(255) NOT NULL,
  `Contenido` LONGBLOB NOT NULL,
  `Content_Type` VARCHAR(64) NULL,
  `Bytes` INT NOT NULL,
  `Actualizado` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`ID_Unico`, `Nombre_Archivo`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""


def resolve_static_images_dir() -> Path:
    """Directorio de imágenes en disco (caché).

    Prioridad:
    1. STATIC_IMAGES_DIR (ruta absoluta o relativa)
    2. RAILWAY_VOLUME_MOUNT_PATH/images (volumen persistente Railway)
    3. <repo>/static/images
    """
    explicit = (os.getenv("STATIC_IMAGES_DIR") or "").strip()
    if explicit:
        return Path(explicit)

    volume = (os.getenv("RAILWAY_VOLUME_MOUNT_PATH") or "").strip()
    if volume:
        return Path(volume) / "images"

    return Path(__file__).resolve().parent.parent.parent / "static" / "images"


def content_type_for(filename: str) -> str:
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


def validate_ids(event_id: str, filename: str) -> Optional[str]:
    if not EVENT_ID_RE.match(event_id):
        return "ID de evento inválido"
    if not FILENAME_RE.match(filename):
        return "Nombre de archivo inválido"
    return None


def disk_path(event_id: str, filename: str, root: Optional[Path] = None) -> Path:
    base = root or resolve_static_images_dir()
    return base / event_id / filename


def write_to_disk(event_id: str, filename: str, content: bytes, root: Optional[Path] = None) -> Path:
    path = disk_path(event_id, filename, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


async def ensure_blob_table(db) -> None:
    await db.execute_query(_CREATE_TABLE_SQL, fetch_all=False)


async def save_image(db, event_id: str, filename: str, content: bytes) -> str:
    """Persiste en disco + MySQL. Devuelve la URL pública relativa."""
    write_to_disk(event_id, filename, content)
    ctype = content_type_for(filename)
    await db.execute_query(
        """
        INSERT INTO IMAGENES_BLOB (ID_Unico, Nombre_Archivo, Contenido, Content_Type, Bytes)
        VALUES (%s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
          Contenido=VALUES(Contenido),
          Content_Type=VALUES(Content_Type),
          Bytes=VALUES(Bytes)
        """,
        (event_id, filename, content, ctype, len(content)),
        fetch_all=False,
    )
    return f"/static/images/{event_id}/{filename}"


async def delete_images(db, event_id: str) -> bool:
    """Borra carpeta en disco y filas blob del id."""
    import shutil

    root = resolve_static_images_dir()
    dest = root / event_id
    removed = False
    if dest.is_dir():
        shutil.rmtree(dest, ignore_errors=True)
        removed = True
    await db.execute_query(
        "DELETE FROM IMAGENES_BLOB WHERE ID_Unico=%s",
        (event_id,),
        fetch_all=False,
    )
    return removed


async def load_blob(db, event_id: str, filename: str) -> Optional[Tuple[bytes, str]]:
    rows = await db.execute_query(
        """
        SELECT Contenido, Content_Type, Bytes
        FROM IMAGENES_BLOB
        WHERE ID_Unico=%s AND Nombre_Archivo=%s
        LIMIT 1
        """,
        (event_id, filename),
    )
    if not rows:
        return None
    row = rows[0]
    content = row.get("Contenido") or row.get("contenido")
    if content is None:
        return None
    if isinstance(content, memoryview):
        content = content.tobytes()
    elif not isinstance(content, (bytes, bytearray)):
        content = bytes(content)
    ctype = row.get("Content_Type") or row.get("content_type") or content_type_for(filename)
    return bytes(content), ctype


async def ensure_on_disk(db, event_id: str, filename: str) -> Optional[Path]:
    """Devuelve path en disco; si falta, restaura desde IMAGENES_BLOB."""
    path = disk_path(event_id, filename)
    if path.is_file() and path.stat().st_size > 0:
        return path
    loaded = await load_blob(db, event_id, filename)
    if not loaded:
        return None
    content, _ = loaded
    return write_to_disk(event_id, filename, content)


async def hydrate_disk_from_db(db) -> int:
    """Reescribe a disco todas las imágenes de IMAGENES_BLOB que falten."""
    await ensure_blob_table(db)
    root = resolve_static_images_dir()
    root.mkdir(parents=True, exist_ok=True)
    rows = await db.execute_query(
        "SELECT ID_Unico, Nombre_Archivo, Contenido FROM IMAGENES_BLOB"
    )
    if not rows:
        logger.info("IMAGENES_BLOB vacía; nada que hidratar en disco")
        return 0

    restored = 0
    for row in rows:
        eid = row.get("ID_Unico") or row.get("id_unico")
        fname = row.get("Nombre_Archivo") or row.get("nombre_archivo")
        content = row.get("Contenido") or row.get("contenido")
        if not eid or not fname or content is None:
            continue
        path = root / eid / fname
        if path.is_file() and path.stat().st_size > 0:
            continue
        if isinstance(content, memoryview):
            content = content.tobytes()
        elif not isinstance(content, (bytes, bytearray)):
            content = bytes(content)
        write_to_disk(eid, fname, bytes(content), root)
        restored += 1

    logger.info(
        "Imágenes: disco=%s — hidratadas %d desde IMAGENES_BLOB (total filas=%d)",
        root,
        restored,
        len(rows),
    )
    return restored
