"""Heurísticas HTML genéricas (listados tipo agenda municipal)."""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, time
from typing import List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.ingestion.models import EventCandidate

logger = logging.getLogger(__name__)

# dd/mm/yyyy o dd/mm/yy; opcional hora HH:MM(h)
_RE_DATE = re.compile(
    r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b(?:\s+(\d{1,2}):(\d{2})(?:h)?)?",
    re.I,
)


def _parse_dm_y(
    m: re.Match,
) -> tuple[Optional[date], Optional[time]]:
    d, mo, y = int(m.group(1)), int(m.group(2)), m.group(3)
    yi = int(y)
    if yi < 100:
        yi += 2000
    try:
        day = date(yi, mo, d)
    except ValueError:
        return None, None
    if m.group(4) and m.group(5):
        try:
            return day, time(int(m.group(4)), int(m.group(5)))
        except ValueError:
            return day, None
    return day, None


def _nearest_heading(el) -> str:
    cur = el
    for _ in range(6):
        if cur is None:
            break
        for tag in ("h1", "h2", "h3", "h4"):
            h = cur.find_previous(tag)
            if h and h.get_text(strip=True):
                return h.get_text(strip=True)[:255]
        cur = getattr(cur, "parent", None)
    return ""


def extract_html_heuristic(html: str, page_url: str) -> List[EventCandidate]:
    """
    Busca elementos <time datetime="..."> y títulos cercanos;
    complementa con regex de fecha en texto (estilo EU).
    """
    soup = BeautifulSoup(html, "html.parser")
    seen: set[tuple[str, date, Optional[time]]] = set()
    out: List[EventCandidate] = []

    for t in soup.find_all("time"):
        dattr = t.get("datetime")
        if not dattr:
            continue
        dattr = str(dattr).strip()
        day: Optional[date] = None
        tm: Optional[time] = None
        try:
            if "T" in dattr:
                dt = datetime.fromisoformat(dattr.replace("Z", "+00:00"))
                day, tm = dt.date(), dt.time().replace(microsecond=0)
            else:
                day = datetime.strptime(dattr[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        title = _nearest_heading(t) or t.get_text(strip=True) or "Sin título"
        loc = None
        p = t.parent
        if p:
            block = p.get_text(" ", strip=True)
            if block and len(block) < 400:
                parts = [x.strip() for x in block.split(title) if x.strip()]
                if parts:
                    loc = parts[-1][:255]
        key = (title[:120], day, tm)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            EventCandidate(
                url_origen=page_url,
                extractor="html_time",
                score_calidad=0.72,
                fecha_inicio=day,
                hora_inicio=tm,
                titulo_cat=title,
                titulo_es=title,
                idioma_origen="ca",
                lugar_nombre=loc,
            )
        )

    if out:
        return out

    # Fallback: bloques con fecha en texto
    for block in soup.find_all(["article", "li", "div"]):
        cls = " ".join(block.get("class", [])).lower()
        if "event" not in cls and "agenda" not in cls and "list" not in cls:
            if block.name != "li":
                continue
        text = block.get_text(" ", strip=True)
        if not text or len(text) > 1200:
            continue
        for m in _RE_DATE.finditer(text):
            parsed = _parse_dm_y(m)
            if not parsed[0]:
                continue
            day, tm = parsed
            title = ""
            h = block.find(["h2", "h3", "h4", "a"])
            if h:
                title = h.get_text(strip=True)[:255]
            if not title:
                title = text[:80]
            key = (title[:120], day, tm)
            if key in seen:
                continue
            seen.add(key)
            link = block.find("a", href=True)
            url_ev = urljoin(page_url, link["href"]) if link else page_url
            out.append(
                EventCandidate(
                    url_origen=url_ev,
                    extractor="html_regex",
                    score_calidad=0.6,
                    fecha_inicio=day,
                    hora_inicio=tm,
                    titulo_cat=title,
                    titulo_es=title,
                    idioma_origen="ca",
                )
            )
            break

    return out[:200]
