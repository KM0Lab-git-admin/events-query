"""Capa Merger: de candidatos a fila lista para persistir."""

from __future__ import annotations

import hashlib
from typing import List

from app.ingestion.models import EventCandidate, IngestionContext, MergedEvent


def _stable_id(url: str, fecha_iso: str, titulo: str) -> str:
    raw = f"{url}|{fecha_iso}|{titulo.strip().lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _normalize_title_pair(c: EventCandidate) -> tuple[str, str]:
    cat = (c.titulo_cat or c.titulo_es or "").strip() or "Sense títol"
    es = (c.titulo_es or c.titulo_cat or "").strip() or "Sin título"
    if len(cat) > 255:
        cat = cat[:252] + "..."
    if len(es) > 255:
        es = es[:252] + "..."
    return cat, es


def merge_candidates(
    candidates: List[EventCandidate],
    ctx: IngestionContext,
) -> List[MergedEvent]:
    merged: List[MergedEvent] = []
    for c in candidates:
        titulo_cat, titulo_es = _normalize_title_pair(c)
        fecha_s = c.fecha_inicio.isoformat()
        uid = _stable_id(c.url_origen, fecha_s, titulo_cat)
        lugar = (c.lugar_nombre or ctx.poblacion_nombre or "—").strip()[:255]
        es_grat = c.es_gratuito if c.es_gratuito is not None else True
        merged.append(
            MergedEvent(
                id_unico_evento=uid,
                metodo_ingesta="SCRAPING",
                id_usuario_carga="ingestion_cli",
                fuente_id="URL_ESTRUCTURAL",
                fuente_url_original=c.url_origen[:2048],
                estado="ACTIVO",
                id_ciudad=ctx.id_ciudad,
                cp_evento=ctx.cp_default,
                poblacion_nombre=ctx.poblacion_nombre,
                lugar_nombre=lugar,
                idioma_origen=c.idioma_origen[:2],
                titulo_cat=titulo_cat,
                titulo_es=titulo_es,
                desc_cat=c.desc_cat,
                desc_es=c.desc_es,
                fecha_inicio=c.fecha_inicio,
                hora_inicio=c.hora_inicio,
                es_gratuito=es_grat,
                requiere_inscripcion=False,
                tags_es=[],
                tags_cat=[],
            )
        )
    return merged
