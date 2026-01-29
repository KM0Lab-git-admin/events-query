"""
Rutas y endpoints de la API.
"""

import json
import logging
from datetime import datetime, date
from typing import Optional, List
from fastapi import APIRouter, HTTPException, status, Query
from fastapi.responses import ORJSONResponse

from app.models.schemas import (
    QueryRequest,
    QueryResponse,
    HealthResponse,
    ErrorResponse
)
from app.services import events_service, db_service, ai_service
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
    "/",
    response_class=ORJSONResponse,
    summary="Root endpoint",
    description="Información básica de la API"
)
async def root():
    """Endpoint raíz con información de la API."""
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
        # Construir query dinámicamente
        query = """
        SELECT 
            em.ID_Unico_Evento as id,
            em.Titulo_ES as titulo_es,
            em.Titulo_CAT as titulo_cat,
            em.Desc_Larga_ES as descripcion_es,
            em.Desc_Larga_CAT as descripcion_cat,
            em.CP_Evento as cp,
            em.Poblacion_Nombre as poblacion,
            em.Lugar_Nombre as lugar,
            em.Direccion_Fisica as direccion,
            em.Tipo_Organizador as tipo_organizador,
            em.Organizador_Nombre as organizador,
            em.Organizador_Web as organizador_web,
            em.Es_Gratuito as es_gratuito,
            em.Precio_Euros as precio,
            em.Imagen_Principal_URL as imagen_url,
            em.Tags_ES as tags_es,
            em.Tags_CAT as tags_cat,
            eh.Fecha_Inicio as fecha_inicio,
            eh.Fecha_Fin as fecha_fin,
            eh.Hora_Inicio as hora_inicio,
            eh.Hora_Fin as hora_fin,
            eh.Es_Recurrente as es_recurrente,
            eh.Recurrencia_JSON as recurrencia,
            GROUP_CONCAT(DISTINCT c.Slug) as categorias_slugs,
            GROUP_CONCAT(DISTINCT c.Nombre_ES) as categorias_es,
            GROUP_CONCAT(DISTINCT c.Nombre_CAT) as categorias_cat
        FROM EVENTOS_MASTER em
        LEFT JOIN EVENTO_HORARIOS eh ON em.ID_Unico_Evento = eh.ID_Unico_Evento
        LEFT JOIN EVENTO_CATEGORIAS ec ON em.ID_Unico_Evento = ec.ID_Unico_Evento
        LEFT JOIN CATEGORIAS c ON ec.ID_Categoria = c.ID_Categoria
        WHERE em.Estado = 'ACTIVO'
          AND em.CP_Evento IN (%s, %s)
        """
        
        params = list(POBLACIONES_SOPORTADAS_CP)
        
        # Filtro por población (refina el CP si se elige una concreta)
        if poblacion:
            query += " AND em.Poblacion_Nombre = %s"
            params.append(poblacion)
        
        # Filtro por categoría
        if categoria:
            query += " AND c.Slug = %s"
            params.append(categoria)
        
        # Filtro por tipo organizador
        if tipo_organizador:
            query += " AND em.Tipo_Organizador = %s"
            params.append(tipo_organizador.upper())
        
        # Filtro por tags (busca en Tags_ES y Tags_CAT, coincidencia parcial)
        if tags and tags.strip():
            tag_search = f"%{tags.strip()}%"
            query += " AND (em.Tags_ES LIKE %s OR em.Tags_CAT LIKE %s)"
            params.append(tag_search)
            params.append(tag_search)
        
        # Filtro por fecha desde
        if fecha_desde:
            query += " AND eh.Fecha_Inicio >= %s"
            params.append(fecha_desde)
        
        # Filtro por fecha hasta
        if fecha_hasta:
            query += " AND eh.Fecha_Inicio <= %s"
            params.append(fecha_hasta)
        
        # Filtro por gratuito
        if es_gratuito is not None:
            query += " AND em.Es_Gratuito = %s"
            params.append(es_gratuito)
        
        # Filtro por recurrente
        if es_recurrente is not None:
            query += " AND eh.Es_Recurrente = %s"
            params.append(es_recurrente)
        
        # Agrupar
        query += """
        GROUP BY em.ID_Unico_Evento, eh.ID_Horario
        ORDER BY eh.Fecha_Inicio ASC, eh.Hora_Inicio ASC
        """
        
        # Paginación
        query += f" LIMIT {limit} OFFSET {offset}"
        
        # Ejecutar query
        result = await db_service.execute_query(query, tuple(params) if params else None)
        
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
            evento = {
                "id": row["id"],
                "titulo_es": row["titulo_es"],
                "titulo_cat": row["titulo_cat"],
                "descripcion_es": row["descripcion_es"],
                "descripcion_cat": row["descripcion_cat"],
                "cp": row["cp"],
                "poblacion": row["poblacion"],
                "lugar": row["lugar"],
                "direccion": row["direccion"],
                "tipo_organizador": row["tipo_organizador"],
                "organizador": row["organizador"],
                "organizador_web": row.get("organizador_web"),
                "es_gratuito": bool(row["es_gratuito"]) if row["es_gratuito"] is not None else False,
                "precio": float(row["precio"]) if row["precio"] else None,
                "imagen_url": row["imagen_url"],
                "tags_es": tags_es,
                "tags_cat": tags_cat,
                "fecha_inicio": str(row["fecha_inicio"]) if row["fecha_inicio"] else None,
                "fecha_fin": str(row["fecha_fin"]) if row["fecha_fin"] else None,
                "hora_inicio": str(row["hora_inicio"]) if row["hora_inicio"] else None,
                "hora_fin": str(row["hora_fin"]) if row["hora_fin"] else None,
                "es_recurrente": bool(row["es_recurrente"]) if row["es_recurrente"] is not None else False,
                "recurrencia": row["recurrencia"],
                "categorias_slugs": row["categorias_slugs"].split(",") if row["categorias_slugs"] else [],
                "categorias_es": row["categorias_es"].split(",") if row["categorias_es"] else [],
                "categorias_cat": row["categorias_cat"].split(",") if row["categorias_cat"] else []
            }
            eventos.append(evento)
        
        # Contar total (sin paginación)
        count_query = """
        SELECT COUNT(DISTINCT em.ID_Unico_Evento) as total
        FROM EVENTOS_MASTER em
        LEFT JOIN EVENTO_HORARIOS eh ON em.ID_Unico_Evento = eh.ID_Unico_Evento
        LEFT JOIN EVENTO_CATEGORIAS ec ON em.ID_Unico_Evento = ec.ID_Unico_Evento
        LEFT JOIN CATEGORIAS c ON ec.ID_Categoria = c.ID_Categoria
        WHERE em.Estado = 'ACTIVO'
          AND em.CP_Evento IN (%s, %s)
        """
        
        # Aplicar mismos filtros al count
        count_params = list(POBLACIONES_SOPORTADAS_CP)
        if poblacion:
            count_query += " AND em.Poblacion_Nombre = %s"
            count_params.append(poblacion)
        if categoria:
            count_query += " AND c.Slug = %s"
            count_params.append(categoria)
        if tipo_organizador:
            count_query += " AND em.Tipo_Organizador = %s"
            count_params.append(tipo_organizador.upper())
        if tags and tags.strip():
            tag_search = f"%{tags.strip()}%"
            count_query += " AND (em.Tags_ES LIKE %s OR em.Tags_CAT LIKE %s)"
            count_params.append(tag_search)
            count_params.append(tag_search)
        if fecha_desde:
            count_query += " AND eh.Fecha_Inicio >= %s"
            count_params.append(fecha_desde)
        if fecha_hasta:
            count_query += " AND eh.Fecha_Inicio <= %s"
            count_params.append(fecha_hasta)
        if es_gratuito is not None:
            count_query += " AND em.Es_Gratuito = %s"
            count_params.append(es_gratuito)
        if es_recurrente is not None:
            count_query += " AND eh.Es_Recurrente = %s"
            count_params.append(es_recurrente)
        
        count_result = await db_service.execute_query(count_query, tuple(count_params) if count_params else None)
        total = count_result[0]["total"] if count_result else 0
        
        return {
            "eventos": eventos,
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(eventos) < total,
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
