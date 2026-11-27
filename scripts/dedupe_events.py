"""
dedupe_events.py — Deduplicación y agrupación semántica de EVENTOS_MASTER.

El pipeline de ingesta deduplica por similitud de título (+ lugar/fechas), pero
distintas fuentes titulan el mismo evento de formas muy diferentes ("Campionat
de volei" vs "La Platja de l'Astillero acull el circuit de vòlei platja") y los
festivales generan piezas relacionadas que NO son duplicados sino actividades
de un mismo paraguas (Festival Libèl·lula y su taller de chapas). Este script
resuelve ambos casos sobre la BD ya poblada:

  - DUPLICADOS  -> FUSIÓN: gana el evento más rico (descripción más larga);
    se le traspasan horarios, fuentes, categorías e imágenes del perdedor y el
    perdedor se borra (BD + imágenes en disco/remoto).
  - RELACIONADOS -> FAMILIA: se elige cabeza (rango de fechas que engloba, o
    descripción más larga) y todos los miembros (incluida la cabeza) reciben
    su id en EVENTOS_MASTER.ID_Familia. No se pierde información.

CÓMO DECIDE
-----------
  1. Blocking barato: solo se comparan pares de la misma ciudad con rangos de
     fechas solapados (±2 días). Sin coste.
  2. Embeddings (text-embedding-3-small) de "título + inicio de descripción":
     similitud coseno + pequeños boosts deterministas (mismo lugar normalizado,
     mismo organizador, misma fecha de inicio).
  3. Bandas:
       score >= UMBRAL_DUP  (0.90) ............ DUPLICADO automático
       UMBRAL_GRIS (0.78) <= score < DUP ...... juez LLM (gpt-4.1-mini):
                                                MISMO | MISMA_FAMILIA | DISTINTO
       score < UMBRAL_GRIS .................... distinto, no se toca

USO
---
    python scripts/dedupe_events.py --target local --dry-run   # informe, no toca BD
    python scripts/dedupe_events.py --target local             # aplica fusiones/familias
    python scripts/dedupe_events.py --target railway
    python scripts/dedupe_events.py --umbral-dup 0.92 --umbral-gris 0.80

Pensado para ejecutarse tras la ingesta (mismo cron). Idempotente: en una BD
ya deduplicada no encuentra pares y no hace nada.

NOTA (railway): las imágenes traspasadas de un evento borrado a su ganador se
re-suben al servidor en el siguiente `ingest_all.py --sync-images-only` (la
fila de BINARIOS_STORAGE ya apunta a la ruta nueva y sync la repara).

VARIABLES DE ENTORNO
--------------------
    OPENAI_API_KEY (+ las de BD según --target, como ingest_all)
    DEDUPE_UMBRAL_DUP (default 0.90), DEDUPE_UMBRAL_GRIS (default 0.78)
"""

import argparse
import json
import logging
import math
import os
import re
import shutil
import sys
from datetime import timedelta
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ingest_all import (  # noqa: E402
    IMAGES_DIR, LLM_MODEL, COST,
    resolve_ingest_target, get_connection, make_http_client, make_openai_client,
    normalize_place, normalize_title, strip_accents, _delete_event_images_remote,
    familia_id, deducir_paraguas_por_titulo,
)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("dedupe_events")

EMBED_MODEL = "text-embedding-3-small"
EMBED_PRICE_PER_M = 0.02  # USD / 1M tokens

UMBRAL_DUP = float(os.getenv("DEDUPE_UMBRAL_DUP", "0.90"))
UMBRAL_GRIS = float(os.getenv("DEDUPE_UMBRAL_GRIS", "0.78"))
# Pares que YA comparten familia: umbral mucho más bajo para mandarlos al juez
# (dos piezas del mismo festival pueden parecerse poco y aun así ser MISMO).
UMBRAL_GRIS_FAMILIA = float(os.getenv("DEDUPE_UMBRAL_GRIS_FAMILIA", "0.60"))
BLOCK_MARGEN_DIAS = 2     # margen al comparar solape de rangos de fechas
DESC_CHARS_EMBED = 600    # caracteres de descripción que entran al embedding

