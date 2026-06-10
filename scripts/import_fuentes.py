"""
import_fuentes.py — Importa semillas JSON de fuentes a la BD (BIBLIOTECA_FUENTES
+ SCRAPING_TARGETS).

Las fuentes de scraping viven en la BD como fuente de verdad (el pipeline
ingest_all.py las lee de ahí cuando se ejecuta sin --input). Este script carga o
actualiza las semillas JSON por municipio, de forma IDEMPOTENTE: re-ejecutarlo
no duplica nada, solo actualiza prioridad/activa/tipo de contenido/notas.
Nunca borra fuentes (desactivación manual en BD si hace falta).

USO
---
    python scripts/import_fuentes.py --input scripts/fuentes/Malgrat.json
    python scripts/import_fuentes.py --input scripts/fuentes/Malgrat.json --target railway
    python scripts/import_fuentes.py --input scripts/fuentes/Blanes.json --dry-run

FORMATO DE LA SEMILLA
---------------------
    {
      "poblacion": "Malgrat de Mar",
      "codigos_postales": ["08380"],
      "fuentes": [
        {"tipo": "FUENTE_OFICIAL",        # FUENTE_OFICIAL | AGREGADOR | RED_SOCIAL_PERFIL | RED_SOCIAL_QUERY
         "nombre": "Agenda Ajuntament",   # informativo (va a Notas)
         "url": "https://...",            # URL_Base (clave de upsert junto a la ciudad)
         "prioridad": 1,                  # menor = más prioritario
         "tipo_contenido": "EVENTOS",     # EVENTOS | NOTICIAS | MIXTO (hint clasificador)
         "plataforma": "TELEGRAM",        # solo redes sociales
         "handle": "AjuntamentdeMalgrat", # solo redes sociales
         "activa": true,                  # false = registrada pero sin target (fase 2)
         "tipo_target": "WEB_DETALLE",    # opcional: fuerza el tipo de target
         "notas": "..."}                  # opcional
      ]
    }

REGLAS
------
  - Upsert de BIBLIOTECA_FUENTES por (ID_Ciudad, URL_Base).
  - Upsert de SCRAPING_TARGETS por UQ_TARGET_ORIGEN (Origen_Tabla, Origen_ID).
  - Tipo_Target deducido: SOCIAL_PERFIL para redes; WEB_DETALLE si la URL casa
    con patrones de página de detalle o se fuerza con "tipo_target";
    WEB_LISTADO en el resto.
  - Fuentes con "activa": false -> fila en BIBLIOTECA_FUENTES con Activa=0 y
    SIN target (quedan preparadas para la fase 2 sin gastar scraping).
  - La ciudad debe existir o se crea sin coordenadas (el pipeline la geocodifica
    en su primera ejecución si le faltan).
"""

import argparse
import json
import logging
import re
import sys
from pathlib import Path

# Reutiliza la resolución de credenciales/conexión del pipeline (mismo .env,
# mismos --target local|railway).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ingest_all import resolve_ingest_target, get_connection  # noqa: E402

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("import_fuentes")

TIPOS_FUENTE = {"FUENTE_OFICIAL", "AGREGADOR", "RED_SOCIAL_PERFIL", "RED_SOCIAL_QUERY"}
TIPOS_CONTENIDO = {"EVENTOS", "NOTICIAS", "MIXTO"}
PLATAFORMAS = {"INSTAGRAM", "FACEBOOK", "X_TWITTER", "TIKTOK", "YOUTUBE", "TELEGRAM"}
TIPOS_TARGET = {"WEB_LISTADO", "WEB_DETALLE", "WEB_SITEMAP", "API_AGREGADOR",
                "SOCIAL_PERFIL", "SOCIAL_QUERY"}

# Patrones de URL que son páginas de DETALLE de un evento concreto (no listados).
# Se registran como WEB_DETALLE: se extraen directamente sin pasar por listado.
DETALLE_URL_PATTERNS = [
    r"esdeveniments\.cat/e/",
    r"turismemaresme\.cat/.+/agenda/\d+/",
    r"firescatalanes\.cat/fires/",
    r"avui\.info/eventos/",
]


