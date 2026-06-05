"""Capa Gate pre-LLM: filtros baratos (sin LLM)."""

from __future__ import annotations

from datetime import date
from typing import List

from app.ingestion.models import EventCandidate


def apply_gate(
    candidates: List[EventCandidate],
    *,
    drop_past_events: bool = True,
    today: date | None = None,
) -> List[EventCandidate]:
    today = today or date.today()
    out: List[EventCandidate] = []
    for c in candidates:
        if not c.titulo_cat and not c.titulo_es:
            continue
        if drop_past_events and c.fecha_inicio < today:
            continue
        out.append(c)
    return out