JUDGE_SCHEMA = {
    "name": "relacion_eventos", "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "relacion": {
                "type": "string", "enum": ["MISMO", "MISMA_FAMILIA", "DISTINTO"],
                "description": (
                    "MISMO: son el mismo evento publicado por fuentes distintas "
                    "(aunque el título varíe). "
                    "MISMA_FAMILIA: uno es una actividad/sesión/parte del otro, "
                    "o ambos son actividades del mismo evento paraguas "
                    "(p.ej. un festival y uno de sus talleres). "
                    "DISTINTO: eventos diferentes."
                ),
            },
            "motivo": {"type": "string", "description": "Justificación en una frase."},
        },
        "required": ["relacion", "motivo"],
        "additionalProperties": False,
    },
}


# ============================================================================
# CARGA Y BLOCKING
# ============================================================================

def load_eventos(conn, poblacion: str = None) -> list:
    sql = """
        SELECT em.ID_Unico_Evento AS id, em.ID_Ciudad, em.Poblacion_Nombre,
               em.Titulo_CAT, em.Desc_Larga_CAT, em.Lugar_Nombre,
               em.Organizador_Nombre, em.ID_Familia, em.Imagen_Principal_URL,
               MIN(h.Fecha_Inicio) AS fmin,
               MAX(COALESCE(h.Fecha_Fin, h.Fecha_Inicio)) AS fmax,
               COUNT(h.ID_Horario) AS n_horarios
        FROM EVENTOS_MASTER em
        LEFT JOIN EVENTO_HORARIOS h ON h.ID_Unico_Evento = em.ID_Unico_Evento
        WHERE em.Estado = 'ACTIVO'
    """
    params = []
    if poblacion:
        sql += " AND em.Poblacion_Nombre = %s"
        params.append(poblacion)
    sql += " GROUP BY em.ID_Unico_Evento"
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def asignar_familias_por_paraguas(destinos: list, eventos: list, dry_run: bool) -> int:
    """Pasada determinista PREVIA a los pares: agrupa por 'evento paraguas'.

    Detecta nombres de paraguas en los títulos ('Festival Libèl·lula: X' ->
    'Festival Libèl·lula') y asigna la misma familia a TODOS los eventos de la
    ciudad cuyo título contiene ese nombre. Esto cierra familias completas sin
    depender de que las actividades se parezcan entre sí ('Tast de circ' y
    'Fem un mural' no se parecen, pero ambas contienen el paraguas).

    El ID de familia es hash(poblacion|paraguas), idéntico al que asigna la
    ingesta vía LLM (campo evento_paraguas del enriquecimiento)."""
    # candidatos a paraguas por ciudad
    paraguas_por_ciudad = {}
    for e in eventos:
        p = deducir_paraguas_por_titulo(e["Titulo_CAT"] or "")
        if p:
            paraguas_por_ciudad.setdefault(e["ID_Ciudad"], {})[normalize_title(p)] = p

    asignados = 0
    for e in eventos:
        if e.get("ID_Familia"):
            continue
        titulo_norm = normalize_title(e["Titulo_CAT"] or "")
        for p_norm, p in paraguas_por_ciudad.get(e["ID_Ciudad"], {}).items():
            if p_norm and p_norm in titulo_norm:
                fam = familia_id(e["Poblacion_Nombre"], p)
                log.info(f"  FAMILIA por paraguas '{p}': {e['Titulo_CAT'][:55]}")
                if not dry_run:
                    for d in destinos:
                        with d["conn"].cursor() as cur:
                            cur.execute("UPDATE EVENTOS_MASTER SET ID_Familia=%s "
                                        "WHERE ID_Unico_Evento=%s", (fam, e["id"]))
                e["ID_Familia"] = fam
                asignados += 1
                break
    if asignados and not dry_run:
        for d in destinos:
            d["conn"].commit()
    if asignados:
        log.info(f"Familias por paraguas: {asignados} eventos asignados")
    return asignados


def rangos_solapan(a, b, margen_dias=BLOCK_MARGEN_DIAS) -> bool:
    """Solape de rangos de fechas con margen. Si alguno no tiene fechas, se
    deja pasar (mejor comparar de más que perder un duplicado)."""
    if not a["fmin"] or not b["fmin"]:
        return True
    m = timedelta(days=margen_dias)
    a_min, a_max = a["fmin"] - m, (a["fmax"] or a["fmin"]) + m
    b_min, b_max = b["fmin"], b["fmax"] or b["fmin"]
    return a_min <= b_max and b_min <= a_max


