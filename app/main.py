"""
Aplicación principal FastAPI - Events Query API.
"""

import logging
import os
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.api.v1.router import router as v1_router
from app.api.routes import router as legacy_router
from app.services import db_service

# Ruta al frontend compilado
FRONTEND_DIR = Path(__file__).parent.parent / "frontend" / "dist"

# Configurar logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Rate limiter
limiter = Limiter(key_func=get_remote_address)


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

    # Datos fake: solo con `python scripts/generate_fake_data.py` (no auto-seed al arrancar).

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
    default_response_class=ORJSONResponse,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# Configure rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Configurar CORS
allowed_origins = [
    "https://app.km0lab.com",
    "https://www.app.km0lab.com",
    "https://eventquery.km0lab.com",
    "http://localhost:5173",  # Vite dev
    "http://localhost:3000",  # React dev
]

# In development, allow all origins
if settings.environment == "development":
    allowed_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"],
)

# Include API v1 routes (production)
app.include_router(v1_router)

# Include legacy routes (backwards compatibility for PoC frontend)
app.include_router(legacy_router, tags=["Legacy"])

# Imágenes guardadas por ingesta (persist_phase_c → repo/static/images/<ID_Unico_Evento>/...)
STATIC_IMAGES_DIR = Path(__file__).resolve().parent.parent / "static" / "images"
if STATIC_IMAGES_DIR.is_dir():
    app.mount(
        "/static/images",
        StaticFiles(directory=str(STATIC_IMAGES_DIR)),
        name="event-images",
    )
    logger.info("✓ Montado /static/images desde %s", STATIC_IMAGES_DIR)
else:
    logger.warning(
        "⚠ Carpeta %s no existe; URLs /static/images/... devolverán 404 hasta crearla (ingesta).",
        STATIC_IMAGES_DIR,
    )

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
        # Archivos estáticos de eventos (montaje más arriba); si llegan aquí, no servir SPA
        if full_path.startswith("static/images/"):
            return ORJSONResponse(
                status_code=404,
                content={"detail": "Image not found"},
            )

        # Si es una ruta de API conocida, dejar que FastAPI devuelva 404
        api_prefixes = ("api", "docs", "redoc", "openapi.json")
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