def deducir_tipo_target(fuente: dict) -> str:
    """Deducción del Tipo_Target a partir del tipo de fuente y la URL."""
    forzado = (fuente.get("tipo_target") or "").strip().upper()
    if forzado:
        if forzado not in TIPOS_TARGET:
            sys.exit(f"tipo_target inválido: {forzado!r} en {fuente.get('url')}")
        return forzado
    if fuente["tipo"] in ("RED_SOCIAL_PERFIL", "RED_SOCIAL_QUERY"):
        return "SOCIAL_PERFIL" if fuente["tipo"] == "RED_SOCIAL_PERFIL" else "SOCIAL_QUERY"
    url = fuente.get("url", "")
    for pat in DETALLE_URL_PATTERNS:
        if re.search(pat, url):
            return "WEB_DETALLE"
    return "WEB_LISTADO"


def validar_fuente(f: dict, idx: int):
    tipo = f.get("tipo")
    if tipo not in TIPOS_FUENTE:
        sys.exit(f"Fuente #{idx}: tipo inválido {tipo!r}")
    if not (f.get("url") or "").strip():
        sys.exit(f"Fuente #{idx}: falta url")
    tc = f.get("tipo_contenido", "MIXTO")
    if tc not in TIPOS_CONTENIDO:
        sys.exit(f"Fuente #{idx}: tipo_contenido inválido {tc!r}")
    plat = f.get("plataforma")
    if tipo.startswith("RED_SOCIAL"):
        if plat not in PLATAFORMAS:
            sys.exit(f"Fuente #{idx}: plataforma inválida {plat!r} para {tipo}")
    elif plat:
        sys.exit(f"Fuente #{idx}: plataforma solo aplica a redes sociales")


def ensure_ciudad_basica(conn, poblacion: str) -> int:
    """Busca la ciudad por nombre; si no existe la crea SIN coordenadas (el
    pipeline la geocodifica en su primera ejecución). No usa LLM aquí."""
    with conn.cursor() as cur:
        cur.execute("SELECT ID_Ciudad FROM CIUDADES WHERE Nombre=%s", (poblacion,))
        r = cur.fetchone()
        if r:
            return r["ID_Ciudad"]
        cur.execute("INSERT INTO CIUDADES (Nombre, Provincia) VALUES (%s, %s)",
                    (poblacion, "Girona"))
        log.warning(f"Ciudad creada sin coordenadas: {poblacion} "
                    f"(se geocodificará en la primera ingesta)")
        return cur.lastrowid


def ensure_cp_basico(conn, cp: str, id_ciudad: int):
    """Asegura el CP usando las coordenadas de la ciudad si existen; si la
    ciudad no tiene coords todavía, lo deja para la primera ingesta."""
    with conn.cursor() as cur:
        cur.execute("SELECT CP FROM CODIGOS_POSTALES WHERE CP=%s", (cp,))
        if cur.fetchone():
            return
        cur.execute("SELECT Latitud, Longitud FROM CIUDADES WHERE ID_Ciudad=%s", (id_ciudad,))
        c = cur.fetchone()
        if not c or c["Latitud"] is None:
            log.warning(f"CP {cp} no insertado (ciudad sin coordenadas aún); "
                        f"lo creará la primera ingesta")
            return
        cur.execute("INSERT INTO CODIGOS_POSTALES (CP, ID_Ciudad, Latitud, Longitud) "
                    "VALUES (%s,%s,%s,%s)", (cp, id_ciudad, c["Latitud"], c["Longitud"]))


