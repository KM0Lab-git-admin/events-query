"""Extracción desde JSON-LD (schema.org/Event)."""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, time
from typing import Any, Iterator, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.ingestion.models import EventCandidate

logger = logging.getLogger(__name__)


def _iter_json_objects(raw: str) -> Iterator[Any]:
    raw = raw.strip()
    if not raw:
        return
    if raw.startswith("["):
        data = json.loads(raw)
        if isinstance(data, list):
            for item in data:
                yield item
        else:
            yield data
        return
    decoder = json.JSONDecoder()
    idx = 0
    while idx < len(raw):
        while idx < len(raw) and raw[idx].isspace():
            idx += 1
        if idx >= len(raw):
            break
        try:
            obj, end = decoder.raw_decode(raw, idx)
            yield obj
            idx = end
        except json.JSONDecodeError:
            break


def _is_event_node(node: dict) -> bool:
    t = node.get("@type")
    if t == "Event":
        return True
    if isinstance(t, list):
        return any(x == "Event" or x == "http://schema.org/Event" for x in t)
    if isinstance(t, str) and "Event" in t:
        return True
    return False


def _walk_graph(obj: Any) -> Iterator[dict]:
    if isinstance(obj, dict):
        if "@graph" in obj and isinstance(obj["@graph"], list):
            for x in obj["@graph"]:
                yield from _walk_graph(x)
        elif _is_event_node(obj):
            yield obj
        else:
            for v in obj.values():
                yield from _walk_graph(v)
    elif isinstance(obj, list):
        for x in obj:
            yield from _walk_graph(x)


def _parse_schema_date(value: Any) -> Optional[tuple[date, Optional[time]]]:
    if value is None:
        return None
    if isinstance(value, dict):
        if "@value" in value:
            return _parse_schema_date(value["@value"])
        if "startDate" in value:
            return _parse_schema_date(value["startDate"])
        return None
    s = str(value).strip()
    if not s:
        return None
    s_iso = s.replace("Z", "+00:00")
    try:
        if "T" in s_iso:
            dt = datetime.fromisoformat(s_iso)
            return dt.date(), dt.time().replace(microsecond=0)
        return datetime.strptime(s[:10], "%Y-%m-%d").date(), None
    except ValueError:
        return None


def extract_json_ld_events(html: str, page_url: str) -> List[EventCandidate]:
    soup = BeautifulSoup(html, "html.parser")
    out: List[EventCandidate] = []
    for tag in soup.find_all("script", attrs={"type": re.compile(r"ld\+json", re.I)}):
        raw = tag.string or tag.text or ""
        for obj in _iter_json_objects(raw):
            try:
                for ev in _walk_graph(obj):
                    if not isinstance(ev, dict):
                        continue
                    start = ev.get("startDate")
                    parsed = _parse_schema_date(start)
                    if not parsed:
                        continue
                    d, tm = parsed
                    name = ev.get("name") or ev.get("headline") or ""
                    if isinstance(name, dict):
                        name = name.get("@value") or ""
                    name = str(name).strip() or "Sin título"
                    loc = ev.get("location")
                    lugar = None
                    if isinstance(loc, dict):
                        lugar = loc.get("name")
                        if isinstance(lugar, dict):
                            lugar = lugar.get("@value")
                    desc = ev.get("description")
                    if isinstance(desc, dict):
                        desc = desc.get("@value")
                    img = ev.get("image")
                    if isinstance(img, list) and img:
                        img = img[0]
                    if isinstance(img, dict):
                        img = img.get("url")
                    offers = ev.get("offers")
                    es_gratis = None
                    if isinstance(offers, dict):
                        price = offers.get("price")
                        es_gratis = price in (0, "0", "0.0", None, "0.00")
                    url_ev = ev.get("url") or page_url
                    if isinstance(url_ev, list):
                        url_ev = url_ev[0] if url_ev else page_url
                    url_ev = urljoin(page_url, str(url_ev))
                    out.append(
                        EventCandidate(
                            url_origen=url_ev,
                            extractor="json_ld",
                            score_calidad=0.92,
                            fecha_inicio=d,
                            hora_inicio=tm,
                            titulo_cat=name,
                            titulo_es=name,
                            idioma_origen="ca",
                            desc_cat=str(desc)[:8000] if desc else None,
                            desc_es=str(desc)[:8000] if desc else None,
                            lugar_nombre=str(lugar).strip() if lugar else None,
                            imagen_url=str(img) if img else None,
                            es_gratuito=es_gratis,
                        )
                    )
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                logger.debug("json-ld skip: %s", e)
    return out
