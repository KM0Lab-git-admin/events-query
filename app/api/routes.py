"""
Rutas y endpoints de la API.
"""

import json
import logging
from datetime import datetime, date
from typing import Optional, List, Any
from fastapi import APIRouter, HTTPException, status, Query
from fastapi.responses import ORJSONResponse

from app.models.schemas import (
    QueryRequest,
    QueryResponse,
    HealthResponse,
    ErrorResponse
)
from app.services import events_service, db_service, ai_service
from app.services.event_binarios import fetch_imagenes_por_eventos, merge_imagenes_en_eventos
from app.config import settings

logger = logging.getLogger(__name__)

# Códigos postales de las únicas poblaciones soportadas (Malgrat de Mar y Blanes)
POBLACIONES_SOPORTADAS_CP = ("08380", "17300")

# Router principal
router = APIRouter()


@router.post(
    "/query",
    response_model=QueryResponse,
    response_class=ORJSONResponse,
    summary="Buscar eventos",
    description="Busca eventos usando lenguaje natural",
    responses={
        200: {"description": "Eventos encontrados exitosamente"},
        400: {"model": ErrorResponse, "description": "Request inválido"},
        500: {"model": ErrorResponse, "description": "Error interno del servidor"}
    }
)
async def query_events(request: QueryRequest) -> QueryResponse:
    """
    Endpoint principal para buscar eventos con lenguaje natural.
    
    **Ejemplo de request:**
    ```json
    {
        "pregunta": "¿Qué hacer este fin de semana?",
        "cp_usuario": "08380",
        "debug": false
    }
    ```
    
    **Ejemplo de response:**
    ```json
    {
        "respuesta_texto": "He encontrado 5 eventos para ti este fin de semana...",
        "eventos": [...],
        "total": 5,
        "idioma_respuesta": "es"
    }
    ```
    """
    try:
        logger.info(f"POST /query - pregunta: '{request.pregunta}', cp: {request.cp_usuario}")
        
        # Procesar búsqueda
        response = await events_service.search_events(request)
        
        logger.info(f"Búsqueda completada: {response.total} eventos encontrados")
        
        return response
        
    except ValueError as e:
        logger.error(f"Error de validación: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error interno: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor"
        )


@router.get(
    "/health",
    response_model=HealthResponse,
    response_class=ORJSONResponse,
    summary="Health check",
    description="Verifica el estado de salud de la API y sus dependencias"
)
async def health_check() -> HealthResponse:
    """
    Endpoint de health check.
    
    Verifica:
    - Estado de la base de datos
    - Conectividad con OpenAI
    - Estado general de la API
    """
    checks = {}
    overall_status = "healthy"
    
    # Check database
    try:
        db_healthy = await db_service.health_check()
        checks["database"] = "healthy" if db_healthy else "unhealthy"
        if not db_healthy:
            overall_status = "unhealthy"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        checks["database"] = "unhealthy"
        overall_status = "unhealthy"
    
    # Check OpenAI (simple check de API key configurada)
    try:
        checks["openai"] = "configured" if settings.openai_api_key else "not_configured"
        if not settings.openai_api_key:
            overall_status = "unhealthy"
    except Exception as e:
        logger.error(f"OpenAI check failed: {e}")
        checks["openai"] = "error"
        overall_status = "unhealthy"
    
    # Check API
    checks["api"] = "healthy"
    
    return HealthResponse(
        status=overall_status,
        version=settings.app_version,
        timestamp=datetime.now(),
        checks=checks
    )


@router.get(
    "/api/info",
    response_class=ORJSONResponse,
    summary="API Info",
    description="Información básica de la API"
)
async def api_info():
    """Endpoint con información de la API."""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "description": settings.app_description,
        "docs_url": "/docs",
        "health_url": "/health"
    }


