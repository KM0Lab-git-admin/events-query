"""
Aplicación principal FastAPI - Events Query API.
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from app.config import settings
from app.api.routes import router
from app.services import db_service

# Configurar logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gestiona el ciclo de vida de la aplicación.
    Se ejecuta al inicio y al final de la aplicación.
    """
    # Startup
    logger.info("=" * 50)
    logger.info(f"Iniciando {settings.app_name} v{settings.app_version}")
    logger.info(f"Entorno: {settings.environment}")
    logger.info("=" * 50)
    
    # Conectar a la base de datos
    try:
        await db_service.connect()
        logger.info("✓ Base de datos conectada")
    except Exception as e:
        logger.error(f"✗ Error al conectar a la base de datos: {e}")
        raise
    
    # Verificar configuración de OpenAI
    if settings.openai_api_key:
        logger.info("✓ OpenAI API key configurada")
    else:
        logger.warning("✗ OpenAI API key NO configurada")
    
    logger.info("✓ Aplicación iniciada correctamente")
    logger.info("=" * 50)
    
    yield
    
    # Shutdown
    logger.info("Cerrando aplicación...")
    
    # Desconectar de la base de datos
    try:
        await db_service.disconnect()
        logger.info("✓ Base de datos desconectada")
    except Exception as e:
        logger.error(f"✗ Error al desconectar de la base de datos: {e}")
    
    logger.info("✓ Aplicación cerrada correctamente")


# Crear aplicación FastAPI
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=settings.app_description,
    lifespan=lifespan,
    default_response_class=ORJSONResponse,  # Usar ORJSONResponse por defecto
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.is_development else [],  # En producción, especificar dominios
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Incluir rutas
app.include_router(router, tags=["Events"])

# Middleware para logging de requests
@app.middleware("http")
async def log_requests(request, call_next):
    """Middleware para loggear todas las requests."""
    logger.info(f"→ {request.method} {request.url.path}")
    response = await call_next(request)
    logger.info(f"← {request.method} {request.url.path} - Status: {response.status_code}")
    return response


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_reload,
        log_level=settings.log_level.lower()
    )
