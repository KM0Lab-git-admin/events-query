"""
enrich_phase_b.py — Enriquecimiento semántico de eventos con LLM y embeddings.

Fase B del módulo de ingesta KM0_Events. Toma un CSV producido por la Fase A
(extracción) y lo enriquece añadiendo:

  - Traducción del título y descripción al castellano (idioma origen es catalán).
  - Tags semánticos en catalán y castellano (5-10 conceptos cada idioma).
  - Categorías asignadas del catálogo cerrado (con jerarquía padre/subcategoría).
  - Embeddings vectoriales por idioma (text-embedding-3-small, 1536 dims).

Catálogo de categorías (jerárquico):

    musica (Música)
    cultura (Cultura)
        cine, teatro, exposiciones, charlas, lectura
    infantil (Infantil)
    deporte (Deporte)
    talleres (Talleres)
    fiestas (Fiestas)
        fiestas-mayores, ferias
    gastro (Gastro)

Regla de asignación: si una subcategoría encaja con el evento, se usa ella
(es más específica). Si ninguna subcategoría aplica, se usa el padre.

Idempotente: si un evento ya tiene columnas enriquecidas rellenadas, lo salta.

USO
---
    # Enriquecer un CSV nuevo (de Fase A):
    python enrich_phase_b.py --input out/malgrat_events.csv

    # Re-enriquecer SOLO las categorías de un CSV ya procesado
    # (conserva traducciones, tags y embeddings; ahorra coste):
    python enrich_phase_b.py --input out/malgrat_events_enriched.csv \\
                             --output out/malgrat_events_enriched.csv \\
                             --reset-categories

DEPENDENCIAS
------------
    pip install openai python-dotenv
"""

import argparse
import csv
import json
import logging
import os
import sys
from pathlib import Path

from openai import OpenAI

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ============================================================================
# CONFIGURACIÓN
# ============================================================================

LLM_MODEL = "gpt-4.1-mini"
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536


# ============================================================================
# CATÁLOGO DE CATEGORÍAS (debe coincidir con la tabla CATEGORIAS en BD)
# ============================================================================

# Definición plana: (codigo, nombre_es, nombre_ca, padre_codigo)
# padre_codigo = None → es un padre.
# padre_codigo = "xxx" → es subcategoría de "xxx".
CATEGORIES_FLAT = [
    # Padres
    ("musica",          "Música",          "Música",          None),
    ("cultura",         "Cultura",         "Cultura",         None),
    ("infantil",        "Infantil",        "Infantil",        None),
    ("deporte",         "Deporte",         "Esport",          None),
    ("talleres",        "Talleres",        "Tallers",         None),
    ("fiestas",         "Fiestas",         "Festes",          None),
    ("gastro",          "Gastro",          "Gastro",          None),
    # Subcategorías de Cultura
    ("cine",            "Cine",            "Cinema",          "cultura"),
    ("teatro",          "Teatro",          "Teatre",          "cultura"),
    ("exposiciones",    "Exposiciones",    "Exposicions",     "cultura"),
    ("charlas",         "Charlas",         "Xerrades",        "cultura"),
    ("lectura",         "Lectura",         "Lectura",         "cultura"),
    # Subcategorías de Fiestas
    ("fiestas-mayores", "Fiestas mayores", "Festes majors",   "fiestas"),
    ("ferias",          "Ferias",          "Fires",           "fiestas"),
]

ALL_CATEGORY_CODES = [c[0] for c in CATEGORIES_FLAT]
PARENT_CODES = {c[0] for c in CATEGORIES_FLAT if c[3] is None}
SUBCATEGORY_TO_PARENT = {c[0]: c[3] for c in CATEGORIES_FLAT if c[3] is not None}


