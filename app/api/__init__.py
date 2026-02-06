"""
API endpoints de Events Query API.
"""

# Legacy routes kept for backwards compatibility
from app.api.routes import router as legacy_router

# API v1 routes
from app.api.v1.router import router as v1_router

__all__ = ["legacy_router", "v1_router"]
