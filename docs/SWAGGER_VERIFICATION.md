# Swagger Documentation Verification

## Issue Reported

User reported that API v1 endpoints (like `/api/v1/events/today`) were not appearing in Swagger documentation when accessing `http://localhost:8000/docs`.

## Root Cause

The user was viewing Swagger documentation from an **old version** of the code or the server wasn't restarted after pulling the new `feature/api-v1-optimized` branch.

## Verification

We created a verification script to confirm all endpoints are correctly registered:

```bash
python scripts/verify_api_v1.py
```

**Result**: ✅ All 7 API v1 endpoints are correctly registered and will appear in Swagger.

## Confirmed Endpoints

The following endpoints are correctly configured and will appear in Swagger:

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/query` | Search events with natural language |
| GET | `/api/v1/events` | List events with filters and pagination |
| GET | `/api/v1/events/{event_id}` | Get event details |
| GET | `/api/v1/events/today` | Get today's events |
| GET | `/api/v1/events/upcoming` | Get upcoming events |
| GET | `/api/v1/categories` | List event categories |
| GET | `/api/v1/health` | Health check |

## How to View Swagger Documentation

### After Railway Deployment

Once the `feature/api-v1-optimized` branch is merged and deployed to Railway:

1. **Access Swagger UI**:
   ```
   https://eventquery.km0lab.com/docs
   ```

2. **All 7 endpoints will be visible** organized by tags:
   - **Query** - Natural language search
   - **Events** - Event listing and details (4 endpoints)
   - **Categories** - Category listing
   - **Health** - Health check

### Local Testing (with MySQL)

If you have MySQL running locally:

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
   cd /tmp/events-query
   python3.11 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

3. Access Swagger:
   ```
   http://localhost:8000/docs
   ```

## Swagger Features

Each endpoint in Swagger includes:

- ✅ **Detailed description** of what the endpoint does
- ✅ **Request parameters** with types and descriptions
- ✅ **Request body schema** (for POST endpoints)
- ✅ **Response examples** showing expected output
- ✅ **Error responses** (400, 404, 429, 500)
- ✅ **Rate limit information** in the description
- ✅ **"Try it out" button** to test endpoints directly

## Example: Testing from Swagger UI

1. Go to `https://eventquery.km0lab.com/docs`
2. Click on **GET /api/v1/events/today**
3. Click **"Try it out"**
4. Click **"Execute"**
5. See the response with today's events

## Troubleshooting

### "I don't see the v1 endpoints in Swagger"

**Possible causes**:

1. **Wrong branch**: Make sure you're on `feature/api-v1-optimized`
   ```bash
   git branch --show-current
   ```

2. **Server not restarted**: Restart the FastAPI server after pulling changes

3. **Cached browser**: Hard refresh the page (Ctrl+Shift+R or Cmd+Shift+R)

4. **Old deployment**: If viewing Railway deployment, make sure the new branch is deployed

### "I see duplicate endpoints"

This might happen if both old and new routers are included. Check `app/main.py` to ensure only `v1_router` is included:

```python
# Correct:
app.include_router(v1_router)

# Wrong (don't include both):
app.include_router(v1_router)
app.include_router(legacy_router)  # Remove this
```

## Verification Script

Run the verification script anytime to confirm endpoints are correctly registered:

```bash
cd /tmp/events-query
ENVIRONMENT=local python3.11 scripts/verify_api_v1.py
```

Expected output:
```
✅ SUCCESS: All expected endpoints are correctly registered!
✅ Swagger documentation will show all 7 API v1 endpoints.
```

## Next Steps

1. **Merge PR** to `develop` branch
2. **Deploy to Railway**
3. **Access Swagger** at `https://eventquery.km0lab.com/docs`
4. **Verify** all 7 endpoints appear correctly
5. **Share documentation URL** with your team

## Documentation URLs

After deployment, share these URLs with your team:

- **Interactive Swagger UI**: https://eventquery.km0lab.com/docs
- **ReDoc (alternative view)**: https://eventquery.km0lab.com/redoc
- **OpenAPI JSON (for Postman)**: https://eventquery.km0lab.com/openapi.json

## Conclusion

All API v1 endpoints are correctly implemented and will appear in Swagger documentation once deployed. The verification script confirms this.

The issue the user experienced was due to viewing documentation from an old version of the code. After deployment of the `feature/api-v1-optimized` branch, all endpoints will be visible and fully documented.
