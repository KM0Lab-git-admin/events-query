"""CLI: ingestión genérica por URL → EVENTOS_MASTER."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from pymysql.err import OperationalError

from app.config import settings
from app.ingestion.pipeline import run_ingestion_url
from app.services.database import DatabaseService


def _mysql_help() -> str:
    return (
        f"No se pudo conectar a MySQL en {settings.db_host}:{settings.db_port}.\n"
        "Comprueba:\n"
        "  • Que el servicio MySQL está en ejecución (local o Docker).\n"
        "  • Con Docker Compose en este repo:  docker compose up -d mysql\n"
        "    (el puerto 3306 debe mapearse a localhost; .env con DB_HOST=127.0.0.1)\n"
        "  • Variables en .env: DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME.\n"
        "Para probar extracción sin BD:  --dry-run"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingesta eventos desde una URL (agenda HTML / iCal / JSON-LD) hacia EVENTOS_MASTER."
    )
    parser.add_argument("--url", required=True, help="URL del listado o .ics")
    parser.add_argument("--cp", default="08380", help="Código postal (FK CODIGOS_POSTALES)")
    parser.add_argument("--ciudad-id", type=int, default=1, dest="ciudad_id")
    parser.add_argument(
        "--poblacion",
        default="Malgrat de Mar",
        help="Nombre población (catalogo / EVENTOS_MASTER.Poblacion_Nombre)",
    )
    parser.add_argument("--lat", type=float, default=41.6465)
    parser.add_argument("--lng", type=float, default=2.7416)
    parser.add_argument(
        "--include-past",
        action="store_true",
        help="No filtrar eventos con fecha de inicio pasada",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Solo descarga y extracción; no escribe en la base de datos",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    db = DatabaseService()

    async def _run():
        res = await run_ingestion_url(
            db,
            args.url,
            id_ciudad=args.ciudad_id,
            cp=args.cp,
            poblacion_nombre=args.poblacion,
            lat=args.lat,
            lng=args.lng,
            drop_past_events=not args.include_past,
            dry_run=args.dry_run,
        )
        print(
            f"OK: candidatos brutos={res.candidates_raw} "
            f"tras gate={res.candidates_after_gate} "
            f"persistidos={res.persisted}"
        )
        if args.dry_run and res.merged_preview:
            print("\nVista previa (dry-run, primeros 15):")
            for i, ev in enumerate(res.merged_preview[:15], 1):
                tit = ev.titulo_cat if len(ev.titulo_cat) <= 60 else ev.titulo_cat[:57] + "…"
                print(f"  {i}. {ev.fecha_inicio} {ev.hora_inicio or ''} | {tit} | {ev.cp_evento}")

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        sys.exit(130)
    except OperationalError as e:
        print(_mysql_help(), file=sys.stderr)
        print(f"\nDetalle: {e}", file=sys.stderr)
        sys.exit(1)
    except OSError as e:
        print(f"ERROR de red o BD: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
