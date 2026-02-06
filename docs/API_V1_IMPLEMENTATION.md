# API v1 Implementation Guide

## Overview

This document describes the implementation of the **Events Query API v1** with optimizations, rate limiting, CORS configuration, and comprehensive Swagger documentation.

## What's New in v1

### 1. API Versioning
- **Base URL**: `/api/v1/`
- All endpoints now use versioned paths
- Backwards compatibility: old endpoints remain functional

### 2. New Endpoints

#### **GET /api/v1/events**
- List events with pagination and filters
- **Pagination**: `page` (default 1), `page_size` (default 20, max 100)
- **Filters**:
  - `poblacion`: Filter by town name
  - `categoria`: Filter by category slug
  - `fecha_desde`: Start date (defaults to today)
  - `fecha_hasta`: End date (defaults to today + 30 days)
  - `es_gratuito`: Filter free events
  - `search`: Text search in titles and tags
- **Rate limit**: 100 requests/minute
- **Response**: Paginated list with metadata

#### **GET /api/v1/events/{event_id}**
- Get full details for a specific event
- **Rate limit**: 100 requests/minute
- **Response**: Complete event information including schedules, categories, and organizer details

#### **GET /api/v1/events/today**
- Get events happening today (optimized and cached)
- **Rate limit**: 200 requests/minute
- **Cache**: 5 minutes (recommended)
- **Response**: List of today's events with essential fields

#### **GET /api/v1/events/upcoming**
- Get upcoming events (next 7 days by default)
- **Parameters**: `days` (1-30, default 7)
- **Rate limit**: 100 requests/minute
- **Response**: List of upcoming events

#### **GET /api/v1/categories**
- List all event categories with event counts
- **Rate limit**: 100 requests/minute
- **Cache**: 1 hour (recommended)
- **Response**: List of categories with counts

#### **POST /api/v1/query**
- Natural language event search (existing endpoint, now versioned)
- **Rate limit**: 30 requests/minute
- **Response**: Natural language response with matching events

#### **GET /api/v1/health**
- Health check endpoint
- **No rate limit**
- **Response**: API status and dependency checks

### 3. Rate Limiting

Implemented using `slowapi`:
- **30/min** for `/query` (AI-powered search)
- **100/min** for `/events`, `/events/{id}`, `/categories`, `/events/upcoming`
- **200/min** for `/events/today` (high-traffic endpoint)

Rate limit headers:
- `X-RateLimit-Limit`: Maximum requests allowed
- `X-RateLimit-Remaining`: Remaining requests
- `X-RateLimit-Reset`: Time when limit resets

### 4. CORS Configuration

**Allowed origins**:
- `https://app.km0lab.com` (production frontend)
- `https://www.app.km0lab.com`
- `https://eventquery.km0lab.com` (API domain)
- `http://localhost:5173` (Vite dev)
- `http://localhost:3000` (React dev)

**Development mode**: All origins allowed when `ENVIRONMENT=development`

**Allowed methods**: GET, POST, PUT, DELETE, OPTIONS

**Exposed headers**: Rate limit headers

### 5. Pagination

All list endpoints support pagination:
- `page`: Page number (starts at 1)
- `page_size`: Items per page (default 20, max 100)

**Response metadata**:
```json
{
  "data": [...],
  "total": 150,
  "page": 1,
  "page_size": 20,
  "total_pages": 8,
  "has_next": true,
  "has_prev": false
}
```

### 6. Default Filters

**Date filters** (for `/events` endpoint):
- Without `fecha_desde`: defaults to **today**
- Without `fecha_hasta`: defaults to **today + 30 days**

This ensures users see relevant upcoming events by default.

### 7. Error Handling

Consistent error responses:
- **400**: Invalid request parameters
- **404**: Resource not found
- **429**: Rate limit exceeded
- **500**: Internal server error

## File Structure

```
app/
├── api/
│   ├── v1/
│   │   ├── __init__.py
│   │   ├── router.py          # Main v1 router
│   │   ├── query.py           # Natural language search
│   │   ├── events.py          # Events endpoints
│   │   ├── categories.py      # Categories endpoint
│   │   └── health.py          # Health check
│   └── routes.py              # Legacy routes (kept for compatibility)
├── main.py                    # Updated with v1 router and rate limiting
└── ...
```

## Dependencies

New dependencies added:
- `slowapi==0.1.9` - Rate limiting
- `pydantic-settings==2.5.0` - Settings management

## Testing

### Local Testing (without MySQL)

The API structure can be validated without a database connection. To test with a database:

1. Set environment variables:
```bash
export ENVIRONMENT=local
export DB_HOST=localhost
export DB_PORT=3306
export DB_USER=root
export DB_PASSWORD=your_password
export DB_NAME=events_db
export OPENAI_API_KEY=your_key
```

