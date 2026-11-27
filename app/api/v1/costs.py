"""
Costs endpoints - Gasto de OpenAI por ejecución de la ingesta (INGESTA_RUNS +
INGESTA_COSTES). Alimenta la pestaña Costes del front: último run, desglose por
población y operación, e histórico.
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import ORJSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.services import db_service
from app.models.schemas import ErrorResponse

logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)

router = APIRouter()


def _row_to_run(row) -> Dict[str, Any]:
    return {
        "id_run": row[0],
        "inicio": row[1].isoformat() if row[1] else None,
        "fin": row[2].isoformat() if row[2] else None,
        "duracion_seg": int((row[2] - row[1]).total_seconds()) if row[1] and row[2] else None,
        "target": row[3],
        "modelo": row[4],
        "parametros": row[5],
        "llamadas": row[6],
        "tokens_in": row[7],
        "tokens_cached": row[8],
        "tokens_out": row[9],
        "coste_usd": float(row[10]) if row[10] is not None else 0.0,
        "imagenes": row[11],
        "eventos": row[12],
        "noticias": row[13],
        "targets_ok": row[14],
        "targets_skip": row[15],
        "targets_error": row[16],
    }


_SELECT_RUN = """
    SELECT ID_Run, Inicio, Fin, Target, Modelo, Parametros, Llamadas,
           Tokens_In, Tokens_Cached, Tokens_Out, Coste_USD,
           Imagenes, Eventos_Persistidos, Noticias_Persistidas,
           Targets_OK, Targets_Skip, Targets_Error
    FROM INGESTA_RUNS
