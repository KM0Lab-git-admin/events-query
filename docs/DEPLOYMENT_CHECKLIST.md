# Deployment Checklist - API v1

## Pre-Deployment

### 1. Code Review
- [x] API v1 structure implemented
- [x] Rate limiting configured
- [x] CORS configured for production domains
- [x] Pagination implemented
- [x] Error handling standardized
- [x] Swagger documentation complete
- [ ] Code reviewed by team
- [ ] Tests passed (if applicable)

### 2. GitHub
- [x] Branch created: `feature/api-v1-optimized`
- [x] Changes committed
- [x] Changes pushed to GitHub
- [ ] Pull request created
- [ ] Pull request reviewed
- [ ] Pull request merged to `develop`

## Railway Deployment

### 3. Environment Variables
Verify these are set in Railway:

- [ ] `ENVIRONMENT=production`
- [ ] `DB_HOST=${{MySQL.MYSQLHOST}}`
- [ ] `DB_PORT=${{MySQL.MYSQLPORT}}`
- [ ] `DB_USER=${{MySQL.MYSQLUSER}}`
- [ ] `DB_PASSWORD=${{MySQL.MYSQLPASSWORD}}`
- [ ] `DB_NAME=${{MySQL.MYSQLDATABASE}}`
- [ ] `OPENAI_API_KEY=sk-...` (your key)

### 4. Dependencies
- [x] `slowapi==0.1.9` added to requirements.txt
- [ ] Railway will auto-install on deployment

### 5. Deploy
- [ ] Merge PR to `develop` branch
- [ ] Railway auto-deploys from `develop`
- [ ] Wait for deployment to complete
- [ ] Check Railway logs for errors

## Post-Deployment Testing

### 6. Health Check
Test the health endpoint:
```bash
curl https://eventquery.km0lab.com/api/v1/health
```

Expected response:
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": "2026-02-06T...",
  "checks": {
    "database": "healthy",
    "openai": "configured",
    "api": "healthy"
  }
}
```

### 7. API Documentation
- [ ] Access Swagger UI: https://eventquery.km0lab.com/docs
- [ ] Verify all v1 endpoints are listed
- [ ] Test each endpoint from Swagger UI

### 8. Test Endpoints

#### Test /api/v1/events/today
```bash
curl https://eventquery.km0lab.com/api/v1/events/today
```

#### Test /api/v1/events with pagination
```bash
curl "https://eventquery.km0lab.com/api/v1/events?page=1&page_size=20"
```

#### Test /api/v1/categories
```bash
curl https://eventquery.km0lab.com/api/v1/categories
```

#### Test /api/v1/events/{id}
```bash
curl https://eventquery.km0lab.com/api/v1/events/evt_123
```

#### Test /api/v1/query
```bash
curl -X POST https://eventquery.km0lab.com/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"pregunta": "¿Qué hacer este fin de semana?", "cp_usuario": "08380"}'
```

### 9. Rate Limiting
- [ ] Test rate limits by making multiple requests
- [ ] Verify `X-RateLimit-*` headers are present
- [ ] Verify 429 response when limit exceeded

### 10. CORS
- [ ] Test from React app on `app.km0lab.com`
- [ ] Verify no CORS errors in browser console
- [ ] Test preflight OPTIONS requests

## Data Migration

### 11. Generate Embeddings
**CRITICAL**: Events need embeddings for semantic search to work.

```bash
# SSH into Railway or run locally with production DB credentials
python scripts/generate_embeddings.py
```

This will:
- Generate embeddings for all events without them
- Update `Tags_Embedding_ES` field in database
- Enable semantic search functionality

**Estimated time**: 5-10 minutes for 200 events

### 12. Verify Embeddings
```bash
# Check if events have embeddings
mysql -h $DB_HOST -u $DB_USER -p$DB_PASSWORD $DB_NAME \
  -e "SELECT COUNT(*) as total, 
      SUM(CASE WHEN Tags_Embedding_ES IS NOT NULL THEN 1 ELSE 0 END) as with_embeddings 
      FROM EVENTOS_MASTER WHERE Estado='ACTIVO';"
```

Expected: `total` = `with_embeddings`

## Frontend Integration

### 13. Update React App
Update frontend to use v1 endpoints:

**Old**:
```javascript
fetch('https://eventquery.km0lab.com/query', ...)
```

**New**:
```javascript
fetch('https://eventquery.km0lab.com/api/v1/query', ...)
```

### 14. Test Frontend
- [ ] Deploy updated React app to Vercel
- [ ] Test all API calls from frontend
- [ ] Verify no CORS errors
- [ ] Test pagination UI
- [ ] Test rate limit handling

## Monitoring

### 15. Check Logs
- [ ] Railway logs show no errors
- [ ] API responds within acceptable time (<500ms for most endpoints)
- [ ] No database connection issues

### 16. Performance
- [ ] Test response times for each endpoint
- [ ] Monitor rate limit usage
- [ ] Check database query performance

### 17. Error Tracking
- [ ] Set up error monitoring (optional: Sentry, LogRocket)
- [ ] Monitor 4xx and 5xx responses
- [ ] Track rate limit violations

## Rollback Plan

If issues occur:

1. **Revert deployment**:
   ```bash
   git revert <commit-hash>
   git push origin develop
   ```

2. **Railway will auto-deploy the revert**

3. **Update frontend** to use old endpoints temporarily

4. **Investigate and fix** issues

5. **Re-deploy** when ready

## Success Criteria

- [ ] All endpoints respond correctly
- [ ] Rate limiting works as expected
- [ ] CORS configured for production domains
- [ ] Swagger documentation accessible
- [ ] Embeddings generated for all events
- [ ] Frontend integrated successfully
- [ ] No errors in Railway logs
- [ ] Response times acceptable

## Notes

- **Backwards compatibility**: Old endpoints (`/query`, `/health`) still work
- **Migration strategy**: Gradual migration from old to new endpoints
- **Caching**: Consider adding Redis for `/events/today` and `/categories`
- **Monitoring**: Set up alerts for high error rates or slow responses

## Contact

For issues or questions:
- Railway logs: https://railway.app
- GitHub: https://github.com/KM0Lab-git-admin/events-query
- Support: https://help.manus.im
