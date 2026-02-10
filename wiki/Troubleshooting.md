# Troubleshooting & Debugging

This page helps diagnose and fix common issues in the Data Insights Copilot.

## Common Issues

### 1. Database Connection Errors

- **Error**: `OperationalError: could not connect to server`
- **Cause**: PostgreSQL is not running or incorrect credentials.
- **Fix**:
    1.  Check if Postgres is running:
        ```bash
        docker ps | grep postgres
        ```
    2.  Verify credentials in `.env` match `docker-compose.yml`.

### 2. OpenAI API Errors

- **Error**: `RateLimitError` or `AuthenticationError`
- **Cause**: Invalid API key or quota exceeded.
- **Fix**:
    - Verify `OPENAI_API_KEY` is set correctly.
    - Check usage limits on OpenAI dashboard.

### 3. Frontend Build Failure

- **Error**: `Vite build failed`
- **Fix**:
    - Clear node_modules: `rm -rf node_modules && npm install`.
    - Check TypeScript errors: `npm run type-check`.

### 4. "No relevant documents found" (RAG)

- **Cause**: Vector store is empty or embeddings are corrupted.
- **Fix**:
    - Re-run ingestion via the configuration page.
    - Check logs for embedding failures.

### 5. "No active LLM provider configured"

- **Error**: `RuntimeError: No active LLM provider configured`
- **Cause**: LLM registry failed to initialize on startup.
- **Fix**:
    1. Check your LLM provider API key is set:
       ```bash
       echo $OPENAI_API_KEY  # Should not be empty
       ```
    2. Check database for valid LLM settings:
       ```bash
       sqlite3 backend/sqliteDb/app.db "SELECT * FROM system_settings WHERE category='llm';"
       ```
    3. Review backend logs for specific initialization errors.
    4. Try resetting LLM config via API:
       ```bash
       curl -X PUT http://localhost:8000/api/v1/settings/llm \
         -H "Authorization: Bearer $TOKEN" \
         -H "Content-Type: application/json" \
         -d '{"provider": "openai", "config": {"api_key": "your-key"}}'
       ```

### 6. Langfuse Tracing Not Working

- **Error**: No traces appearing in Langfuse dashboard
- **Cause**: Incorrect credentials or connection issues.
- **Fix**:
    1. Verify environment variables:
       ```bash
       echo $LANGFUSE_PUBLIC_KEY
       echo $LANGFUSE_SECRET_KEY
       echo $LANGFUSE_HOST
       ```
    2. Check Langfuse is running (if self-hosted):
       ```bash
       curl http://localhost:3001/api/public/health
       ```
    3. Look for initialization message in logs:
       ```
       ✅ Langfuse tracing enabled
       ```
    4. If using local Langfuse, ensure Docker containers are running:
       ```bash
       docker-compose -f docker-compose.langfuse.yml ps
       ```

### 7. "LangchainCallbackHandler unexpected keyword argument"

- **Error**: `LangchainCallbackHandler.__init__() got an unexpected keyword argument 'secret_key'`
- **Cause**: Langfuse v3.x API change - CallbackHandler no longer accepts direct credentials.
- **Fix**:
    1. Ensure langfuse v3.x is installed: `pip install langfuse>=3.0.0`
    2. Set credentials via environment variables (not constructor args):
       ```bash
       export LANGFUSE_PUBLIC_KEY=pk-lf-...
       export LANGFUSE_SECRET_KEY=sk-lf-...
       export LANGFUSE_HOST=http://localhost:3001
       ```
    3. The code should use `CallbackHandler()` with no arguments.

## Debugging

### Checking Logs

- **Backend**:
    ```bash
    docker logs fhir_rag_backend
    # or local
    tail -f backend/logs/backend.log
    ```

- **Frontend**:
    Check browser console (F12) for network errors.

### Enabling Debug Logging

Set log level to DEBUG for verbose output:

```bash
# In .env
LOG_LEVEL=DEBUG

# Or via API (requires admin)
curl -X PUT http://localhost:8000/api/v1/observability/config \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"log_level": "DEBUG"}'
```

### Testing Observability

Emit a test log to verify logging is working:

```bash
curl -X POST "http://localhost:8000/api/v1/observability/test-log?level=INFO&message=Test" \
  -H "Authorization: Bearer $TOKEN"
```

### Inspecting Langfuse Traces

1. Open Langfuse dashboard: http://localhost:3001
2. Navigate to **Traces** tab
3. Filter by time range or session ID
4. Click a trace to see full call chain, tokens, and latency

## Support

If issues persist, please open an issue on the GitHub repository with:
- Error message and stack trace
- Relevant log excerpts
- Environment details (OS, Python version, package versions)

## Related Documentation

- [Observability & Tracing](Observability.md)
- [Backend Architecture](Backend.md)
- [Deployment Guide](Deployment.md)