def _build_catalog_description() -> str:
    """Construye una descripción legible del catálogo para meter en el prompt."""
    lines = []
    for codigo, nombre_es, nombre_ca, padre in CATEGORIES_FLAT:
        if padre is None:
            subs = [c[0] for c in CATEGORIES_FLAT if c[3] == codigo]
            if subs:
                lines.append(f"  - {codigo} ({nombre_es}) → subcategorías: {', '.join(subs)}")
            else:
                lines.append(f"  - {codigo} ({nombre_es}) → sin subcategorías")
    return "\n".join(lines)


CATALOG_DESCRIPTION = _build_catalog_description()


# ============================================================================
# LOGGING
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("enrich")


# ============================================================================
# COLUMNAS ENRIQUECIDAS
# ============================================================================

ENRICHED_COLUMNS = [
    "titulo_es",
    "desc_larga_es",
    "tags_ca",
    "tags_es",
    "categorias_codigos",
    "categoria_principal",
    "tags_embedding_ca",
    "tags_embedding_es",
]

# Subconjunto que se borra cuando se pasa --reset-categories
CATEGORY_COLUMNS = ["categorias_codigos", "categoria_principal"]


# ============================================================================
# LLM: SCHEMA DE ENRIQUECIMIENTO
# ============================================================================

ENRICHMENT_SCHEMA = {
    "name": "event_enrichment",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "titulo_es": {
                "type": "string",
                "description": (
                    "Traducción al castellano del título. Mantén nombres propios "
                    "sin traducir (p.ej. 'Millenium actress', 'Marimurtra'). "
                    "Si el original ya está en castellano, devuélvelo tal cual."
                ),
            },
            "desc_larga_es": {
                "type": "string",
                "description": (
                    "Traducción al castellano de la descripción larga. Si está "
                    "vacía, devuelve string vacío. Mantén nombres propios."
                ),
            },
            "tags_ca": {
                "type": "array",
                "description": (
                    "Entre 5 y 10 tags GENÉRICOS en catalán para categorización y "
                    "búsqueda. Reglas estrictas:\n"
                    "- Conceptos amplios que mucha gente buscaría: tipo de actividad, "
                    "público, ámbito cultural. Ejemplos buenos: 'cinema', 'animació', "
                    "'anime', 'infantil', 'literatura', 'familiar', 'teatre', "
                    "'comèdia', 'drama', 'arts escèniques'.\n"
                    "- PROHIBIDO incluir nombres propios DE NINGÚN TIPO: ni de "
                    "personas (autores, directores, actores, profesores), ni de "
                    "obras (libros, películas, espectáculos), ni de grupos/compañías, "
                    "ni de lugares (teatros, bibliotecas, equipamientos, ciudades).\n"
                    "- EJEMPLO NEGATIVO REAL: para un evento sobre la obra 'Pijames' "
                    "de Marc Camoletti interpretada por La Magnòlia Teatre en el "
                    "Centre Cultural, los tags CORRECTOS son: ['teatre', 'comèdia', "
                    "'drama', 'arts escèniques', 'espectacle', 'cultura', "
                    "'teatre amateur']. Los tags INCORRECTOS son: 'Marc Camoletti', "
                    "'La Magnòlia Teatre', 'Centre Cultural', 'Pijames'.\n"
                    "- Heurística: si el tag identifica este evento concreto en vez "
                    "de un tipo general de eventos, ES INCORRECTO."
                ),
                "items": {"type": "string"},
                "minItems": 5,
                "maxItems": 10,
            },
            "tags_es": {
                "type": "array",
                "description": (
                    "Los mismos tags en castellano, mismo orden y número que tags_ca."
                ),
                "items": {"type": "string"},
                "minItems": 5,
                "maxItems": 10,
            },
            "categorias_codigos": {
                "type": "array",
                "description": (
                    "Códigos de las categorías que mejor describen el evento. "
                    "Mínimo 1, máximo 3. Solo valores del catálogo. "
                    "REGLA: si una subcategoría encaja, úsala (es más específica). "
                    "Si ninguna subcategoría aplica, usa el padre. "
                    "NO mezcles padre y subcategoría del mismo árbol "
                    "(p.ej. nunca 'cultura' y 'cine' juntos)."
                ),
                "items": {"type": "string", "enum": ALL_CATEGORY_CODES},
                "minItems": 1,
                "maxItems": 3,
            },
            "categoria_principal": {
                "type": "string",
                "enum": ALL_CATEGORY_CODES,
                "description": (
                    "La categoría más representativa del evento. Debe estar "
                    "en categorias_codigos."
                ),
            },
        },
        "required": ["titulo_es", "desc_larga_es", "tags_ca", "tags_es",
                     "categorias_codigos", "categoria_principal"],
        "additionalProperties": False,
    },
}


