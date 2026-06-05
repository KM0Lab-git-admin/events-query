"""Capa Persister: escritura en MySQL (eventos + scraping targets)."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Tuple

from app.ingestion.models import IngestionContext, MergedEvent
from app.services.database import DatabaseService

logger = logging.getLogger(__name__)

ORIGIN_TABLE = "ingestion_cli"


async def ensure_geography(
    db: DatabaseService,
    *,
    id_ciudad: int,
    cp: str,
    nombre_ciudad: str,
    lat: float,
    lng: float,
) -> None:
    await db.execute_query(
        """
        INSERT INTO CIUDADES (ID_Ciudad, Nombre, Provincia, Latitud, Longitud)
        VALUES (%s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            Nombre = VALUES(Nombre),
            Latitud = VALUES(Latitud),
            Longitud = VALUES(Longitud)
        """,
        (id_ciudad, nombre_ciudad, "", lat, lng),
        fetch_one=False,
        fetch_all=False,
    )
    await db.execute_query(
        """
        INSERT INTO CODIGOS_POSTALES (CP, ID_Ciudad, Latitud, Longitud)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            ID_Ciudad = VALUES(ID_Ciudad),
            Latitud = VALUES(Latitud),
            Longitud = VALUES(Longitud)
        """,
        (cp, id_ciudad, lat, lng),
        fetch_one=False,
        fetch_all=False,
    )


async def get_or_create_fuente_target(
    db: DatabaseService,
    *,
    page_url: str,
    id_ciudad: int,
) -> Tuple[int, int]:
    url_base = page_url[:2048]
    rows = await db.execute_query(
        """
        SELECT ID_Fuente FROM BIBLIOTECA_FUENTES
        WHERE URL_Base = %s AND ID_Ciudad = %s
        LIMIT 1
        """,
        (url_base, id_ciudad),
        fetch_one=True,
    )
    if rows:
        id_fuente = int(rows[0]["ID_Fuente"])
    else:
        id_fuente = await db.execute_insert(
            """
            INSERT INTO BIBLIOTECA_FUENTES (
                ID_Ciudad, Tipo_Fuente, URL_Base, Activa, Prioridad
            ) VALUES (%s, 'FUENTE_OFICIAL', %s, 1, 10)
            """,
            (id_ciudad, url_base),
        )

    origin_id = hashlib.sha256(page_url.encode()).hexdigest()
    trows = await db.execute_query(
        """
        SELECT ID_Target FROM SCRAPING_TARGETS
        WHERE ID_Fuente = %s AND Origen_Tabla = %s AND Origen_ID = %s
        LIMIT 1
        """,
        (id_fuente, ORIGIN_TABLE, origin_id),
        fetch_one=True,
    )
    if trows:
        id_target = int(trows[0]["ID_Target"])
    else:
        id_target = await db.execute_insert(
            """
            INSERT INTO SCRAPING_TARGETS (
                ID_Fuente, ID_Ciudad, Tipo_Target, Plataforma,
                URL_Target, Origen_Tabla, Origen_ID,
                Estado, Frecuencia_Horas, Frecuencia_Base_Horas
            ) VALUES (
                %s, %s, 'WEB_LISTADO', NULL,
                %s, %s, %s,
                'OK', 24, 24
            )
            """,
            (id_fuente, id_ciudad, page_url[:2048], ORIGIN_TABLE, origin_id),
        )
    return id_fuente, id_target


async def persist_merged_events(
    db: DatabaseService,
    events: list[MergedEvent],
    *,
    ctx: IngestionContext,
) -> int:
    n = 0
    for ev in events:
        await db.execute_query(
            """
            INSERT INTO EVENTOS_MASTER (
                ID_Unico_Evento, Metodo_Ingesta, ID_Usuario_Carga, Fuente_ID,
                Fuente_URL_Original, ID_Ciudad, CP_Evento, Poblacion_Nombre, Lugar_Nombre,
                Idioma_Origen, Titulo_CAT, Titulo_ES, Desc_Larga_CAT, Desc_Larga_ES,
                Tags_ES, Tags_CAT, Es_Gratuito, Requiere_Inscripcion, Estado, Es_Patrocinado
            ) VALUES (
                %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, 0
            )
            ON DUPLICATE KEY UPDATE
                Titulo_ES = VALUES(Titulo_ES),
                Titulo_CAT = VALUES(Titulo_CAT),
                Desc_Larga_ES = VALUES(Desc_Larga_ES),
                Desc_Larga_CAT = VALUES(Desc_Larga_CAT),
                Lugar_Nombre = VALUES(Lugar_Nombre),
                Fuente_URL_Original = VALUES(Fuente_URL_Original),
                CP_Evento = VALUES(CP_Evento),
                ID_Ciudad = VALUES(ID_Ciudad)
            """,
            (
                ev.id_unico_evento,
                ev.metodo_ingesta,
                ev.id_usuario_carga,
                ev.fuente_id,
                ev.fuente_url_original[:2048],
                ev.id_ciudad,
                ev.cp_evento,
                ev.poblacion_nombre,
                ev.lugar_nombre,
                ev.idioma_origen,
                ev.titulo_cat,
                ev.titulo_es,
                ev.desc_cat,
                ev.desc_es,
                json.dumps(ev.tags_es) if ev.tags_es else None,
                json.dumps(ev.tags_cat) if ev.tags_cat else None,
                1 if ev.es_gratuito else 0,
                1 if ev.requiere_inscripcion else 0,
                ev.estado,
            ),
            fetch_one=False,
            fetch_all=False,
        )

        await db.execute_query(
            "DELETE FROM EVENTO_HORARIOS WHERE ID_Unico_Evento = %s",
            (ev.id_unico_evento,),
            fetch_one=False,
            fetch_all=False,
        )
        hora = ev.hora_inicio
        await db.execute_query(
            """
            INSERT INTO EVENTO_HORARIOS (
                ID_Unico_Evento, Fecha_Inicio, Hora_Inicio, Es_Recurrente, Horario_Texto_ES
            ) VALUES (%s, %s, %s, 0, NULL)
            """,
            (ev.id_unico_evento, ev.fecha_inicio, hora),
            fetch_one=False,
            fetch_all=False,
        )

        url_ef = ev.fuente_url_original[:2048]
        await db.execute_query(
            """
            INSERT INTO EVENTO_FUENTES (
                ID_Unico_Evento, ID_Fuente, URL_Origen,
                Es_Fuente_Principal, Aporto_Extraccion, Score_Calidad
            ) VALUES (%s, %s, %s, 1, 1, 0.85)
            ON DUPLICATE KEY UPDATE
                Score_Calidad = VALUES(Score_Calidad)
            """,
            (ev.id_unico_evento, ctx.id_fuente, url_ef),
            fetch_one=False,
            fetch_all=False,
        )
        n += 1
    return n
