"""Capa Connector: descarga genérica por URL."""

from __future__ import annotations

import logging

import httpx

from app.ingestion.models import FetchedDocument

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": "EventsQuery-Ingestion/1.0 (+https://github.com/events-query)",
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,text/calendar;q=0.8,*/*;q=0.7",
}


async def fetch_url(url: str, timeout_s: float = 45.0) -> FetchedDocument:
    """
    GET de la URL objetivo con redirects.
    """
    async with httpx.AsyncClient(
        headers=DEFAULT_HEADERS,
        follow_redirects=True,
        timeout=httpx.Timeout(timeout_s),
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
        ct = response.headers.get("content-type", "").split(";")[0].strip().lower()
        if not ct:
            ct = "application/octet-stream"
        body = response.content
        logger.info("Connector: %s bytes from %s (%s)", len(body), url, ct)
        return FetchedDocument(url=url, content_type=ct, body=body)
