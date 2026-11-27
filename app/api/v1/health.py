"""
Health check endpoint - API status monitoring.
"""

import logging
from datetime import datetime
from fastapi import APIRouter
from fastapi.responses import ORJSONResponse

from app.models.schemas import HealthResponse
from app.services import db_service
from app.config import settings

logger = logging.getLogger(__name__)

# Router
router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    response_class=ORJSONResponse,
    summary="Health check",
    description="Check API health status and dependencies",
    responses={
        200: {
            "description": "Health status retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "status": "healthy",
                        "version": "1.0.0",
                        "timestamp": "2026-02-06T12:00:00",
                        "checks": {
                            "database": "healthy",
                            "openai": "configured",
                            "api": "healthy"
                        }
                    }
                }
            }
        }
    }
)
async def health_check() -> HealthResponse:
    """
    Health check endpoint.
    
    **Checks:**
    - Database connectivity
    - OpenAI API configuration
    - API status
    
    **Status values:**
    - `healthy`: All systems operational
    - `unhealthy`: One or more systems failing
    
    **Example:**
    ```
    GET /api/v1/health
    ```
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
    
    # Check OpenAI
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
