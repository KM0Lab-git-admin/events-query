"""generar_imagenes_ia_faltantes.py — Backfill de portadas IA para eventos
que ya están en BD pero no tienen ninguna imagen.

Recorre los eventos ACTIVO sin fila en BINARIOS_STORAGE y, para cada uno,
ejecuta el mismo camino que el hook de la ingesta (_generar_imagen_si_falta):
genera con OpenAI Images API (gpt-image-1-mini por defecto) y persiste como
imagen principal (disco local o PUT a la API + IMAGENES_BLOB, según --target),
actualizando EVENTOS_MASTER.Imagen_Principal_URL.

USO
---
    python scripts/generar_imagenes_ia_faltantes.py                      # local
    python scripts/generar_imagenes_ia_faltantes.py --target railway     # UAT
    python scripts/generar_imagenes_ia_faltantes.py --poblacion "Malgrat de Mar"
    python scripts/generar_imagenes_ia_faltantes.py --limit 5 --dry-run

El tope de generadas por ejecución es IMAGE_GEN_MAX_POR_RUN (defecto 20);
--limit lo reduce. Coste estimado por imagen: ~$0,006 (low, 1536x1024).
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import httpx
import ingest_all as ia


def main() -> None:
    ap = argparse.ArgumentParser(description="Genera portadas IA para eventos sin imagen")
    ap.add_argument("--target", default="local", choices=["local", "railway"])
    ap.add_argument("--poblacion", default=None, help="Filtrar por población")
    ap.add_argument("--limit", type=int, default=None,
                    help="Tope de imágenes a generar (<= IMAGE_GEN_MAX_POR_RUN)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Solo lista los eventos candidatos, no genera")
    args = ap.parse_args()

    target = ia.resolve_ingest_target(args.target)
    conn = ia.get_connection(target)
    oai = ia.make_openai_client()
    http = httpx.Client(headers={"User-Agent": ia.HTTP_USER_AGENT},
                        timeout=ia.HTTP_TIMEOUT, follow_redirects=True)

    sql = """
        SELECT e.ID_Unico_Evento, e.Poblacion_Nombre, e.Titulo_CAT,
               e.Desc_Corta_CAT, e.Lugar_Nombre, e.CP_Evento,
               (SELECT c.Slug FROM EVENTO_CATEGORIAS ec
                  JOIN CATEGORIAS c ON c.ID_Categoria = ec.ID_Categoria
                 WHERE ec.ID_Unico_Evento = e.ID_Unico_Evento LIMIT 1) AS slug
        FROM EVENTOS_MASTER e
        WHERE e.Estado = 'ACTIVO'
          AND NOT EXISTS (SELECT 1 FROM BINARIOS_STORAGE b
                          WHERE b.ID_Unico_Evento = e.ID_Unico_Evento)
    """
    params: list = []
    if args.poblacion:
        sql += " AND e.Poblacion_Nombre = %s"
        params.append(args.poblacion)
    sql += " ORDER BY e.Poblacion_Nombre, e.Titulo_CAT"
    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    cap = min(args.limit, ia.IMAGE_GEN_MAX_POR_RUN) if args.limit else ia.IMAGE_GEN_MAX_POR_RUN
    print(f"Eventos sin imagen en {target.name}: {len(rows)} "
          f"(tope esta ejecución: {cap})")
    if args.dry_run:
        for r in rows:
            print(f"  [{r['Poblacion_Nombre']}] {r['Titulo_CAT'][:70]}")
        return
    if not rows:
        return

    generadas = 0
    for row in rows:
        if generadas >= cap:
            print(f"Tope alcanzado ({cap}); quedan {len(rows) - generadas} sin imagen")
            break
        ev = ia.MergedEvent(
            id_unico=row["ID_Unico_Evento"],
            poblacion=row["Poblacion_Nombre"] or "",
            cp=row.get("CP_Evento") or "",
            titulo=row["Titulo_CAT"] or row["ID_Unico_Evento"][:12],
            lugar=row.get("Lugar_Nombre") or "",
            descripcion_larga="",
            direccion_fisica="",
            organizador_nombre="",
            es_gratuito=1,
            precio_euros=None,
            link_inscripcion="",
        )
        ev.desc_corta = row.get("Desc_Corta_CAT") or ""
        ev.categoria_principal = row.get("slug") or ""

        antes = ia.COST.global_stats["imagenes_ia"]
        ia._generar_imagen_si_falta(conn, oai, http, ev, target)
        if ia.COST.global_stats["imagenes_ia"] == antes:
            print(f"  -- sin generar: {ev.titulo[:60]}")
            continue

        # Mismo UPDATE que hace persist_event tras el hook
        with conn.cursor() as cur:
            cur.execute("""SELECT URL_Almacenamiento_Nube FROM BINARIOS_STORAGE
                           WHERE ID_Unico_Evento=%s AND Es_Principal=1 LIMIT 1""",
                        (ev.id_unico,))
            r = cur.fetchone()
            if r:
                cur.execute("UPDATE EVENTOS_MASTER SET Imagen_Principal_URL=%s "
                            "WHERE ID_Unico_Evento=%s",
                            (r["URL_Almacenamiento_Nube"], ev.id_unico))
        conn.commit()
        generadas += 1
        print(f"  OK [{ev.poblacion}] {ev.titulo[:60]}")

    http.close()
    coste = generadas * ia._image_gen_precio_usd()
    print(f"\nGeneradas: {generadas} | Coste estimado: ${coste:.4f} USD")
    conn.close()


if __name__ == "__main__":
    main()