def upsert_fuente(conn, id_ciudad: int, f: dict) -> tuple:
    """Upsert en BIBLIOTECA_FUENTES por (ID_Ciudad, URL_Base). Devuelve
    (id_fuente, creada: bool)."""
    url = f["url"].strip()
    activa = 1 if f.get("activa", True) else 0
    notas_partes = [p for p in (f.get("nombre"), f.get("notas")) if p]
    notas = " — ".join(notas_partes) or None
    with conn.cursor() as cur:
        cur.execute("SELECT ID_Fuente FROM BIBLIOTECA_FUENTES "
                    "WHERE ID_Ciudad=%s AND URL_Base=%s", (id_ciudad, url))
        r = cur.fetchone()
        if r:
            cur.execute("""UPDATE BIBLIOTECA_FUENTES
                SET Tipo_Fuente=%s, Tipo_Contenido=%s, Plataforma=%s, Handle=%s,
                    Activa=%s, Prioridad=%s, Notas=%s
                WHERE ID_Fuente=%s""",
                (f["tipo"], f.get("tipo_contenido", "MIXTO"), f.get("plataforma"),
                 f.get("handle"), activa, f.get("prioridad", 100), notas,
                 r["ID_Fuente"]))
            return r["ID_Fuente"], False
        cur.execute("""INSERT INTO BIBLIOTECA_FUENTES
            (ID_Ciudad, Tipo_Fuente, Tipo_Contenido, Plataforma, Handle,
             URL_Base, Activa, Prioridad, Notas)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (id_ciudad, f["tipo"], f.get("tipo_contenido", "MIXTO"),
             f.get("plataforma"), f.get("handle"), url, activa,
             f.get("prioridad", 100), notas))
        return cur.lastrowid, True


def upsert_target(conn, id_fuente: int, id_ciudad: int, f: dict) -> bool:
    """Upsert en SCRAPING_TARGETS por UQ_TARGET_ORIGEN. Devuelve True si creado."""
    url = f["url"].strip()
    tipo_target = deducir_tipo_target(f)
    origen_id = f"{id_fuente}:{url}"
    with conn.cursor() as cur:
        cur.execute("SELECT ID_Target FROM SCRAPING_TARGETS "
                    "WHERE Origen_Tabla=%s AND Origen_ID=%s",
                    ("BIBLIOTECA_FUENTES", origen_id))
        r = cur.fetchone()
        if r:
            cur.execute("""UPDATE SCRAPING_TARGETS
                SET Tipo_Target=%s, Plataforma=%s, URL_Target=%s
                WHERE ID_Target=%s""",
                (tipo_target, f.get("plataforma"), url, r["ID_Target"]))
            return False
        cur.execute("""INSERT INTO SCRAPING_TARGETS
            (ID_Fuente, ID_Ciudad, Tipo_Target, Plataforma, URL_Target,
             Origen_Tabla, Origen_ID, Estado)
            VALUES (%s,%s,%s,%s,%s,%s,%s,'PENDIENTE')""",
            (id_fuente, id_ciudad, tipo_target, f.get("plataforma"), url,
             "BIBLIOTECA_FUENTES", origen_id))
        return True


def importar(input_path: Path, target_name: str, dry_run: bool):
    if not input_path.exists():
        sys.exit(f"Semilla no encontrada: {input_path}")
    seed = json.loads(input_path.read_text(encoding="utf-8"))
    poblacion = (seed.get("poblacion") or "").strip()
    fuentes = seed.get("fuentes") or []
    if not poblacion or not fuentes:
        sys.exit("La semilla necesita 'poblacion' y 'fuentes' no vacíos")
    for i, f in enumerate(fuentes):
        validar_fuente(f, i)

    ingest_target = resolve_ingest_target(target_name)
    conn = get_connection(ingest_target)
    creadas = actualizadas = targets_nuevos = sin_target = 0
    try:
        id_ciudad = ensure_ciudad_basica(conn, poblacion)
        for cp in seed.get("codigos_postales", []):
            ensure_cp_basico(conn, cp, id_ciudad)

        for f in fuentes:
            activa = f.get("activa", True)
            estado = "ACTIVA" if activa else "inactiva (fase 2)"
            if dry_run:
                log.info(f"[dry-run] {f['tipo']:<18} {deducir_tipo_target(f):<13} "
                         f"P{f.get('prioridad', 100)} {estado:<16} {f['url']}")
                continue
            id_fuente, creada = upsert_fuente(conn, id_ciudad, f)
            creadas += 1 if creada else 0
            actualizadas += 0 if creada else 1
            if activa:
                if upsert_target(conn, id_fuente, id_ciudad, f):
                    targets_nuevos += 1
            else:
                sin_target += 1
            log.info(f"{'NUEVA' if creada else 'upd  '} fuente #{id_fuente} "
                     f"{f['tipo']:<18} {estado:<16} {f['url']}")

        if dry_run:
            conn.rollback()
            log.info("(dry-run: ningún cambio escrito)")
        else:
            conn.commit()
            log.info("=" * 60)
            log.info(f"{poblacion}: {creadas} fuentes nuevas, {actualizadas} "
                     f"actualizadas, {targets_nuevos} targets nuevos, "
                     f"{sin_target} inactivas sin target (fase 2)")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser(description="Importa semillas JSON de fuentes a BD.")
    ap.add_argument("--input", required=True, help="JSON de semilla (un municipio)")
    ap.add_argument("--target", choices=("local", "railway"), default="local")
    ap.add_argument("--dry-run", action="store_true", help="Muestra qué haría sin escribir")
    args = ap.parse_args()
    importar(Path(args.input), args.target, args.dry_run)


if __name__ == "__main__":
    main()
