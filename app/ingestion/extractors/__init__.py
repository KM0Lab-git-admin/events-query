"""Registro de extractores: orden fijo y genérico."""

from __future__ import annotations

import logging
from typing import List

from app.ingestion.extractors.html_heuristic import extract_html_heuristic
from app.ingestion.extractors.ical_extract import extract_ical_events
from app.ingestion.extractors.json_ld import extract_json_ld_events
from app.ingestion.models import EventCandidate, FetchedDocument

logger = logging.getLogger(__name__)


def extract_events(doc: FetchedDocument) -> List[EventCandidate]:
    body = doc.body
    url = doc.url
    ct = (doc.content_type or "").lower()

    if body[:40].lstrip().upper().startswith(b"BEGIN:VCALENDAR"):
        events = extract_ical_events(body, url)
        if events:
            logger.info("Extractor: ical -> %d eventos", len(events))
            return events

    if "calendar" in ct or url.lower().endswith(".ics"):
        events = extract_ical_events(body, url)
        if events:
            logger.info("Extractor: ical(ct) -> %d eventos", len(events))
            return events

    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        text = body.decode("utf-8", errors="replace")

    events = extract_json_ld_events(text, url)
    if events:
        logger.info("Extractor: json-ld -> %d eventos", len(events))
        return events

    events = extract_html_heuristic(text, url)
    logger.info("Extractor: html heurístico -> %d eventos", len(events))
    return events