SYSTEM_PROMPT = (
    "Eres un asistente que enriquece datos de eventos municipales catalanes. "
    "Recibes un evento extraído (en catalán) y devuelves su enriquecimiento "
    "semántico: traducción al castellano, tags conceptuales en ambos idiomas, "
    "y asignación a categorías de un catálogo cerrado con jerarquía.\n\n"
    "CATÁLOGO DE CATEGORÍAS:\n"
    f"{CATALOG_DESCRIPTION}\n\n"
    "REGLAS:\n"
    "(1) Traduce con naturalidad, no literalmente. Mantén nombres propios.\n"
    "(2) TAGS GENÉRICOS, no específicos. Son para que cualquier persona "
    "pueda filtrar/buscar eventos por tipo. PROHIBIDO incluir como tag "
    "nombres propios (personas, obras, autores), nombres de lugares "
    "(equipamientos, municipios), o palabras-acción del título individual. "
    "Piensa en categorías amplias: 'cine', 'literatura', 'familiar', "
    "'animació', no 'Satoshi Kon' ni 'Centre Cultural'.\n"
    "(3) Para categorías: si una subcategoría encaja con el evento, úsala "
    "(es más específica). Si ninguna subcategoría del árbol aplica, usa "
    "el padre. NO mezcles padre con subcategoría suya en el mismo evento "
    "(p.ej. nunca 'cultura' y 'cine' juntos: o cine, o cultura).\n"
    "(4) Si el evento no encaja bien en ninguna categoría específica, "
    "asigna 'cultura' como default genérico."
)


# ============================================================================
# ACUMULADOR DE USO
# ============================================================================

_usage = {
    "llm_calls": 0,
    "llm_prompt_tokens": 0,
    "llm_completion_tokens": 0,
    "embedding_calls": 0,
    "embedding_tokens": 0,
}


def _log_llm_usage(response):
    if hasattr(response, "usage") and response.usage:
        _usage["llm_prompt_tokens"] += response.usage.prompt_tokens
        _usage["llm_completion_tokens"] += response.usage.completion_tokens
        _usage["llm_calls"] += 1


def _log_embedding_usage(response):
    if hasattr(response, "usage") and response.usage:
        _usage["embedding_tokens"] += response.usage.total_tokens
        _usage["embedding_calls"] += 1


PRICE_LLM_INPUT_PER_M = 0.40
PRICE_LLM_OUTPUT_PER_M = 1.60
PRICE_EMBEDDING_PER_M = 0.02


def estimate_cost_usd() -> float:
    llm = (
        _usage["llm_prompt_tokens"] / 1_000_000 * PRICE_LLM_INPUT_PER_M +
        _usage["llm_completion_tokens"] / 1_000_000 * PRICE_LLM_OUTPUT_PER_M
    )
    emb = _usage["embedding_tokens"] / 1_000_000 * PRICE_EMBEDDING_PER_M
    return llm + emb


# ============================================================================
# ENRIQUECIMIENTO SEMÁNTICO (LLM)
# ============================================================================

