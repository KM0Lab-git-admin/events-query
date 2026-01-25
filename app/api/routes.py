"""
Rutas y endpoints de la API.
"""

import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException, status
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