"""


@router.get(
    "/costs/runs",
    response_class=ORJSONResponse,
    summary="List ingestion runs with cost",
    responses={
        200: {"description": "Runs retrieved successfully"},
        429: {"description": "Too many requests"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
@limiter.limit("100/minute")
async def list_runs(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> Dict[str, Any]:
    """Lista de ejecuciones de la ingesta, la más reciente primero."""
    try:
        async with db_service.get_connection() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("SELECT COUNT(*) FROM INGESTA_RUNS")
                total = (await cursor.fetchone())[0]
                await cursor.execute(
                    _SELECT_RUN + " ORDER BY Inicio DESC LIMIT %s OFFSET %s",
                    [limit, offset],
                )
                rows = await cursor.fetchall()
        return {"data": [_row_to_run(r) for r in rows], "total": total,
                "limit": limit, "offset": offset}
    except Exception as e:
        logger.error(f"Error listing runs: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Error retrieving runs")


@router.get(
    "/costs/runs/{run_id}",
    response_class=ORJSONResponse,
    summary="Run detail with breakdown by town and operation",
    responses={
        200: {"description": "Run retrieved successfully"},
        404: {"model": ErrorResponse, "description": "Run not found"},
        429: {"description": "Too many requests"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
@limiter.limit("100/minute")
async def get_run(request: Request, run_id: int) -> Dict[str, Any]:
    """Detalle de un run: totales + desglose por población y por operación."""
    try:
        async with db_service.get_connection() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(_SELECT_RUN + " WHERE ID_Run = %s", [run_id])
                row = await cursor.fetchone()
                if not row:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                        detail="Run not found")
                run = _row_to_run(row)

                await cursor.execute("""
                    SELECT Poblacion, SUM(Llamadas), SUM(Tokens_In),
                           SUM(Tokens_Cached), SUM(Tokens_Out), SUM(Coste_USD)
                    FROM INGESTA_COSTES WHERE ID_Run = %s
                    GROUP BY Poblacion ORDER BY SUM(Coste_USD) DESC
                """, [run_id])
                por_poblacion = [
                    {"poblacion": r[0], "llamadas": int(r[1]),
                     "tokens_in": int(r[2]), "tokens_cached": int(r[3]),
                     "tokens_out": int(r[4]), "coste_usd": float(r[5])}
                    for r in await cursor.fetchall()
                ]

                await cursor.execute("""
                    SELECT Operacion, SUM(Llamadas), SUM(Tokens_In),
                           SUM(Tokens_Cached), SUM(Tokens_Out), SUM(Coste_USD)
                    FROM INGESTA_COSTES WHERE ID_Run = %s
                    GROUP BY Operacion ORDER BY SUM(Coste_USD) DESC
                """, [run_id])
                por_operacion = [
                    {"operacion": r[0], "llamadas": int(r[1]),
                     "tokens_in": int(r[2]), "tokens_cached": int(r[3]),
                     "tokens_out": int(r[4]), "coste_usd": float(r[5])}
                    for r in await cursor.fetchall()
                ]

        run["por_poblacion"] = por_poblacion
        run["por_operacion"] = por_operacion
        return {"data": run}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting run {run_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Error retrieving run")


@router.get(
    "/costs/summary",
    response_class=ORJSONResponse,
    summary="Aggregated cost by day and by town over a period",
    responses={
        200: {"description": "Summary retrieved successfully"},
        429: {"description": "Too many requests"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
@limiter.limit("100/minute")
async def costs_summary(
    request: Request,
    dias: int = Query(30, ge=1, le=365, description="Periodo en días"),
) -> Dict[str, Any]:
    """Agregado del periodo: total, por día y por población."""
    try:
        async with db_service.get_connection() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("""
                    SELECT COUNT(*), COALESCE(SUM(Llamadas),0),
                           COALESCE(SUM(Tokens_In),0), COALESCE(SUM(Tokens_Cached),0),
                           COALESCE(SUM(Tokens_Out),0), COALESCE(SUM(Coste_USD),0),
                           COALESCE(SUM(Eventos_Persistidos),0),
                           COALESCE(SUM(Noticias_Persistidas),0)
                    FROM INGESTA_RUNS
                    WHERE Inicio >= DATE_SUB(NOW(), INTERVAL %s DAY)
                """, [dias])
                t = await cursor.fetchone()
                totales = {
                    "runs": int(t[0]), "llamadas": int(t[1]),
                    "tokens_in": int(t[2]), "tokens_cached": int(t[3]),
                    "tokens_out": int(t[4]), "coste_usd": float(t[5]),
                    "eventos": int(t[6]), "noticias": int(t[7]),
                }

                await cursor.execute("""
                    SELECT DATE(Inicio), COUNT(*), SUM(Coste_USD),
                           SUM(Eventos_Persistidos), SUM(Noticias_Persistidas)
                    FROM INGESTA_RUNS
                    WHERE Inicio >= DATE_SUB(NOW(), INTERVAL %s DAY)
                    GROUP BY DATE(Inicio) ORDER BY DATE(Inicio)
                """, [dias])
                por_dia = [
                    {"fecha": r[0].isoformat(), "runs": int(r[1]),
                     "coste_usd": float(r[2]), "eventos": int(r[3]),
                     "noticias": int(r[4])}
                    for r in await cursor.fetchall()
                ]

                await cursor.execute("""
                    SELECT c.Poblacion, SUM(c.Llamadas), SUM(c.Tokens_In),
                           SUM(c.Tokens_Cached), SUM(c.Tokens_Out), SUM(c.Coste_USD)
                    FROM INGESTA_COSTES c
                    JOIN INGESTA_RUNS r ON r.ID_Run = c.ID_Run
                    WHERE r.Inicio >= DATE_SUB(NOW(), INTERVAL %s DAY)
                    GROUP BY c.Poblacion ORDER BY SUM(c.Coste_USD) DESC
                """, [dias])
                por_poblacion = [
                    {"poblacion": r[0], "llamadas": int(r[1]),
                     "tokens_in": int(r[2]), "tokens_cached": int(r[3]),
                     "tokens_out": int(r[4]), "coste_usd": float(r[5])}
                    for r in await cursor.fetchall()
                ]

        return {"dias": dias, "totales": totales, "por_dia": por_dia,
                "por_poblacion": por_poblacion}
    except Exception as e:
        logger.error(f"Error getting costs summary: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Error retrieving costs summary")