def enrich_event(row: dict, oai: OpenAI) -> dict:
    """Llama al LLM con los datos del evento y devuelve los campos enriquecidos."""
    user_prompt = (
        f"TÍTULO (catalán): {row.get('titulo', '')}\n"
        f"DESCRIPCIÓN LARGA (catalán):\n{row.get('descripcion_larga', '')}\n"
        f"LUGAR: {row.get('lugar_nombre', '')}\n"
        f"ORGANIZADOR: {row.get('organizador_nombre', '')}"
    )

    response = oai.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_schema", "json_schema": ENRICHMENT_SCHEMA},
        temperature=0,
    )
    _log_llm_usage(response)

    enriched = json.loads(response.choices[0].message.content)

    # Validaciones defensivas:
    # (a) categoria_principal debe estar en categorias_codigos
    if enriched["categoria_principal"] not in enriched["categorias_codigos"]:
        enriched["categorias_codigos"] = (
            [enriched["categoria_principal"]] + enriched["categorias_codigos"]
        )

    # (b) Si el LLM puso padre Y subcategoría del mismo árbol, nos quedamos
    # con la subcategoría (más específica)
    cats = list(enriched["categorias_codigos"])
    subs_present = {c for c in cats if c in SUBCATEGORY_TO_PARENT}
    parents_to_remove = {SUBCATEGORY_TO_PARENT[s] for s in subs_present}
    cleaned = [c for c in cats if c not in parents_to_remove]
    if not cleaned:
        cleaned = cats  # fallback paranoia
    enriched["categorias_codigos"] = cleaned

    # Si categoria_principal era un padre que hemos eliminado, sustituirla
    # por la subcategoría correspondiente
    if enriched["categoria_principal"] in parents_to_remove:
        for sub in subs_present:
            if SUBCATEGORY_TO_PARENT[sub] == enriched["categoria_principal"]:
                enriched["categoria_principal"] = sub
                break

    return enriched


# ============================================================================
# EMBEDDINGS
# ============================================================================

def build_embedding_text(titulo: str, tags: list, desc: str) -> str:
    first_sentence = (desc.split(".")[0] if desc else "").strip()
    tags_str = ", ".join(tags) if tags else ""
    parts = [titulo, tags_str, first_sentence]
    return ". ".join(p for p in parts if p)


def embed_text(text: str, oai: OpenAI) -> list:
    response = oai.embeddings.create(model=EMBEDDING_MODEL, input=text)
    _log_embedding_usage(response)
    return response.data[0].embedding


# ============================================================================
# IDEMPOTENCIA
# ============================================================================

def is_already_enriched(row: dict) -> bool:
    """Una fila está enriquecida semánticamente si tiene traducción, tags y
    categorías. Embeddings se comprueban aparte."""
    return all([
        row.get("titulo_es"),
        row.get("tags_ca"),
        row.get("categorias_codigos"),
    ])


def has_embeddings(row: dict) -> bool:
    return all([
        row.get("tags_embedding_ca"),
        row.get("tags_embedding_es"),
    ])


# ============================================================================
# PIPELINE PRINCIPAL
# ============================================================================

