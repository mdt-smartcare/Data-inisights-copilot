# Observability & Tracing

This guide covers the observability features in Data Insights Copilot, including LLM tracing with Langfuse, logging configuration, and usage tracking.

## Overview

The observability system provides:
- **LLM Tracing**: Track all LLM calls, tokens, latency, and costs via Langfuse
- **Structured Logging**: Configurable log levels and destinations
- **Usage Metrics**: Token consumption and cost tracking per request
- **Distributed Tracing**: OpenTelemetry support (optional)

## Architecture

```mermaid
graph TD
    User[User Request] --> API[FastAPI Backend]
    API --> Agent[Agent Service]
    Agent --> LLM[LLM Provider]
    
    LLM -->|Callback| Langfuse[Langfuse Tracing]
    Agent -->|@observe| Langfuse
    
    Langfuse --> Dashboard[Langfuse Dashboard]
    
    API --> Logger[Structured Logger]
    Logger --> Console[Console Output]
    Logger --> File[Log Files]
```

## Langfuse Integration

[Langfuse](https://langfuse.com) is an open-source LLM observability platform that provides detailed insights into your AI application.

### Features
- **Traces**: Full request/response chains with timing
- **Generations**: Individual LLM calls with token counts
- **Costs**: Estimated costs per model and request
- **Scores**: User feedback and quality metrics
- **Datasets**: Collect examples for fine-tuning

### Local Setup (Self-Hosted)

We recommend running Langfuse locally for development. A Docker Compose file is included:

```bash
# Start Langfuse locally
docker-compose -f docker-compose.langfuse.yml up -d

# View logs
docker-compose -f docker-compose.langfuse.yml logs -f

# Stop Langfuse
docker-compose -f docker-compose.langfuse.yml down
```

**Access Points:**
| Service | URL |
|---------|-----|
| Langfuse UI | http://localhost:3001 |
| Langfuse API | http://localhost:3001/api |

### Initial Configuration

1. **Open Langfuse UI**: http://localhost:3001
2. **Create Account**: Click "Sign Up" and register
3. **Create Project**: Name it "Data Insights Copilot"
4. **Generate API Keys**: Settings → API Keys → Create New

### Environment Variables

Add these to your `.env` file:

```bash
# Langfuse Tracing
ENABLE_LANGFUSE=true
LANGFUSE_PUBLIC_KEY=pk-lf-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
LANGFUSE_SECRET_KEY=sk-lf-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
LANGFUSE_HOST=http://localhost:3001
```

For cloud-hosted Langfuse:
```bash
LANGFUSE_HOST=https://cloud.langfuse.com
```

### How Tracing Works

The system automatically traces LLM calls using two mechanisms:

#### 1. Decorator-Based Tracing
Key operations are decorated with `@observe`:

```python
from langfuse import observe

@observe(as_type="generation")
def embed_documents(self, texts: List[str]) -> List[List[float]]:
    # Embedding calls are traced automatically
    ...

@observe(as_type="span")
def search(self, query: str, top_k: int) -> List[Document]:
    # Vector searches are traced
    ...
```

#### 2. LangChain Callback Integration
LLM providers automatically attach the Langfuse callback:

```python
# In LLMRegistry.get_langchain_llm()
llm = provider.get_langchain_llm()
callback = tracer.get_langchain_callback()
if callback:
    llm.callbacks = [callback]
```

### Viewing Traces

Once configured, traces appear in the Langfuse dashboard:

1. **Traces View**: See all request chains
2. **Generations**: Filter by model, view token usage
3. **Metrics**: Latency percentiles, cost breakdowns
4. **Sessions**: Group traces by user session

## Logging Configuration

### Log Levels

| Level | Description |
|-------|-------------|
| `DEBUG` | Detailed diagnostic information |
| `INFO` | General operational messages |
| `WARNING` | Unexpected but handled situations |
| `ERROR` | Errors that need attention |
| `CRITICAL` | System failures |

### Configuration via Settings API

```bash
# Get current observability config
GET /api/v1/observability/config

# Update log level
PUT /api/v1/observability/config
{
  "log_level": "DEBUG",
  "log_destinations": ["console", "file"]
}

# Test logging
POST /api/v1/observability/test-log?level=INFO&message=Test%20message
```

### Log Destinations

Logs can be sent to multiple destinations:
- **Console**: Standard output (default)
- **File**: `logs/backend.log` with rotation
- **Structured JSON**: Machine-readable format

### Log File Rotation

Default settings (configurable in database):
- **Max Size**: 100 MB per file
- **Backup Count**: 5 rotated files

## Usage Metrics

Track token consumption and costs across your application.

### Metrics Tracked

| Metric | Description |
|--------|-------------|
| `total_tokens` | Input + output tokens |
| `prompt_tokens` | Tokens in the prompt |
| `completion_tokens` | Tokens in the response |
| `latency_ms` | Request duration |
| `estimated_cost_usd` | Cost based on model pricing |

### Querying Usage Stats

```bash
# Get usage for last 24 hours
GET /api/v1/observability/usage?period=24h

# Available periods: 1h, 24h, 7d, 30d
```

**Response:**
```json
{
  "period": "24h",
  "total_llm_calls": 156,
  "total_tokens": 89420,
  "prompt_tokens": 67890,
  "completion_tokens": 21530,
  "estimated_cost_usd": 4.52,
  "avg_latency_ms": 1234,
  "by_model": {
    "gpt-4o": { "calls": 120, "tokens": 75000, "cost": 3.75 },
    "gpt-3.5-turbo": { "calls": 36, "tokens": 14420, "cost": 0.77 }
  }
}
```

## Frontend Observability Panel

The admin dashboard includes an Observability panel at **Settings → Observability**.

### Features
- Toggle Langfuse tracing on/off
- Configure log level and destinations
- View real-time usage statistics
- Test log emission
- Link to Langfuse dashboard

## Database Schema

Observability settings are stored in the `system_settings` table:

```sql
-- Key observability settings
INSERT INTO system_settings (category, key, value) VALUES
('observability', 'log_level', '"INFO"'),
('observability', 'langfuse_enabled', 'false'),
('observability', 'tracing_provider', '"langfuse"'),
('observability', 'log_destinations', '["console", "file"]');
```

Usage metrics are stored in the `usage_metrics` table:

```sql
CREATE TABLE usage_metrics (
    id INTEGER PRIMARY KEY,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    user_id INTEGER,
    session_id TEXT,
    trace_id TEXT,
    model_name TEXT,
    provider TEXT,
    operation_type TEXT,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    total_tokens INTEGER,
    latency_ms INTEGER,
    estimated_cost_usd REAL,
    success BOOLEAN,
    error_message TEXT
);
```

## Troubleshooting

### Langfuse Not Receiving Traces

1. **Check credentials**: Verify `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY`
2. **Check host**: Ensure `LANGFUSE_HOST` is correct (include `http://`)
3. **Check connection**: 
   ```bash
   curl http://localhost:3001/api/public/health
   ```
4. **Check logs**: Look for Langfuse initialization messages:
   ```
   ✅ Langfuse tracing enabled
   ```

### "No active LLM provider configured"

This error occurs when the LLM registry cannot initialize:
1. Check `OPENAI_API_KEY` or other provider credentials
2. Verify database has valid LLM settings
3. Check logs for specific initialization errors

### High Latency in Traces

1. Check network connectivity to LLM provider
2. Review token counts (large prompts = slow)
3. Consider using a faster model for non-critical operations

## OpenTelemetry (Advanced)

For distributed tracing across microservices, OpenTelemetry support is available:

```bash
# Enable OTEL (in .env)
OPENTELEMETRY_ENABLED=true
OTLP_ENDPOINT=http://localhost:4317
```

This sends traces to any OTLP-compatible backend (Jaeger, Zipkin, etc.).

## Best Practices

1. **Development**: Enable `DEBUG` logging, use local Langfuse
2. **Staging**: Use `INFO` logging, cloud Langfuse with separate project
3. **Production**: Use `WARNING` logging, enable cost alerts in Langfuse
4. **Cost Control**: Set up usage alerts, review expensive traces
5. **Privacy**: Avoid logging PII in traces, use Langfuse's masking features

## Related Documentation

- [Backend Architecture](Backend.md)
- [API Reference](API.md)
- [Deployment Guide](Deployment.md)
- [Troubleshooting](Troubleshooting.md)
