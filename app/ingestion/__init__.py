"""
Módulo de ingesta: pipeline genérico URL → EVENTOS_MASTER (7 capas).

Uso: python -m app.ingestion.cli --url https://ejemplo.cat/agenda --cp 08380
"""

from app.ingestion.pipeline import run_ingestion_url