def generar_pares(eventos: list) -> list:
    """Pares candidatos: misma ciudad + fechas solapadas (±margen)."""
    pares = []
    por_ciudad = {}
    for e in eventos:
        por_ciudad.setdefault(e["ID_Ciudad"], []).append(e)
    for grupo in por_ciudad.values():
        for i in range(len(grupo)):
            for j in range(i + 1, len(grupo)):
                if rangos_solapan(grupo[i], grupo[j]):
                    pares.append((grupo[i], grupo[j]))
    return pares


# ============================================================================
# EMBEDDINGS + SCORE
# ============================================================================

def texto_embedding(e) -> str:
    desc = re.sub(r"\s+", " ", (e["Desc_Larga_CAT"] or ""))[:DESC_CHARS_EMBED]
    return f"{e['Titulo_CAT']}. {e['Lugar_Nombre'] or ''}. {desc}"


def calcular_embeddings(oai, eventos: list) -> dict:
    """Una sola llamada batch. Devuelve {id: vector} y el coste en tokens."""
    textos = [texto_embedding(e) for e in eventos]
    resp = oai.embeddings.create(model=EMBED_MODEL, input=textos)
    tokens = resp.usage.total_tokens if resp.usage else 0
    log.info(f"Embeddings: {len(textos)} textos, {tokens:,} tokens "
             f"(${tokens / 1_000_000 * EMBED_PRICE_PER_M:.4f})")
    return {e["id"]: d.embedding for e, d in zip(eventos, resp.data)}, tokens


def coseno(v1, v2) -> float:
    dot = sum(a * b for a, b in zip(v1, v2))
    n1 = math.sqrt(sum(a * a for a in v1))
    n2 = math.sqrt(sum(b * b for b in v2))
    return dot / (n1 * n2) if n1 and n2 else 0.0


def _norm_org(s) -> str:
    return re.sub(r"\s+", " ", strip_accents((s or "").lower())).strip()


def score_par(a, b, emb) -> float:
    s = coseno(emb[a["id"]], emb[b["id"]])
    la, lb = normalize_place(a["Lugar_Nombre"] or ""), normalize_place(b["Lugar_Nombre"] or "")
    if la and lb and la == lb and la != "sin lugar":
        s += 0.04
    oa, ob = _norm_org(a["Organizador_Nombre"]), _norm_org(b["Organizador_Nombre"])
    if oa and ob and oa == ob:
        s += 0.02
    if a["fmin"] and b["fmin"] and a["fmin"] == b["fmin"]:
        s += 0.02
    return min(s, 1.0)


# ============================================================================
# JUEZ LLM (zona gris)
# ============================================================================

def juzgar_par(oai, a, b, cost=None, modelo=None) -> dict:
    system = (
        "Decides la relación entre dos eventos municipales de la misma ciudad. "
        "MISMO: el mismo evento publicado por fuentes distintas, aunque el "
        "título o el nivel de detalle varíen. MISMA_FAMILIA: uno es una "
        "actividad, sesión o parte del programa del otro, o ambos cuelgan del "
        "mismo evento paraguas (festival, fira, ciclo). DISTINTO: no tienen "
        "relación directa. Fíjate en fechas, lugar y contenido, no solo en el título."
    )

    def ficha(e, n):
        return (f"EVENTO {n}\nTítulo: {e['Titulo_CAT']}\n"
                f"Fechas: {e['fmin']} a {e['fmax']}\n"
                f"Lugar: {e['Lugar_Nombre']}\nOrganizador: {e['Organizador_Nombre']}\n"
                f"Descripción: {(e['Desc_Larga_CAT'] or '')[:800]}")

    resp = oai.chat.completions.create(
        model=modelo or LLM_MODEL,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": ficha(a, 1) + "\n\n" + ficha(b, 2)}],
        response_format={"type": "json_schema", "json_schema": JUDGE_SCHEMA},
        temperature=0,
    )
    (cost or COST).add_llm(a["Poblacion_Nombre"], resp, op="dedupe_juez")
    return json.loads(resp.choices[0].message.content)


# ============================================================================
# ACCIONES: FUSIÓN Y FAMILIA
# ============================================================================

def elegir_ganador(a, b):
    """El evento más rico sobrevive: descripción más larga; a igualdad, más
    horarios; a igualdad, el más antiguo (id estable entre runs)."""
    ka = (len(a["Desc_Larga_CAT"] or ""), a["n_horarios"], a["id"])
    kb = (len(b["Desc_Larga_CAT"] or ""), b["n_horarios"], b["id"])
    return (a, b) if ka >= kb else (b, a)