def process_csv(input_path: Path, output_path: Path, reset_categories: bool) -> None:
    if not os.getenv("OPENAI_API_KEY"):
        sys.exit("Falta OPENAI_API_KEY (en .env o en variables de entorno).")
    if not input_path.exists():
        sys.exit(f"CSV de entrada no encontrado: {input_path}")

    oai = OpenAI()

    with input_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        input_fieldnames = reader.fieldnames or []
        rows = list(reader)

    log.info(f"Leídas {len(rows)} filas de {input_path}")

    # Si --reset-categories: vaciar SOLO esas dos columnas para forzar
    # re-categorización. Las traducciones, tags y embeddings se conservan.
    # PERO la idempotencia normal vuelve a llamar al LLM completo si falta
    # alguna columna semántica. Lo aceptamos: re-pagar traducción es un coste
    # despreciable (~$0.005 para 9 eventos), y mantiene el código simple.
    if reset_categories:
        log.info("--reset-categories: vaciando columnas de categoría")
        for row in rows:
            for col in CATEGORY_COLUMNS:
                row[col] = ""

    # Fieldnames de salida: input + enriquecidas (sin duplicar)
    output_fieldnames = list(input_fieldnames)
    for col in ENRICHED_COLUMNS:
        if col not in output_fieldnames:
            output_fieldnames.append(col)

    for row in rows:
        for col in ENRICHED_COLUMNS:
            row.setdefault(col, "")

    enriched_count = 0
    skipped_count = 0
    error_count = 0

    for i, row in enumerate(rows, 1):
        titulo_short = (row.get("titulo") or "")[:70]
        log.info(f"[{i}/{len(rows)}] {titulo_short}")

        # PASO 1: enriquecimiento semántico
        if is_already_enriched(row):
            log.info("  ya enriquecido, saltando enriquecimiento semántico")
            skipped_count += 1
        else:
            try:
                enriched = enrich_event(row, oai)
                row["titulo_es"] = enriched["titulo_es"]
                row["desc_larga_es"] = enriched["desc_larga_es"]
                row["tags_ca"] = json.dumps(enriched["tags_ca"], ensure_ascii=False)
                row["tags_es"] = json.dumps(enriched["tags_es"], ensure_ascii=False)
                row["categorias_codigos"] = json.dumps(
                    enriched["categorias_codigos"], ensure_ascii=False
                )
                row["categoria_principal"] = enriched["categoria_principal"]
                enriched_count += 1
                log.info(
                    f"  enriquecido → cat principal: {enriched['categoria_principal']}, "
                    f"todas: {enriched['categorias_codigos']}, "
                    f"{len(enriched['tags_ca'])} tags"
                )
            except Exception as e:
                log.error(f"  ERROR enriquecimiento: {e}")
                error_count += 1
                continue

        # PASO 2: embeddings — DESACTIVADO en esta versión.
        # Decisión: poblamos la BD con datos estructurados primero. Los
        # embeddings se generarán más adelante en un script aparte, sobre
        # los eventos ya persistidos, cuando se necesite la búsqueda semántica.
        # Las columnas tags_embedding_ca y tags_embedding_es se quedan vacías.
        pass

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=output_fieldnames, quoting=csv.QUOTE_NONNUMERIC
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    log.info("=== Reporte ===")
    log.info(f"  Filas totales:              {len(rows)}")
    log.info(f"  Filas enriquecidas ahora:   {enriched_count}")
    log.info(f"  Filas ya enriquecidas:      {skipped_count}")
    log.info(f"  Filas con error:            {error_count}")
    log.info(f"  Llamadas LLM:               {_usage['llm_calls']}")
    log.info(f"  Llamadas embeddings:        {_usage['embedding_calls']}")
    log.info(f"  Tokens LLM input:           {_usage['llm_prompt_tokens']:,}")
    log.info(f"  Tokens LLM output:          {_usage['llm_completion_tokens']:,}")
    log.info(f"  Tokens embeddings:          {_usage['embedding_tokens']:,}")
    log.info(f"  Coste estimado:             ${estimate_cost_usd():.4f}")
    log.info(f"  CSV de salida:              {output_path}")


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Fase B — Enriquecimiento semántico (traducción + tags + "
            "categorías jerárquicas + embeddings) sobre un CSV de Fase A."
        )
    )
    parser.add_argument(
        "--input", required=True,
        help="CSV de entrada (producido por ingest_phase_a.py)",
    )
    parser.add_argument(
        "--output", default=None,
        help="CSV de salida. Default: añade '_enriched' al input.",
    )
    parser.add_argument(
        "--reset-categories", action="store_true",
        help=(
            "Vacía las columnas de categoría antes de procesar. "
            "Útil para re-categorizar un CSV ya enriquecido tras un cambio "
            "del catálogo. Traducciones, tags y embeddings se conservan."
        ),
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = input_path.with_name(input_path.stem + "_enriched.csv")

    process_csv(input_path, output_path, reset_categories=args.reset_categories)


if __name__ == "__main__":
    main()