@router.get(
    "/events/simple",
    response_class=ORJSONResponse,
    summary="Listar eventos (simple)",
    description="Lista simple de todos los eventos para visualización rápida"
)
async def list_events_simple():
    """
    Endpoint simple para listar eventos.
    
    Devuelve una lista básica de eventos con información esencial
    para poder visualizar qué datos hay disponibles en la BD.
    """
    try:
        query = """
        SELECT 
            em.ID_Unico_Evento,
            em.Titulo_ES,
            em.Titulo_CAT,
            em.CP_Evento,
            em.Poblacion_Nombre,
            em.Es_Gratuito,
            em.Precio_Euros,
            MIN(eh.Fecha_Inicio) as Fecha_Inicio,
            MIN(eh.Hora_Inicio) as Hora_Inicio,
            GROUP_CONCAT(DISTINCT c.Nombre_ES SEPARATOR ', ') AS Categorias
        FROM EVENTOS_MASTER em
        LEFT JOIN EVENTO_HORARIOS eh ON em.ID_Unico_Evento = eh.ID_Unico_Evento
        LEFT JOIN EVENTO_CATEGORIAS ec ON em.ID_Unico_Evento = ec.ID_Unico_Evento
        LEFT JOIN CATEGORIAS c ON ec.ID_Categoria = c.ID_Categoria
        WHERE em.Estado = 'ACTIVO'
          AND em.CP_Evento IN (%s, %s)
        GROUP BY em.ID_Unico_Evento, em.Titulo_ES, em.Titulo_CAT, em.CP_Evento, em.Poblacion_Nombre, em.Es_Gratuito, em.Precio_Euros
        ORDER BY Fecha_Inicio ASC, em.Titulo_ES ASC
        LIMIT 200
        """
        
        async with db_service.get_connection() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(query, POBLACIONES_SOPORTADAS_CP)
                rows = await cursor.fetchall()
                
                eventos = []
                for row in rows:
                    eventos.append({
                        "id": row[0],
                        "titulo_es": row[1],
                        "titulo_cat": row[2],
                        "cp": row[3],
                        "poblacion": row[4],
                        "es_gratuito": bool(row[5]),
                        "precio": float(row[6]) if row[6] else None,
                        "fecha": str(row[7]) if row[7] else None,
                        "hora": str(row[8]) if row[8] else None,
                        "categorias": row[9] if row[9] else ""
                    })
                
                return {
                    "eventos": eventos,
                    "total": len(eventos)
                }
                
    except Exception as e:
        logger.error(f"Error al listar eventos: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener eventos"
        )