2. Start the server:
```bash
python3.11 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

3. Access Swagger docs:
```
http://localhost:8000/docs
```

### Railway Deployment

1. **Environment variables** (set in Railway):
   - `ENVIRONMENT=production`
   - `DB_HOST=${{MySQL.MYSQLHOST}}`
   - `DB_PORT=${{MySQL.MYSQLPORT}}`
   - `DB_USER=${{MySQL.MYSQLUSER}}`
   - `DB_PASSWORD=${{MySQL.MYSQLPASSWORD}}`
   - `DB_NAME=${{MySQL.MYSQLDATABASE}}`
   - `OPENAI_API_KEY=your_key`

2. **Deploy**: Push to GitHub, Railway will auto-deploy

3. **Test endpoints**:
   - Health: `https://eventquery.km0lab.com/api/v1/health`
   - Docs: `https://eventquery.km0lab.com/docs`

## API Documentation

### Swagger UI
- **URL**: `https://eventquery.km0lab.com/docs`
- Interactive API documentation with examples
- Try endpoints directly from the browser

### ReDoc
- **URL**: `https://eventquery.km0lab.com/redoc`
- Alternative documentation view

### OpenAPI JSON
- **URL**: `https://eventquery.km0lab.com/openapi.json`
- Machine-readable API specification

## Frontend Integration

### Example: Fetch Today's Events

```javascript
const response = await fetch('https://eventquery.km0lab.com/api/v1/events/today');
const data = await response.json();

console.log(`Found ${data.total} events today:`, data.data);
```

### Example: Paginated Events List

```javascript
const page = 1;
const pageSize = 20;
const response = await fetch(
  `https://eventquery.km0lab.com/api/v1/events?page=${page}&page_size=${pageSize}&es_gratuito=true`
);
const data = await response.json();

console.log(`Page ${data.page} of ${data.total_pages}`);
console.log(`Events:`, data.data);
```

### Example: Natural Language Query

```javascript
const response = await fetch('https://eventquery.km0lab.com/api/v1/query', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    pregunta: '¿Qué hacer este fin de semana?',
    cp_usuario: '08380'
  })
});
const data = await response.json();

console.log(data.respuesta_texto);
console.log(`Found ${data.total} events:`, data.eventos);
```

### Rate Limit Handling

```javascript
const response = await fetch('https://eventquery.km0lab.com/api/v1/events/today');

// Check rate limit headers
const limit = response.headers.get('X-RateLimit-Limit');
const remaining = response.headers.get('X-RateLimit-Remaining');
const reset = response.headers.get('X-RateLimit-Reset');

console.log(`Rate limit: ${remaining}/${limit} remaining`);

if (response.status === 429) {
  console.error('Rate limit exceeded. Try again later.');
}
```

## Performance Optimizations

### 1. Database Indexes
Ensure indexes exist on:
- `EVENTOS_MASTER.Estado`
- `EVENTOS_MASTER.CP_Evento`
- `EVENTO_HORARIOS.Fecha_Inicio`
- `EVENTO_CATEGORIAS.ID_Categoria`

### 2. Caching Strategy
Recommended caching:
- `/events/today`: 5 minutes
- `/categories`: 1 hour
- `/events`: 1 minute (with query params as cache key)

### 3. Connection Pooling
Already configured in `database.py`:
- Min connections: 5
- Max connections: 20
- Auto-reconnect enabled

## Known Issues

### 1. Missing Embeddings
Events without embeddings will not appear in semantic search results. To fix:
```bash
python scripts/generate_embeddings.py
```

### 2. Similarity Threshold
Current threshold: 0.4 (reduced from 0.6). If search results are too broad, increase it.

## Next Steps

1. **Deploy to Railway**: Push changes and verify deployment
2. **Generate embeddings**: Run `generate_embeddings.py` for existing events
3. **Test frontend integration**: Update React app to use v1 endpoints
4. **Monitor rate limits**: Check if limits need adjustment based on usage
5. **Add caching**: Implement Redis or in-memory caching for frequently accessed endpoints

## Migration Guide

### For Frontend Developers

**Old endpoint** → **New endpoint**:
- `/query` → `/api/v1/query`
- `/health` → `/api/v1/health`
- `/events/simple` → `/api/v1/events` (with better pagination)
- `/events/list` → `/api/v1/events` (unified endpoint)

**New endpoints** (no equivalent before):
- `/api/v1/events/{id}` - Get single event details
- `/api/v1/events/today` - Today's events (optimized)
- `/api/v1/events/upcoming` - Upcoming events
- `/api/v1/categories` - List categories

### Breaking Changes
None. Old endpoints remain functional for backwards compatibility.

## Support

For questions or issues:
- Check Swagger docs: `https://eventquery.km0lab.com/docs`
- Review API specification: `ESPECIFICACION_API_DEFINITIVA.md`
- Contact: https://help.manus.im
