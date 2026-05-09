"""
Desplaza Fecha_Inicio y Fecha_Fin en EVENTO_HORARIOS hacia el futuro sin tocar
EVENTOS_MASTER. Ajusta regla.finalizacion.valor en Recurrencia_JSON para eventos
recurrentes.

Criterio de offset (local, date.today()):
  offset_days = max(0, (today - min(Fecha_Inicio)).days + 1)
Así el nuevo mínimo de Fecha_Inicio queda estrictamente posterior a hoy.

Uso (desde la raíz del repo, con .env cargado vía pydantic-settings):
  python scripts/shift_horarios_to_future.py
  python scripts/shift_horarios_to_future.py --dry-run

En entornos con datos reales, haz backup (mysqldump) antes de ejecutar.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import date, timedelta
from typing import Any, Dict, Optional, Tuple, Union

# Raíz del proyecto
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.database import DatabaseService  # noqa: E402


def _parse_json_column(raw: Union[None, str, bytes, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8")
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
    return None


def shift_finalizacion_in_recurrencia(
    data: Dict[str, Any], offset_days: int
) -> Optional[str]:
    """Devuelve JSON string actualizado o None si no hay cambio."""
    regla = data.get("regla")
    if not isinstance(regla, dict):
        return None
    fin = regla.get("finalizacion")
    if not isinstance(fin, dict):
        return None
    if fin.get("tipo") != "fecha":
        return None
    valor = fin.get("valor")
    if not valor or not isinstance(valor, str):
        return None
    try:
        d = date.fromisoformat(valor[:10])
    except ValueError:
        return None
    new_d = d + timedelta(days=offset_days)
    fin = dict(fin)
    fin["valor"] = new_d.isoformat()
    regla = dict(regla)
    regla["finalizacion"] = fin
    out = dict(data)
    out["regla"] = regla
    return json.dumps(out, ensure_ascii=False)


async def compute_offset(db: DatabaseService) -> Tuple[Optional[date], int]:
    rows = await db.execute_query(
        "SELECT MIN(Fecha_Inicio) AS min_f FROM EVENTO_HORARIOS"
    )
    if not rows or rows[0].get("min_f") is None:
        print("EVENTO_HORARIOS vacío: no hay nada que desplazar.")
        return None, 0
    min_start = rows[0]["min_f"]
    if hasattr(min_start, "date"):
        min_start = min_start.date()
    today = date.today()
    offset = max(0, (today - min_start).days + 1)
    return min_start, offset


async def update_recurrent_json(
    db: DatabaseService, offset_days: int, dry_run: bool
) -> int:
    if offset_days <= 0:
        return 0
    rows = await db.execute_query(
        """
        SELECT ID_Horario, Recurrencia_JSON
        FROM EVENTO_HORARIOS
        WHERE Es_Recurrente = 1 AND Recurrencia_JSON IS NOT NULL
        """
    )
    updated = 0
    for row in rows or []:
        hid = row["ID_Horario"]
        raw = row["Recurrencia_JSON"]
        data = _parse_json_column(raw)
        if not data:
            continue
        new_json = shift_finalizacion_in_recurrencia(data, offset_days)
        if new_json is None:
            continue
        if dry_run:
            print(f"  [dry-run] ID_Horario={hid}: actualizaría Recurrencia_JSON")
            updated += 1
            continue
        await db.execute_query(
            "UPDATE EVENTO_HORARIOS SET Recurrencia_JSON = %s WHERE ID_Horario = %s",
            (new_json, hid),
            fetch_all=False,
        )
        updated += 1
    return updated


async def count_horarios(db: DatabaseService) -> int:
    r = await db.execute_query(
        "SELECT COUNT(*) AS c FROM EVENTO_HORARIOS", fetch_one=True
    )
    return int(r[0]["c"]) if r else 0


async def main_async(dry_run: bool) -> int:
    db = DatabaseService()
    try:
        await db.connect()
        total = await count_horarios(db)
        if total == 0:
            print("No hay filas en EVENTO_HORARIOS.")
            return 0

        min_start, offset_days = await compute_offset(db)
        if min_start is None:
            return 0

        today = date.today()
        print("Desplazar horarios al futuro")
        print(f"  Fecha mínima actual Fecha_Inicio: {min_start}")
        print(f"  Hoy (date.today): {today}")
        print(f"  offset_days: {offset_days}")
        if offset_days == 0:
            print("Nada que hacer: las fechas ya están en el futuro respecto a la regla.")
            return 0

        if dry_run:
            print(f"[dry-run] Se actualizarían ~{total} filas de fechas (UPDATE masivo).")
        else:
            async with db.get_connection() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        """
                        UPDATE EVENTO_HORARIOS
                        SET
                          Fecha_Inicio = DATE_ADD(Fecha_Inicio, INTERVAL %s DAY),
                          Fecha_Fin = CASE
                            WHEN Fecha_Fin IS NULL THEN NULL
                            ELSE DATE_ADD(Fecha_Fin, INTERVAL %s DAY)
                          END
                        """,
                        (offset_days, offset_days),
                    )
                    fecha_updates = cursor.rowcount
            print(f"Filas actualizadas (fechas): {fecha_updates}")

        json_updates = await update_recurrent_json(db, offset_days, dry_run)
        if dry_run:
            print(f"[dry-run] Recurrencia_JSON a revisar/actualizar: {json_updates} filas candidatas.")
        else:
            print(f"Filas con Recurrencia_JSON ajustado (finalizacion fecha): {json_updates}")

        if not dry_run:
            r = await db.execute_query(
                "SELECT MIN(Fecha_Inicio) AS mn, MAX(Fecha_Inicio) AS mx "
                "FROM EVENTO_HORARIOS",
                fetch_one=True,
            )
            if r:
                print(f"Nuevo MIN(Fecha_Inicio): {r[0]['mn']}, MAX: {r[0]['mx']}")

        return 0
    finally:
        await db.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Desplaza fechas de EVENTO_HORARIOS al futuro (mismo offset para todas las filas)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Calcula offset y lista acciones sin ejecutar UPDATEs.",
    )
    args = parser.parse_args()
    rc = asyncio.run(main_async(dry_run=args.dry_run))
    raise SystemExit(rc)


if __name__ == "__main__":
    main()