def fusionar_eventos(conn, http, target, ganador, perdedor, dry_run) -> None:
    gid, pid = ganador["id"], perdedor["id"]
    log.info(f"  FUSIÓN: '{perdedor['Titulo_CAT'][:50]}' -> "
             f"'{ganador['Titulo_CAT'][:50]}'")
    if dry_run:
        return

    with conn.cursor() as cur:
        # Horarios: traspasar los que el ganador no tenga ya (mismo día+hora)
        cur.execute("""
            INSERT INTO EVENTO_HORARIOS
                (ID_Unico_Evento, Fecha_Inicio, Fecha_Fin, Hora_Inicio, Hora_Fin, Es_Recurrente)
            SELECT %s, h.Fecha_Inicio, h.Fecha_Fin, h.Hora_Inicio, h.Hora_Fin, h.Es_Recurrente
            FROM EVENTO_HORARIOS h
            WHERE h.ID_Unico_Evento = %s
              AND NOT EXISTS (
                SELECT 1 FROM EVENTO_HORARIOS g
                WHERE g.ID_Unico_Evento = %s
                  AND g.Fecha_Inicio = h.Fecha_Inicio
                  AND COALESCE(g.Hora_Inicio, '') = COALESCE(h.Hora_Inicio, '')
              )
        """, (gid, pid, gid))

        # Fuentes: traspasar con dedupe por (evento, URL_Origen)
        cur.execute("""
            INSERT INTO EVENTO_FUENTES
                (ID_Unico_Evento, ID_Fuente, URL_Origen, Es_Fuente_Principal, Aporto_Extraccion)
            SELECT %s, f.ID_Fuente, f.URL_Origen, 0, f.Aporto_Extraccion
            FROM EVENTO_FUENTES f WHERE f.ID_Unico_Evento = %s
            ON DUPLICATE KEY UPDATE Fecha_Ultima_Confirmacion = NOW()
        """, (gid, pid))

        # Categorías
        cur.execute("""
            INSERT IGNORE INTO EVENTO_CATEGORIAS (ID_Unico_Evento, ID_Categoria)
            SELECT %s, ID_Categoria FROM EVENTO_CATEGORIAS WHERE ID_Unico_Evento = %s
        """, (gid, pid))

        # Imágenes: re-apuntar filas al ganador (nunca como principal si ya tiene)
        cur.execute("SELECT COUNT(*) AS n FROM BINARIOS_STORAGE WHERE ID_Unico_Evento=%s", (gid,))
        ganador_tiene = cur.fetchone()["n"] > 0
        cur.execute("""
            SELECT ID_Binario, Nombre_Archivo, URL_Almacenamiento_Nube
            FROM BINARIOS_STORAGE WHERE ID_Unico_Evento = %s
        """, (pid,))
        binarios_perdedor = cur.fetchall()

    # Mover ficheros locales y re-apuntar filas
    for b in binarios_perdedor:
        nueva_url = (b["URL_Almacenamiento_Nube"] or "").replace(pid, gid)
        if target.store_images_locally:
            origen = IMAGES_DIR / pid / b["Nombre_Archivo"]
            destino_dir = IMAGES_DIR / gid
            destino = destino_dir / b["Nombre_Archivo"]
            if origen.exists() and not destino.exists():
                destino_dir.mkdir(parents=True, exist_ok=True)
                shutil.move(str(origen), str(destino))
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE BINARIOS_STORAGE
                SET ID_Unico_Evento=%s, URL_Almacenamiento_Nube=%s,
                    Es_Principal=IF(%s, 0, Es_Principal)
                WHERE ID_Binario=%s
            """, (gid, nueva_url, ganador_tiene, b["ID_Binario"]))

    with conn.cursor() as cur:
        # Heredar la familia del perdedor si el ganador no tenía
        if perdedor.get("ID_Familia") and not ganador.get("ID_Familia"):
            cur.execute("UPDATE EVENTOS_MASTER SET ID_Familia=%s WHERE ID_Unico_Evento=%s",
                        (perdedor["ID_Familia"], gid))
        # Borrar el perdedor (CASCADE limpia lo que quede)
        cur.execute("DELETE FROM EVENTOS_MASTER WHERE ID_Unico_Evento=%s", (pid,))
        # Imagen principal del ganador si le faltaba
        cur.execute("""
            SELECT URL_Almacenamiento_Nube FROM BINARIOS_STORAGE
            WHERE ID_Unico_Evento=%s ORDER BY Es_Principal DESC, Orden LIMIT 1
        """, (gid,))
        r = cur.fetchone()
        if r:
            cur.execute("""
                UPDATE EVENTOS_MASTER SET Imagen_Principal_URL=%s
                WHERE ID_Unico_Evento=%s AND (Imagen_Principal_URL IS NULL
                                              OR Imagen_Principal_URL LIKE %s)
            """, (r["URL_Almacenamiento_Nube"], gid, f"%{pid}%"))

    # Limpieza de imágenes del perdedor
    if target.store_images_locally:
        pdir = IMAGES_DIR / pid
        if pdir.exists():
            shutil.rmtree(pdir, ignore_errors=True)
    else:
        try:
            _delete_event_images_remote(http, target, pid)
        except httpx.HTTPError as exc:
            log.warning(f"  No se pudieron borrar imágenes remotas de {pid}: {exc}")

    conn.commit()


def elegir_cabeza_familia(a, b):
    """Cabeza = el que engloba al otro en fechas; si no, descripción más larga."""
    if a["fmin"] and b["fmin"]:
        a_rango = (a["fmin"], a["fmax"] or a["fmin"])
        b_rango = (b["fmin"], b["fmax"] or b["fmin"])
        if a_rango[0] <= b_rango[0] and a_rango[1] >= b_rango[1] and a_rango != b_rango:
            return a, b
        if b_rango[0] <= a_rango[0] and b_rango[1] >= a_rango[1] and a_rango != b_rango:
            return b, a
    return elegir_ganador(a, b)


def agrupar_familia(destinos: list, a, b, dry_run) -> str:
    """Asigna ID_Familia a ambos eventos en todos los destinos. Si alguno ya
    tiene familia, se reusa (las familias se transitivizan solas entre pares)."""
    cabeza, miembro = elegir_cabeza_familia(a, b)
    familia = a.get("ID_Familia") or b.get("ID_Familia") or cabeza["id"]
    log.info(f"  FAMILIA [{familia[:12]}…]: '{cabeza['Titulo_CAT'][:45]}' (cabeza) "
             f"+ '{miembro['Titulo_CAT'][:45]}'")
    if not dry_run:
        for d in destinos:
            with d["conn"].cursor() as cur:
                cur.execute("UPDATE EVENTOS_MASTER SET ID_Familia=%s "
                            "WHERE ID_Unico_Evento IN (%s, %s)",
                            (familia, a["id"], b["id"]))
            d["conn"].commit()
    # reflejar en memoria para la transitividad dentro del mismo run
    a["ID_Familia"] = familia
    b["ID_Familia"] = familia
    return familia


# ============================================================================
# MAIN
# ============================================================================

def dedupe_poblacion(oai, http, destinos: list, poblacion: str = None,
                     dry_run: bool = False, umbral_dup: float = None,
                     umbral_gris: float = None, cost=None, modelo=None) -> tuple:
    """Núcleo de deduplicación, invocable desde ingest_all tras cada población.

    destinos = [{"conn": ..., "target": IngestTarget}, ...]: el ANÁLISIS
    (carga de eventos, embeddings, juez LLM) se hace UNA sola vez sobre el
    primer destino (primario); las ACCIONES (fusión, familia) se aplican en
    todos. Funciona porque los IDs de evento son hashes deterministas,
    idénticos en todas las BDs.

    Devuelve (n_fusiones, n_familias)."""
    umbral_dup = umbral_dup if umbral_dup is not None else UMBRAL_DUP
    umbral_gris = umbral_gris if umbral_gris is not None else UMBRAL_GRIS
    primario = destinos[0]["conn"]

    eventos = load_eventos(primario, poblacion)
    ambito = f" de {poblacion}" if poblacion else ""
    if len(eventos) < 2:
        return 0, 0
    log.info(f"  Dedupe{ambito}: {len(eventos)} eventos activos")

    # Pasada 0: familias por evento paraguas (determinista, sin coste)
    asignar_familias_por_paraguas(destinos, eventos, dry_run)

    pares = generar_pares(eventos)
    if not pares:
        return 0, 0
    log.info(f"  Pares candidatos (misma ciudad + fechas solapadas "
             f"±{BLOCK_MARGEN_DIAS}d): {len(pares)}")

    emb, emb_tokens = calcular_embeddings(oai, eventos)
    if cost is not None and hasattr(cost, "add_embedding"):
        cost.add_embedding(poblacion or "(global)", emb_tokens)

    borrados = set()
    n_fusion = n_familia = n_distinto = n_juez = 0
    for a, b in sorted(pares, key=lambda p: -score_par(p[0], p[1], emb)):
        if a["id"] in borrados or b["id"] in borrados:
            continue
        s = score_par(a, b, emb)
        # Dentro de la misma familia el umbral del juez baja: dos piezas del
        # mismo festival pueden parecerse poco y aun así ser el MISMO evento
        # (las dos notas del "festival entero" desde webs distintas).
        misma_familia = bool(a.get("ID_Familia")) and a["ID_Familia"] == b.get("ID_Familia")
        gris_efectivo = UMBRAL_GRIS_FAMILIA if misma_familia else umbral_gris
        if s < gris_efectivo:
            n_distinto += 1
            continue

        if s >= umbral_dup:
            relacion = "MISMO"
            log.info(f"  score {s:.3f} (auto) — '{a['Titulo_CAT'][:40]}' vs "
                     f"'{b['Titulo_CAT'][:40]}'")
        else:
            veredicto = juzgar_par(oai, a, b, cost, modelo)
            n_juez += 1
            relacion = veredicto["relacion"]
            log.info(f"  score {s:.3f} (juez: {relacion}) — '{a['Titulo_CAT'][:40]}' vs "
                     f"'{b['Titulo_CAT'][:40]}' · {veredicto['motivo'][:80]}")

        if relacion == "MISMO":
            ganador, perdedor = elegir_ganador(a, b)
            for d in destinos:
                fusionar_eventos(d["conn"], http, d["target"], ganador,
                                 perdedor, dry_run)
            borrados.add(perdedor["id"])
            n_fusion += 1
        elif relacion == "MISMA_FAMILIA":
            agrupar_familia(destinos, a, b, dry_run)
            n_familia += 1
        else:
            n_distinto += 1

    log.info(f"  Dedupe{ambito}: {n_fusion} fusiones · {n_familia} familias · "
             f"{n_distinto} descartados · {n_juez} juzgados por LLM")
    return n_fusion, n_familia


def run(target_name: str, dry_run: bool, umbral_dup: float, umbral_gris: float):
    """Ejecución standalone del deduplicador (toda la BD de un destino)."""
    if not os.getenv("OPENAI_API_KEY"):
        sys.exit("Falta OPENAI_API_KEY en .env")
    if umbral_gris >= umbral_dup:
        sys.exit("--umbral-gris debe ser menor que --umbral-dup")

    target = resolve_ingest_target(target_name)
    oai = make_openai_client()
    http = make_http_client()
    conn = get_connection(target)
    destinos = [{"conn": conn, "target": target}]

    try:
        n_fusion, n_familia = dedupe_poblacion(oai, http, destinos, None,
                                               dry_run, umbral_dup, umbral_gris)
        log.info("=" * 64)
        log.info(f"RESULTADO: {n_fusion} fusiones · {n_familia} agrupaciones de familia")
        if dry_run:
            log.info("(dry-run: no se ha tocado la BD; las fusiones/familias son simulación)")
        COST.report()
    finally:
        http.close()
        conn.close()


def main():
    ap = argparse.ArgumentParser(
        description="Deduplica y agrupa eventos de EVENTOS_MASTER (embeddings + juez LLM).")
    ap.add_argument("--target", choices=("local", "railway"), default="local")
    ap.add_argument("--dry-run", action="store_true",
                    help="Solo informa: no fusiona ni agrupa (SÍ gasta embeddings/juez)")
    ap.add_argument("--umbral-dup", type=float, default=UMBRAL_DUP,
                    help=f"Score >= esto = duplicado automático (default {UMBRAL_DUP})")
    ap.add_argument("--umbral-gris", type=float, default=UMBRAL_GRIS,
                    help=f"Score >= esto pasa al juez LLM (default {UMBRAL_GRIS})")
    args = ap.parse_args()
    run(args.target, args.dry_run, args.umbral_dup, args.umbral_gris)


if __name__ == "__main__":
    main()
