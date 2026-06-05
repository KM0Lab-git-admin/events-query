"""
API v1 Router - Aggregates all v1 endpoints.
"""

from fastapi import APIRouter

from app.api.v1 import query, events, categories, health, ingest_sync

# Create v1 router
router = APIRouter(prefix="/api/v1")

# Include all v1 routers
router.include_router(query.router, tags=["Query"])
router.include_router(events.router, tags=["Events"])
router.include_router(categories.router, tags=["Categories"])
router.include_router(health.router, tags=["Health"])
router.include_router(ingest_sync.router, tags=["Ingest"])
