#!/usr/bin/env python3
"""
Script to verify API v1 endpoints are correctly registered.
Run this to confirm all endpoints will appear in Swagger documentation.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set environment to local to avoid DB validation
os.environ['ENVIRONMENT'] = 'local'

from fastapi import FastAPI
from app.api.v1.router import router as v1_router

def main():
    # Create FastAPI app
    app = FastAPI(
        title="Events Query API",
        version="1.0.0",
        description="API de búsqueda de eventos con lenguaje natural"
    )
    
    # Include v1 router
    app.include_router(v1_router)
    
    # Extract API routes
    api_routes = []
    for route in app.routes:
        if hasattr(route, 'path') and hasattr(route, 'methods'):
            # Skip internal FastAPI routes
            if route.path in ['/openapi.json', '/docs', '/docs/oauth2-redirect', '/redoc']:
                continue
            
            methods = sorted(route.methods)
            for method in methods:
                if method in ['GET', 'POST', 'PUT', 'DELETE', 'PATCH']:
                    api_routes.append({
                        'method': method,
                        'path': route.path,
                        'name': route.name,
                        'summary': getattr(route, 'summary', '')
                    })
    
    # Display results
    print("=" * 80)
    print("API v1 Endpoints Verification")
    print("=" * 80)
    print(f"\nTotal API endpoints found: {len(api_routes)}")
    print("\nEndpoints that will appear in Swagger documentation:")
    print("-" * 80)
    
    for route in sorted(api_routes, key=lambda x: (x['path'], x['method'])):
        print(f"{route['method']:6} {route['path']:40} {route['summary']}")
    
    print("\n" + "=" * 80)
    print("Expected Endpoints:")
    print("=" * 80)
    
    expected = [
        ('POST', '/api/v1/query', 'Search events with natural language'),
        ('GET', '/api/v1/events', 'List events with filters and pagination'),
        ('GET', '/api/v1/events/{event_id}', 'Get event details'),
        ('GET', '/api/v1/events/today', "Get today's events"),
        ('GET', '/api/v1/events/upcoming', 'Get upcoming events'),
        ('GET', '/api/v1/categories', 'List event categories'),
        ('GET', '/api/v1/health', 'Health check'),
    ]
    
    for method, path, desc in expected:
        print(f"{method:6} {path:40} {desc}")
    
    # Verify all expected endpoints are present
    print("\n" + "=" * 80)
    print("Verification Results:")
    print("=" * 80)
    
    found_paths = {(r['method'], r['path']) for r in api_routes}
    expected_paths = {(m, p) for m, p, _ in expected}
    
    missing = expected_paths - found_paths
    extra = found_paths - expected_paths
    
    if not missing and not extra:
        print("✅ SUCCESS: All expected endpoints are correctly registered!")
        print("✅ Swagger documentation will show all 7 API v1 endpoints.")
        return 0
    else:
        if missing:
            print("❌ MISSING endpoints:")
            for method, path in missing:
                print(f"   {method} {path}")
        
        if extra:
            print("⚠️  EXTRA endpoints (not in specification):")
            for method, path in extra:
                print(f"   {method} {path}")
        
        return 1

if __name__ == '__main__':
    sys.exit(main())
