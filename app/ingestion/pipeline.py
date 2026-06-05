"""Orquestación de las 7 capas (embedder omitido en CLI — sin cola)."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.ingestion.connector import fetch_url
from app.ingestion.extractors import extract_events
from app.ingestion.gate import apply_gate
from app.ingestion.merger import merge_candidates
from app.ingestion.models import IngestionContext, MergedEvent
from app.ingestion.persister import (
    ensure_geography,
    get_or_create_fuente_target,
    persist_merged_events,
)
from app.services.database import DatabaseService

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class IngestionResult:
    url: str
    candidates_raw: int
    candidates_after_gate: int
    persisted: int
    merged_preview: tuple[MergedEvent, ...] = ()


async def run_ingestion_url(
    db: DatabaseService,
    url: str,
    *,
    id_ciudad: int,
    cp: str,
    poblacion_nombre: str,
    lat: float = 41.64,
    lng: float = 2.74,
    drop_past_events: bool = True,
    dry_run: bool = False,
) -> IngestionResult:
    """
    Ejecuta el pipeline completo para una URL (típicamente listado de agenda).
    Si dry_run=True, no toca la base de datos (solo fetch + extract + gate + merge).
    """
    doc = await fetch_url(url)
    raw_list = extract_events(doc)
    gated = apply_gate(raw_list, drop_past_events=drop_past_events)
    ctx = IngestionContext(
        id_fuente=0,
        id_ciudad=id_ciudad,
        cp_default=cp,
        poblacion_nombre=poblacion_nombre,
    )
    merged = merge_candidates(gated, ctx)

    if dry_run:
        return IngestionResult(
            url=url,
            candidates_raw=len(raw_list),
            candidates_after_gate=len(gated),
            persisted=len(merged),
            merged_preview=tuple(merged),
        )

    await db.connect()
    try:
        await ensure_geography(
            db,
            id_ciudad=id_ciudad,
            cp=cp,
            nombre_ciudad=poblacion_nombre,
            lat=lat,
            lng=lng,
        )
        id_fuente, id_target = await get_or_create_fuente_target(
            db, page_url=url, id_ciudad=id_ciudad
        )
        _ = id_target  # SCRAPING_TARGETS sigue registrado; no se persiste captura cruda

        ctx = IngestionContext(
            id_fuente=id_fuente,
            id_ciudad=id_ciudad,
            cp_default=cp,
            poblacion_nombre=poblacion_nombre,
        )
        merged_db = merge_candidates(gated, ctx)
        persisted = await persist_merged_events(db, merged_db, ctx=ctx)

        # Capa 7 Embedder: fuera de CLI (job asíncrono / otro proceso).
        if persisted and logger.isEnabledFor(logging.INFO):
            logger.info(
                "Embedder: omitido en CLI; generar Tags_Embedding_* aparte si procede."
            )

        return IngestionResult(
            url=url,
            candidates_raw=len(raw_list),
            candidates_after_gate=len(gated),
            persisted=persisted,
            merged_preview=(),
        )
    finally:
        await db.disconnect()
