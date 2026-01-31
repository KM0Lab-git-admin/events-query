"""
Aplicación principal FastAPI - Events Query API.
"""

import logging
import os
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.api.routes import router
from app.services import db_service
from app.services.seed_service import seed_if_empty

# Ruta al frontend compilado
FRONTEND_DIR = Path(__file__).parent.parent / "frontend" / "dist"

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

    # Crear tablas si no existen (útil para Railway y despliegues sin init manual)
    try:
        await db_service.init_schema_if_needed()
    except Exception as e:
        logger.error(f"✗ Error al inicializar esquema: {e}")
        raise

    # Auto-seed: generar datos fake si la BD está vacía (solo primera vez)
    try:
        await seed_if_empty()
    except Exception as e:
        logger.warning(f"⚠ Error en auto-seed (no crítico): {e}")
        # No hacer raise - el seed no es crítico para arrancar

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
    allow_origins = ["*"],  # En producción, especificar dominios
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


# ============================================
# Servir Frontend estático (SPA)
# ============================================

# Montar assets estáticos (JS, CSS, imágenes) si el directorio existe
if FRONTEND_DIR.exists():
    # Montar la carpeta assets
    assets_dir = FRONTEND_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="static-assets")
    
    logger.info(f"✓ Frontend estático configurado desde {FRONTEND_DIR}")
    
    # Ruta para la raíz - sirve index.html
    @app.get("/")
    async def serve_index():
        """Sirve el index.html del frontend en la raíz."""
        index_file = FRONTEND_DIR / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        return ORJSONResponse(status_code=404, content={"detail": "Frontend not found"})
    
    # Ruta catch-all para SPA - debe ir AL FINAL para no bloquear rutas de API
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """
        Sirve el frontend React para cualquier ruta no manejada por la API.
        Permite que React Router maneje el routing del lado del cliente.
        """
        # Si es una ruta de API conocida, dejar que FastAPI devuelva 404
        api_prefixes = ("api", "events", "query", "health", "docs", "redoc", "openapi.json")
        if full_path.startswith(api_prefixes):
            return ORJSONResponse(
                status_code=404,
                content={"detail": "Not Found"}
            )
        
        # Para cualquier otra ruta, servir index.html (SPA)
        index_file = FRONTEND_DIR / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        
        return ORJSONResponse(
            status_code=404,
            content={"detail": "Frontend not found"}
        )
else:
    logger.warning(f"⚠ Frontend no encontrado en {FRONTEND_DIR}")


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_reload,
        log_level=settings.log_level.lower()
    )
