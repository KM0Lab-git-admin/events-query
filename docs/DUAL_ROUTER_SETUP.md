# Dual Router Setup - Legacy + API v1

## Overview

The backend now supports **both** legacy routes and new API v1 routes simultaneously. This allows:

1. **PoC Frontend** (local development) to continue using legacy endpoints
2. **Production Frontend** to use new optimized v1 endpoints
3. **Gradual migration** without breaking existing integrations

## Router Configuration

### Legacy Routes (Backwards Compatibility)

These routes are available for the PoC frontend:

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/query` | Natural language search (legacy) |
| GET | `/health` | Health check (legacy) |
| GET | `/api/info` | API information |
| GET | `/events/simple` | Simple event list |
| GET | `/events/list` | Event list with filters |
| GET | `/events/categorias` | List categories |
| GET | `/events/poblaciones` | List towns |

### API v1 Routes (Production)

These routes are for production frontend:

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/query` | Natural language search |
| GET | `/api/v1/health` | Health check |
| GET | `/api/v1/events` | Paginated event list with filters |
| GET | `/api/v1/events/{id}` | Single event details |
| GET | `/api/v1/events/today` | Today's events (optimized) |
| GET | `/api/v1/events/upcoming` | Upcoming events |
| GET | `/api/v1/categories` | List categories with counts |

## Swagger Documentation

Both sets of routes appear in Swagger UI (`/docs`):

- **Legacy** tag - Old endpoints for backwards compatibility
- **Query**, **Events**, **Categories**, **Health** tags - New v1 endpoints

## Frontend Integration

### PoC Frontend (Local)

Your current PoC frontend can continue using legacy routes:

```javascript
// These will work with the dual router setup
fetch('/events/list?limit=20')
fetch('/events/categorias')
fetch('/events/poblaciones')
fetch('/query', { method: 'POST', body: ... })
```

### Production Frontend (Vercel)

Production frontend should use v1 routes:

```javascript
// Use these for production
fetch('/api/v1/events?page=1&page_size=20')
fetch('/api/v1/categories')
fetch('/api/v1/query', { method: 'POST', body: ... })
```

## Starting the Backend

### Option 1: Using start.ps1 (Windows)

```powershell
.\start.ps1
```

This will:
1. Start MySQL (if not running)
2. Start the API on port 8000
3. Start the frontend on port 5173

### Option 2: Manual Start

```bash
# Activate virtual environment
source venv/bin/activate  # Linux/Mac
# or
.\venv\Scripts\activate  # Windows

# Start the API
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Option 3: Environment Variables

```bash
# Set environment
export ENVIRONMENT=local
export DB_HOST=localhost
export DB_PORT=3306
export DB_USER=root
export DB_PASSWORD=your_password
export DB_NAME=events_db
export OPENAI_API_KEY=your_key

# Start server
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Verification

Run the verification script to confirm both routers are mounted:

```bash
cd /tmp/events-query
ENVIRONMENT=local python scripts/verify_api_v1.py
```

Expected output:
```
📦 Legacy Routes (for PoC frontend): 7
🚀 API v1 Routes (for production): 7
✅ Both routers are mounted successfully!
```

## Troubleshooting

### ECONNREFUSED Error

**Cause**: Backend is not running

**Solution**:
1. Make sure MySQL is running
2. Start the backend with `.\start.ps1` or manually with uvicorn
3. Check that the API is listening on port 8000

### 404 Not Found

**Cause**: Using wrong endpoint path

**Solution**:
- PoC frontend: Use `/events/list`, `/events/categorias`, etc.
- Production frontend: Use `/api/v1/events`, `/api/v1/categories`, etc.

### Routes Not Appearing in Swagger

**Cause**: Server not restarted after code changes

**Solution**:
1. Stop the server (Ctrl+C)
2. Restart with `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
3. Access `/docs` again

## Migration Strategy

### Phase 1: Dual Router (Current)
- ✅ Both legacy and v1 routes available
- PoC frontend uses legacy routes
- Production frontend uses v1 routes

### Phase 2: Frontend Migration
- Update PoC frontend to use v1 routes
- Test thoroughly
- Deploy updated frontend

### Phase 3: Deprecate Legacy
- Remove legacy router from `main.py`
- Keep only v1 routes
- Cleaner codebase

## Code Changes

### main.py

```python
# Import both routers
from app.api.v1.router import router as v1_router
from app.api.routes import router as legacy_router

# Include both routers
app.include_router(v1_router)                          # API v1
app.include_router(legacy_router, tags=["Legacy"])    # Legacy
```

## Benefits

✅ **No breaking changes** - PoC frontend continues working
✅ **Production ready** - v1 API ready for deployment
✅ **Gradual migration** - Update frontend at your own pace
✅ **Clear separation** - Legacy vs v1 routes clearly marked
✅ **Full documentation** - Both sets appear in Swagger

## Next Steps

1. **Start backend**: `.\start.ps1` or manually with uvicorn
2. **Test PoC frontend**: Should work with legacy routes
3. **Test v1 endpoints**: Access `/docs` and try v1 routes
4. **Plan migration**: Update frontend to use v1 routes gradually
5. **Deploy to Railway**: Both routers will be available in production

## Notes

- Legacy routes will be **deprecated** once frontend is migrated
- v1 routes include **rate limiting** and **optimizations**
- Production frontend should **only** use v1 routes
- PoC frontend can use legacy routes **temporarily**

## Support

If you encounter issues:
1. Check that MySQL is running
2. Verify backend is listening on port 8000
3. Check Swagger docs at `http://localhost:8000/docs`
4. Review logs for errors
