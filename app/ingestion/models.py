"""Modelos de datos entre capas (alineados con docs/INGESTION_DATA_MODEL.md)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from typing import Optional


@dataclass(slots=True)
class FetchedDocument:
    """Salida del conector (HTTP)."""

    url: str
    content_type: str
    body: bytes


@dataclass(slots=True)
class EventCandidate:
    """Candidato de evento tras extracción estructural."""

    url_origen: str
    extractor: str
    score_calidad: float
    fecha_inicio: date
    hora_inicio: Optional[time] = None
    hora_fin: Optional[time] = None
    titulo_cat: Optional[str] = None
    titulo_es: Optional[str] = None
    idioma_origen: str = "ca"
    desc_cat: Optional[str] = None
    desc_es: Optional[str] = None
    lugar_nombre: Optional[str] = None
    imagen_url: Optional[str] = None
    es_gratuito: Optional[bool] = None


@dataclass(slots=True)
class MergedEvent:
    """Listo para persistir en EVENTOS_MASTER + hijas."""

    id_unico_evento: str
    metodo_ingesta: str
    id_usuario_carga: str
    fuente_id: str
    fuente_url_original: str
    estado: str
    id_ciudad: Optional[int]
    cp_evento: str
    poblacion_nombre: str
    lugar_nombre: str
    idioma_origen: str
    titulo_cat: str
    titulo_es: str
    desc_cat: Optional[str]
    desc_es: Optional[str]
    fecha_inicio: date
    hora_inicio: Optional[time]
    es_gratuito: bool
    requiere_inscripcion: bool
    tags_es: list[str]
    tags_cat: list[str]


@dataclass(slots=True)
class IngestionContext:
    """Metadatos de ejecución (fuente ciudad/CP para el merger)."""

    id_fuente: int
    id_ciudad: int
    cp_default: str
    poblacion_nombre: str