@router.get(
    "/events/list",
    response_class=ORJSONResponse,
    summary="Listar eventos con filtros",
    description="Lista eventos con filtros avanzados: población, categoría, organizador, fechas, precio"
)
async def list_events_with_filters(
    poblacion: Optional[str] = Query(None, description="Filtrar por nombre de población (ej: 'Malgrat de Mar')"),
    categoria: Optional[str] = Query(None, description="Filtrar por slug de categoría (ej: 'cultura', 'deportes')"),
    tipo_organizador: Optional[str] = Query(None, description="Filtrar por tipo: PUBLICO, PRIVADO, ASOCIACION"),
    tags: Optional[str] = Query(None, description="Filtrar por texto en tags (campo abierto, busca en tags ES y CAT)"),
    fecha_desde: Optional[date] = Query(None, description="Fecha mínima (YYYY-MM-DD)"),
    fecha_hasta: Optional[date] = Query(None, description="Fecha máxima (YYYY-MM-DD)"),
    es_gratuito: Optional[bool] = Query(None, description="Filtrar solo eventos gratuitos"),
    es_recurrente: Optional[bool] = Query(None, description="Filtrar eventos recurrentes"),
    limit: int = Query(50, ge=1, le=200, description="Número máximo de resultados"),
    offset: int = Query(0, ge=0, description="Offset para paginación")
):
    """
    Endpoint avanzado para listar eventos con filtros.
    
    **Filtros disponibles:**
    - `poblacion`: Nombre de la población (Malgrat de Mar, Blanes)
    - `categoria`: Slug de categoría (cultura, deportes, ocio, infantil, formacion, gastronomia, musica, naturaleza)
    - `tipo_organizador`: PUBLICO, PRIVADO, ASOCIACION
    - `tags`: Texto libre para buscar en tags (ES y CAT)
    - `fecha_desde` / `fecha_hasta`: Rango de fechas
    - `es_gratuito`: true/false
    - `es_recurrente`: true/false
    
    **Paginación:**
    - `limit`: Número de resultados (máx 200)
    - `offset`: Saltar N resultados
    
    **Ejemplo:**
    ```
    GET /events/list?poblacion=Malgrat%20de%20Mar&categoria=gastronomia&es_gratuito=true&limit=20
    ```
    """
    try:
        # Construir filtros dinámicos (evento único + horarios agregados)
        where_clauses = [
            "em.Estado = 'ACTIVO'",
            "em.CP_Evento IN (%s, %s)",
        ]
        where_params: List[Any] = list(POBLACIONES_SOPORTADAS_CP)

        if poblacion:
            where_clauses.append("em.Poblacion_Nombre = %s")
            where_params.append(poblacion)

        if categoria:
            where_clauses.append(
                """
                EXISTS (
                    SELECT 1
                    FROM EVENTO_CATEGORIAS ecf
                    JOIN CATEGORIAS cf ON ecf.ID_Categoria = cf.ID_Categoria
                    WHERE ecf.ID_Unico_Evento = em.ID_Unico_Evento
                      AND cf.Slug = %s
                )
                """
            )
            where_params.append(categoria)

        if tipo_organizador:
            where_clauses.append("em.Tipo_Organizador = %s")
            where_params.append(tipo_organizador.upper())

        if tags and tags.strip():
            tag_search = f"%{tags.strip()}%"
            where_clauses.append("(em.Tags_ES LIKE %s OR em.Tags_CAT LIKE %s)")
            where_params.append(tag_search)
            where_params.append(tag_search)

        horario_filters: List[str] = []
        horario_params: List[Any] = []
        if fecha_desde:
            horario_filters.append("ehf.Fecha_Inicio >= %s")
            horario_params.append(fecha_desde)
        if fecha_hasta:
            horario_filters.append("ehf.Fecha_Inicio <= %s")
            horario_params.append(fecha_hasta)
        if es_recurrente is not None:
            horario_filters.append("ehf.Es_Recurrente = %s")
            horario_params.append(es_recurrente)
        if horario_filters:
            where_clauses.append(
                f"""
                EXISTS (
                    SELECT 1
                    FROM EVENTO_HORARIOS ehf
                    WHERE ehf.ID_Unico_Evento = em.ID_Unico_Evento
                      AND {' AND '.join(horario_filters)}
                )
                """
            )
            where_params.extend(horario_params)

        if es_gratuito is not None:
            where_clauses.append("em.Es_Gratuito = %s")
            where_params.append(es_gratuito)

        where_sql = " AND ".join(where_clauses)

        query = f"""
        SELECT
            em.ID_Unico_Evento as id,
            COALESCE(em.ID_Familia, em.ID_Unico_Evento) as familia,
            em.Titulo_ES as titulo_es,
            em.Titulo_CAT as titulo_cat,
            em.Desc_Larga_ES as descripcion_es,
            em.Desc_Larga_CAT as descripcion_cat,
            COALESCE(NULLIF(em.Desc_Corta_ES, ''),
                     LEFT(COALESCE(em.Desc_Larga_ES, ''), 400)) as descripcion_corta_es,
            COALESCE(NULLIF(em.Desc_Corta_CAT, ''),
                     LEFT(COALESCE(em.Desc_Larga_CAT, ''), 400)) as descripcion_corta_cat,
            em.CP_Evento as cp,
            em.Poblacion_Nombre as poblacion,
            em.Lugar_Nombre as lugar,
            em.Direccion_Fisica as direccion,
            em.Tipo_Organizador as tipo_organizador,
            em.Organizador_Nombre as organizador,
            em.Organizador_Web as organizador_web,
            em.Fuente_URL_Original as fuente_url_original,
            em.Es_Gratuito as es_gratuito,
            em.Precio_Euros as precio,
            em.Imagen_Principal_URL as imagen_url,
            em.Tags_ES as tags_es,
            em.Tags_CAT as tags_cat,
            (
                SELECT MIN(eh0.Fecha_Inicio)
                FROM EVENTO_HORARIOS eh0
                WHERE eh0.ID_Unico_Evento = em.ID_Unico_Evento
            ) as fecha_inicio,
            (
                SELECT MIN(eh0.Hora_Inicio)
                FROM EVENTO_HORARIOS eh0
                WHERE eh0.ID_Unico_Evento = em.ID_Unico_Evento
            ) as hora_inicio,
            (
                SELECT COALESCE(
                    JSON_ARRAYAGG(
                        JSON_OBJECT(
                            'fecha_inicio', eh2.Fecha_Inicio,
                            'fecha_fin', eh2.Fecha_Fin,
                            'hora_inicio', eh2.Hora_Inicio,
                            'hora_fin', eh2.Hora_Fin,
                            'es_recurrente', eh2.Es_Recurrente,
                            'recurrencia', eh2.Recurrencia_JSON
                        )
                    ),
                    JSON_ARRAY()
                )
                FROM EVENTO_HORARIOS eh2
                WHERE eh2.ID_Unico_Evento = em.ID_Unico_Evento
            ) as horarios_json,
            (
                SELECT GROUP_CONCAT(DISTINCT c1.Slug ORDER BY c1.Slug)
                FROM EVENTO_CATEGORIAS ec1
                JOIN CATEGORIAS c1 ON ec1.ID_Categoria = c1.ID_Categoria
                WHERE ec1.ID_Unico_Evento = em.ID_Unico_Evento
            ) as categorias_slugs,
            (
                SELECT GROUP_CONCAT(DISTINCT c2.Nombre_ES ORDER BY c2.Slug)
                FROM EVENTO_CATEGORIAS ec2
                JOIN CATEGORIAS c2 ON ec2.ID_Categoria = c2.ID_Categoria
                WHERE ec2.ID_Unico_Evento = em.ID_Unico_Evento
            ) as categorias_es,
            (
                SELECT GROUP_CONCAT(DISTINCT c3.Nombre_CAT ORDER BY c3.Slug)
                FROM EVENTO_CATEGORIAS ec3
                JOIN CATEGORIAS c3 ON ec3.ID_Categoria = c3.ID_Categoria
                WHERE ec3.ID_Unico_Evento = em.ID_Unico_Evento
            ) as categorias_cat
        FROM EVENTOS_MASTER em
        WHERE {where_sql}
        ORDER BY fecha_inicio ASC, hora_inicio ASC, em.Titulo_ES ASC
        """
        # Nota: sin LIMIT en SQL — la agrupación por familia y la paginación se
        # hacen en Python sobre las tarjetas resultantes (volumen actual bajo).

        result = await db_service.execute_query(query, tuple(where_params))
        
        # Formatear resultados
        eventos = []
        for row in result or []:
            # Parsear tags desde JSON si vienen como string
            tags_es = row["tags_es"]
            if isinstance(tags_es, str):
                try:
                    tags_es = json.loads(tags_es) if tags_es else []
                except (ValueError, TypeError):
                    tags_es = []
            tags_es = tags_es or []
            tags_cat = row["tags_cat"]
            if isinstance(tags_cat, str):
                try:
                    tags_cat = json.loads(tags_cat) if tags_cat else []
                except (ValueError, TypeError):
                    tags_cat = []
            tags_cat = tags_cat or []
            horarios_raw = row.get("horarios_json") or []
            if isinstance(horarios_raw, str):
                try:
                    horarios_raw = json.loads(horarios_raw)
                except (ValueError, TypeError):
                    horarios_raw = []
            horarios: List[Dict[str, Any]] = []
            for h in horarios_raw or []:
                if not isinstance(h, dict):
                    continue
                horarios.append(
                    {
                        "fecha_inicio": str(h.get("fecha_inicio")) if h.get("fecha_inicio") else None,
                        "fecha_fin": str(h.get("fecha_fin")) if h.get("fecha_fin") else None,
                        "hora_inicio": str(h.get("hora_inicio")) if h.get("hora_inicio") else None,
                        "hora_fin": str(h.get("hora_fin")) if h.get("hora_fin") else None,
                        "es_recurrente": bool(h.get("es_recurrente")) if h.get("es_recurrente") is not None else False,
                        "recurrencia": h.get("recurrencia"),
                    }
                )
            # Orden estable en Python (MySQL no garantiza orden en JSON_ARRAYAGG aquí)
            horarios.sort(key=lambda x: (x.get("fecha_inicio") or "", x.get("hora_inicio") or ""))

            evento = {
                "id": row["id"],
                "familia": row["familia"],
                "titulo_es": row["titulo_es"],
                "titulo_cat": row["titulo_cat"],
                "descripcion_es": row["descripcion_es"],
                "descripcion_cat": row["descripcion_cat"],
                "descripcion_corta_es": row["descripcion_corta_es"],
                "descripcion_corta_cat": row["descripcion_corta_cat"],
                "cp": row["cp"],
                "poblacion": row["poblacion"],
                "lugar": row["lugar"],
                "direccion": row["direccion"],
                "tipo_organizador": row["tipo_organizador"],
                "organizador": row["organizador"],
                "organizador_web": row.get("organizador_web"),
                "fuente_url_original": row.get("fuente_url_original"),
                "es_gratuito": bool(row["es_gratuito"]) if row["es_gratuito"] is not None else False,
                "precio": float(row["precio"]) if row["precio"] else None,
                "imagen_url": row["imagen_url"],
                "tags_es": tags_es,
                "tags_cat": tags_cat,
                "fecha_inicio": str(row["fecha_inicio"]) if row["fecha_inicio"] else None,
                "fecha_fin": None,
                "hora_inicio": str(row["hora_inicio"]) if row["hora_inicio"] else None,
                "hora_fin": None,
                "es_recurrente": any(h.get("es_recurrente") for h in horarios),
                "recurrencia": next((h.get("recurrencia") for h in horarios if h.get("recurrencia")), None),
                "horarios": horarios,
                "categorias_slugs": row["categorias_slugs"].split(",") if row["categorias_slugs"] else [],
                "categorias_es": row["categorias_es"].split(",") if row["categorias_es"] else [],
                "categorias_cat": row["categorias_cat"].split(",") if row["categorias_cat"] else []
            }
            eventos.append(evento)

        # AGRUPACIÓN POR FAMILIA: los eventos que cuelgan de un evento paraguas
        # (festival, fira, ciclo) comparten ID_Familia. Se devuelve UNA tarjeta
        # por familia: la cabeza (rango de fechas más amplio; empate ->
        # descripción más larga) con sus 'actividades' anidadas.
        def _span_dias(e: Dict[str, Any]) -> int:
            fechas = [h.get("fecha_inicio") for h in e.get("horarios", []) if h.get("fecha_inicio")]
            fines = [h.get("fecha_fin") or h.get("fecha_inicio")
                     for h in e.get("horarios", []) if h.get("fecha_inicio")]
            if not fechas:
                return 0
            try:
                d0 = date.fromisoformat(min(fechas))
                d1 = date.fromisoformat(max(f for f in fines if f))
                return (d1 - d0).days
            except (ValueError, TypeError):
                return 0

        familias: Dict[str, List[Dict[str, Any]]] = {}
        orden_familias: List[str] = []
        for e in eventos:
            key = e["familia"]
            if key not in familias:
                familias[key] = []
                orden_familias.append(key)
            familias[key].append(e)

        tarjetas: List[Dict[str, Any]] = []
        for key in orden_familias:
            miembros = familias[key]
            cabeza = max(miembros,
                         key=lambda e: (_span_dias(e),
                                        len(e.get("descripcion_cat") or "")))
            actividades = [e for e in miembros if e["id"] != cabeza["id"]]
            actividades.sort(key=lambda e: (e.get("fecha_inicio") or "",
                                            e.get("hora_inicio") or ""))
            cabeza["es_familia"] = bool(actividades)
            cabeza["actividades"] = actividades
            tarjetas.append(cabeza)

        total = len(tarjetas)
        pagina = tarjetas[offset:offset + limit]

        try:
            async with db_service.get_connection() as conn:
                # imágenes de las cabezas de la página y de sus actividades
                visibles = list(pagina)
                for c in pagina:
                    visibles.extend(c.get("actividades", []))
                ids_ev = [e["id"] for e in visibles if e.get("id")]
                img_map = await fetch_imagenes_por_eventos(conn, ids_ev) if ids_ev else {}
                merge_imagenes_en_eventos(visibles, img_map)
        except Exception as img_err:
            logger.warning("BINARIOS_STORAGE no disponible o error al cargar imágenes: %s", img_err)
            for e in pagina:
                e.setdefault("imagenes", [])

        return {
            "eventos": pagina,
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(pagina) < total,
            "filtros_aplicados": {
                "poblacion": poblacion,
                "categoria": categoria,
                "tipo_organizador": tipo_organizador,
                "tags": tags.strip() if tags and tags.strip() else None,
                "fecha_desde": str(fecha_desde) if fecha_desde else None,
                "fecha_hasta": str(fecha_hasta) if fecha_hasta else None,
                "es_gratuito": es_gratuito,
                "es_recurrente": es_recurrente
            }
        }
        
    except Exception as e:
        logger.error(f"Error al listar eventos con filtros: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener eventos"
        )


