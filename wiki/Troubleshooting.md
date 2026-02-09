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

## Support

If issues persist, please open an issue on the GitHub repository.
