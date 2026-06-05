"""Extracción desde iCalendar (.ics)."""

from __future__ import annotations

import logging
from datetime import date, datetime, time
from typing import List, Optional

from icalendar import Calendar

from app.ingestion.models import EventCandidate

logger = logging.getLogger(__name__)


def _to_date(dt_val) -> tuple[Optional[date], Optional[time]]:
    if dt_val is None:
        return None, None
    if isinstance(dt_val, datetime):
        return dt_val.date(), dt_val.time().replace(microsecond=0)
    if isinstance(dt_val, date) and not isinstance(dt_val, datetime):
        return dt_val, None
    try:
        d = dt_val.dt
        if isinstance(d, datetime):
            return d.date(), d.time().replace(microsecond=0)
        if isinstance(d, date) and not isinstance(d, datetime):
            return d, None
    except Exception:
        pass
    return None, None


def extract_ical_events(content: bytes, page_url: str) -> List[EventCandidate]:
    out: List[EventCandidate] = []
    try:
        cal = Calendar.from_ical(content)
    except Exception as e:
        logger.debug("ical parse error: %s", e)
        return []
    for comp in cal.walk():
        if comp.name != "VEVENT":
            continue
        try:
            summary = comp.get("summary")
            title = str(summary) if summary else "Sin título"
            uid = comp.get("uid")
            url_ev = page_url
            if uid:
                url_ev = f"{page_url}#ical-{str(uid)}"
            start = comp.get("dtstart")
            d, tm = _to_date(start)
            if not d:
                continue
            loc = comp.get("location")
            lugar = str(loc) if loc else None
            desc = comp.get("description")
            description = str(desc)[:8000] if desc else None
            out.append(
                EventCandidate(
                    url_origen=url_ev,
                    extractor="ical",
                    score_calidad=0.9,
                    fecha_inicio=d,
                    hora_inicio=tm,
                    titulo_cat=title,
                    titulo_es=title,
                    idioma_origen="ca",
                    desc_cat=description,
                    desc_es=description,
                    lugar_nombre=lugar,
                )
            )
        except (ValueError, TypeError, KeyError) as e:
            logger.debug("vevent skip: %s", e)
    return out