@router.get(
    "/events/categorias",
    response_class=ORJSONResponse,
    summary="Listar categorías",
    description="Obtiene todas las categorías disponibles"
)
async def list_categorias():
    """Devuelve la lista de categorías disponibles."""
    try:
        query = """
        SELECT 
            ID_Categoria as id,
            Nombre_ES as nombre_es,
            Nombre_CAT as nombre_cat,
            Slug as slug,
            Icono as icono,
            Color_Hex as color
        FROM CATEGORIAS
        WHERE Activo = TRUE
        ORDER BY Orden ASC
        """
        
        result = await db_service.execute_query(query)
        
        return {
            "categorias": result or [],
            "total": len(result) if result else 0
        }
        
    except Exception as e:
        logger.error(f"Error al listar categorías: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener categorías"
        )


@router.get(
    "/events/poblaciones",
    response_class=ORJSONResponse,
    summary="Listar poblaciones",
    description="Obtiene las poblaciones disponibles con eventos (solo Malgrat de Mar y Blanes)"
)
async def list_poblaciones():
    """Devuelve la lista de poblaciones con eventos. Solo Malgrat de Mar (08380) y Blanes (17300)."""
    try:
        query = """
        SELECT
            em.Poblacion_Nombre as nombre,
            em.CP_Evento as cp,
            COUNT(em.ID_Unico_Evento) as total_eventos
        FROM EVENTOS_MASTER em
        WHERE em.Estado = 'ACTIVO'
          AND em.CP_Evento IN (%s, %s)
        GROUP BY em.Poblacion_Nombre, em.CP_Evento
        ORDER BY em.Poblacion_Nombre ASC
        """
        
        result = await db_service.execute_query(query, POBLACIONES_SOPORTADAS_CP)
        
        # Asegurar que total_eventos es entero (MySQL puede devolver Decimal)
        poblaciones = []
        if result:
            for row in result:
                poblaciones.append({
                    "nombre": row["nombre"],
                    "cp": row["cp"],
                    "total_eventos": int(row["total_eventos"]) if row.get("total_eventos") is not None else 0
                })
        
        return {
            "poblaciones": poblaciones,
            "total": len(poblaciones)
        }
        
    except Exception as e:
        logger.error(f"Error al listar poblaciones: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener poblaciones"
        )
