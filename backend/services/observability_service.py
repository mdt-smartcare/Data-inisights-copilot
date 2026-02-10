"""
Observability Service for Data Insights Copilot.

Uses Langfuse as the single source of truth for:
- Usage metrics and cost tracking
- Trace data and latency
- Model usage statistics

Also manages:
- Runtime log level configuration
- Tracing provider toggling
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import httpx

from backend.config import get_settings
from backend.core.logging import get_logger
from backend.services.settings_service import get_settings_service

settings = get_settings()
logger = get_logger(__name__)


class LangfuseClient:
    """Client for Langfuse API to fetch observability metrics."""
    
    def __init__(self):
        self.host = settings.langfuse_host.rstrip('/')
        self.public_key = settings.langfuse_public_key
        self.secret_key = settings.langfuse_secret_key
        self.enabled = bool(settings.enable_langfuse and self.public_key and self.secret_key)
        
        # Log initialization for debugging
        logger.info(f"LangfuseClient initialized: host={self.host}, enabled={self.enabled}, "
                   f"has_public_key={bool(self.public_key)}, has_secret_key={bool(self.secret_key)}")
        
    def _get_auth(self) -> tuple:
        """Get HTTP Basic Auth tuple for httpx."""
        return (self.public_key, self.secret_key)
    
    async def get_traces(self, 
                         limit: int = 100, 
                         offset: int = 0,
                         from_timestamp: Optional[datetime] = None,
                         to_timestamp: Optional[datetime] = None) -> Dict[str, Any]:
        """Fetch traces from Langfuse API."""
        if not self.enabled:
            return {"data": [], "meta": {"totalItems": 0}}
            
        try:
            params = {"limit": limit, "offset": offset}
            if from_timestamp:
                params["fromTimestamp"] = from_timestamp.strftime("%Y-%m-%dT%H:%M:%S.000Z")
            if to_timestamp:
                params["toTimestamp"] = to_timestamp.strftime("%Y-%m-%dT%H:%M:%S.000Z")
                
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.host}/api/public/traces",
                    auth=self._get_auth(),
                    params=params
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Failed to fetch traces from Langfuse: {e}")
            return {"data": [], "meta": {"totalItems": 0}}
    
    async def get_observations(self,
                               limit: int = 100,
                               offset: int = 0,
                               type: Optional[str] = None,
                               from_timestamp: Optional[datetime] = None) -> Dict[str, Any]:
        """Fetch observations (generations, spans) from Langfuse API."""
        if not self.enabled:
            return {"data": [], "meta": {"totalItems": 0}}
            
        try:
            # Langfuse API limits to 100 per request
            actual_limit = min(limit, 100)
            params = {"limit": actual_limit}
            if offset:
                params["offset"] = offset
            
            logger.debug(f"Fetching observations from {self.host}/api/public/observations with params={params}")
                
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.host}/api/public/observations",
                    auth=self._get_auth(),
                    params=params
                )
                
                if response.status_code != 200:
                    logger.error(f"Langfuse observations API returned {response.status_code}: {response.text[:500]}")
                    return {"data": [], "meta": {"totalItems": 0}}
                    
                result = response.json()
                logger.debug(f"Observations API returned {len(result.get('data', []))} items")
                
                # Filter by type client-side if needed
                if type:
                    result["data"] = [
                        obs for obs in result.get("data", [])
                        if obs.get("type") == type
                    ]
                    
                return result
        except Exception as e:
            logger.error(f"Failed to fetch observations from Langfuse: {e}")
            return {"data": [], "meta": {"totalItems": 0}}
    
    async def get_daily_metrics(self, 
                                from_timestamp: Optional[datetime] = None,
                                to_timestamp: Optional[datetime] = None) -> Dict[str, Any]:
        """Fetch daily metrics from Langfuse API."""
        if not self.enabled:
            return {"data": []}
            
        try:
            params = {}
            if from_timestamp:
                params["fromTimestamp"] = from_timestamp.strftime("%Y-%m-%dT%H:%M:%S.000Z")
            if to_timestamp:
                params["toTimestamp"] = to_timestamp.strftime("%Y-%m-%dT%H:%M:%S.000Z")
                
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.host}/api/public/metrics/daily",
                    auth=self._get_auth(),
                    params=params
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Failed to fetch daily metrics from Langfuse: {e}")
            return {"data": []}
    
    async def get_model_usage(self, 
                              from_timestamp: Optional[datetime] = None,
                              to_timestamp: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Fetch model usage statistics by paginating through observations."""
        if not self.enabled:
            return []
            
        try:
            logger.debug(f"Fetching model usage from Langfuse")
            
            # Paginate to get all observations (Langfuse limits to 100 per request)
            all_observations = []
            offset = 0
            page_size = 100
            max_pages = 10  # Safety limit: max 1000 observations
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                for _ in range(max_pages):
                    response = await client.get(
                        f"{self.host}/api/public/observations",
                        auth=self._get_auth(),
                        params={"limit": page_size, "offset": offset}
                    )
                    
                    if response.status_code != 200:
                        logger.error(f"Langfuse observations API returned {response.status_code}: {response.text[:500]}")
                        break
                        
                    data = response.json()
                    page_data = data.get("data", [])
                    all_observations.extend(page_data)
                    
                    # Check if we got all data
                    if len(page_data) < page_size:
                        break
                    offset += page_size
                
            logger.debug(f"Got {len(all_observations)} total observations for model usage")
                
            # Aggregate by model, filtering by timestamp and type client-side
            model_stats = {}
            generation_count = 0
            for obs in all_observations:
                # Only process GENERATION type
                if obs.get("type") != "GENERATION":
                    continue
                
                generation_count += 1
                    
                # Filter by timestamp if provided
                if from_timestamp:
                    obs_time = obs.get("startTime")
                    if obs_time:
                        try:
                            obs_dt = datetime.fromisoformat(obs_time.replace("Z", "+00:00"))
                            if obs_dt < from_timestamp.replace(tzinfo=obs_dt.tzinfo):
                                continue
                        except (ValueError, AttributeError):
                            pass
                
                # Get model name from metadata if not in model field
                model = obs.get("model")
                if not model:
                    metadata = obs.get("metadata") or {}
                    model = metadata.get("ls_model_name") or "unknown"
                    
                if model not in model_stats:
                    model_stats[model] = {
                        "model": model,
                        "calls": 0,
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "total_tokens": 0,
                        "total_cost": 0.0,
                        "avg_latency_ms": 0,
                        "latencies": []
                    }
                
                stats = model_stats[model]
                stats["calls"] += 1
                
                # Token usage - handle both old and new format
                usage = obs.get("usageDetails") or obs.get("usage") or {}
                stats["input_tokens"] += usage.get("input", 0) or 0
                stats["output_tokens"] += usage.get("output", 0) or 0
                stats["total_tokens"] += usage.get("total", 0) or 0
                
                # Cost (Langfuse calculates this)
                cost_details = obs.get("costDetails") or {}
                stats["total_cost"] += cost_details.get("total", 0) or 0
                
                # Latency (in seconds, convert to ms)
                if obs.get("latency"):
                    stats["latencies"].append(obs["latency"] * 1000)
            
            logger.info(f"Found {generation_count} GENERATION observations, {len(model_stats)} unique models")
            
            # Calculate average latencies
            for model, stats in model_stats.items():
                if stats["latencies"]:
                    stats["avg_latency_ms"] = sum(stats["latencies"]) / len(stats["latencies"])
                del stats["latencies"]  # Remove raw data
                
            return list(model_stats.values())
            
        except Exception as e:
            logger.error(f"Failed to fetch model usage from Langfuse: {e}")
            return []


class ObservabilityService:
    """Service for managing observability configuration and fetching metrics from Langfuse."""
    
    def __init__(self):
        self.settings_service = get_settings_service()
        self.langfuse_client = LangfuseClient()
        
    async def get_config(self) -> Dict[str, Any]:
        """Get current observability configuration."""
        try:
            obs_settings = self.settings_service.get_category_settings("observability")
            return obs_settings
        except Exception as e:
            logger.warning(f"Could not load observability settings: {e}")
            return {
                "log_level": settings.log_level,
                "langfuse_enabled": settings.enable_langfuse,
                "langfuse_host": settings.langfuse_host,
                "tracing_provider": "langfuse" if settings.enable_langfuse else "none",
                "log_destinations": ["console"]
            }
        
    async def update_config(self, updates: Dict[str, Any], updated_by: str = "system") -> Dict[str, Any]:
        """Update observability configuration and apply changes immediately."""
        try:
            current = await self.get_config()
            merged = {**current, **updates}
            
            for key, value in updates.items():
                self.settings_service.update_setting("observability", key, value, updated_by)
            
            self._apply_runtime_changes(updates)
            return merged
        except Exception as e:
            logger.error(f"Failed to update observability config: {e}")
            raise

    def _apply_runtime_changes(self, changes: Dict[str, Any]):
        """Apply configuration changes to running application."""
        if 'log_level' in changes:
            new_level = changes['log_level']
            logging.getLogger().setLevel(new_level)
            logger.info(f"Log level changed to {new_level}")
            
        if 'tracing_provider' in changes or 'langfuse_enabled' in changes:
            try:
                from backend.core.tracing import get_tracing_manager
                tm = get_tracing_manager()
                
                if 'langfuse_enabled' in changes:
                    tm.langfuse_enabled = changes['langfuse_enabled']
                    
                if 'tracing_provider' in changes:
                    provider = changes['tracing_provider']
                    tm.langfuse_enabled = provider in ['langfuse', 'both']
                    tm.otel_enabled = provider in ['opentelemetry', 'both']
                    
                logger.info("Tracing configuration updated")
            except Exception as e:
                logger.warning(f"Could not update tracing config: {e}")

    async def track_usage(self, 
                          operation: str,
                          model: str = None,
                          input_tokens: int = 0,
                          output_tokens: int = 0,
                          latency_ms: float = 0,
                          cost: float = 0,
                          metadata: Dict[str, Any] = None) -> None:
        """
        Track usage metrics. 
        
        Note: With Langfuse as the source of truth, this is a no-op since
        Langfuse automatically tracks all LLM calls via the callback handler.
        This method exists for backward compatibility with code that calls it.
        """
        # Langfuse automatically tracks usage via the callback handler
        # This method is kept for backward compatibility
        logger.debug(f"Usage tracked (via Langfuse): operation={operation}, model={model}, "
                    f"tokens={input_tokens + output_tokens}, latency={latency_ms}ms")

    async def get_usage_stats(self, period: str = "24h") -> Dict[str, Any]:
        """
        Get aggregated usage statistics from Langfuse.
        
        Args:
            period: Time period ('1h', '24h', '7d', '30d')
            
        Returns:
            Aggregated stats dictionary
        """
        # Calculate time range
        now = datetime.utcnow()
        if period == "1h":
            from_time = now - timedelta(hours=1)
        elif period == "24h":
            from_time = now - timedelta(hours=24)
        elif period == "7d":
            from_time = now - timedelta(days=7)
        elif period == "30d":
            from_time = now - timedelta(days=30)
        else:
            from_time = now - timedelta(hours=24)
        
        stats = {
            "period": period,
            "from_timestamp": from_time.isoformat(),
            "to_timestamp": now.isoformat(),
            "langfuse_enabled": self.langfuse_client.enabled,
            "langfuse_host": settings.langfuse_host,
            "summary": {
                "total_traces": 0,
                "total_observations": 0,
                "total_generations": 0,
                "total_cost": 0.0,
                "total_tokens": 0
            },
            "by_model": [],
            "by_operation": {
                "llm": {"calls": 0, "tokens": 0, "cost": 0.0, "avg_latency_ms": 0},
                "embedding": {"calls": 0, "tokens": 0, "cost": 0.0, "avg_latency_ms": 0},
                "retrieval": {"calls": 0, "tokens": 0, "cost": 0.0, "avg_latency_ms": 0}
            },
            "latency_percentiles": {
                "p50": 0,
                "p75": 0,
                "p90": 0,
                "p95": 0,
                "p99": 0
            }
        }
        
        if not self.langfuse_client.enabled:
            logger.warning("Langfuse is not enabled - returning empty stats")
            return stats
        
        try:
            # Fetch traces count
            traces_data = await self.langfuse_client.get_traces(
                limit=1, 
                from_timestamp=from_time,
                to_timestamp=now
            )
            stats["summary"]["total_traces"] = traces_data.get("meta", {}).get("totalItems", 0)
            
            # Fetch model usage (this also gives us generations)
            model_usage = await self.langfuse_client.get_model_usage(
                from_timestamp=from_time,
                to_timestamp=now
            )
            stats["by_model"] = model_usage
            
            # Aggregate totals from model usage
            for model_stats in model_usage:
                stats["summary"]["total_generations"] += model_stats.get("calls", 0)
                stats["summary"]["total_cost"] += model_stats.get("total_cost", 0)
                stats["summary"]["total_tokens"] += model_stats.get("total_tokens", 0)
                
                # Categorize by operation type based on model name
                model_name = (model_stats.get("model") or "").lower()
                if "embed" in model_name:
                    category = "embedding"
                else:
                    category = "llm"
                
                stats["by_operation"][category]["calls"] += model_stats.get("calls", 0)
                stats["by_operation"][category]["tokens"] += model_stats.get("total_tokens", 0)
                stats["by_operation"][category]["cost"] += model_stats.get("total_cost", 0)
                
                if model_stats.get("avg_latency_ms"):
                    stats["by_operation"][category]["avg_latency_ms"] = model_stats["avg_latency_ms"]
            
            # Fetch all observations for latency percentiles
            obs_data = await self.langfuse_client.get_observations(
                limit=500,
                from_timestamp=from_time
            )
            
            latencies = []
            for obs in obs_data.get("data", []):
                if obs.get("latency"):
                    latencies.append(obs["latency"])
                    
            stats["summary"]["total_observations"] = obs_data.get("meta", {}).get("totalItems", 0)
            
            # Calculate percentiles
            if latencies:
                latencies.sort()
                n = len(latencies)
                stats["latency_percentiles"] = {
                    "p50": latencies[int(n * 0.50)] if n > 0 else 0,
                    "p75": latencies[int(n * 0.75)] if n > 0 else 0,
                    "p90": latencies[int(n * 0.90)] if n > 0 else 0,
                    "p95": latencies[int(n * 0.95)] if n > 0 else 0,
                    "p99": latencies[min(int(n * 0.99), n-1)] if n > 0 else 0
                }
                
        except Exception as e:
            logger.error(f"Failed to get usage stats from Langfuse: {e}")
            
        return stats

    async def get_recent_traces(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent traces for display in UI."""
        if not self.langfuse_client.enabled:
            return []
            
        try:
            data = await self.langfuse_client.get_traces(limit=limit)
            traces = []
            for trace in data.get("data", []):
                traces.append({
                    "id": trace.get("id"),
                    "name": trace.get("name"),
                    "timestamp": trace.get("timestamp"),
                    "latency": trace.get("latency"),
                    "input_tokens": trace.get("usage", {}).get("input", 0),
                    "output_tokens": trace.get("usage", {}).get("output", 0),
                    "total_cost": trace.get("totalCost", 0),
                    "status": trace.get("status"),
                    "user_id": trace.get("userId"),
                    "session_id": trace.get("sessionId"),
                    "metadata": trace.get("metadata")
                })
            return traces
        except Exception as e:
            logger.error(f"Failed to get recent traces: {e}")
            return []

    async def get_trace_detail(self, trace_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed trace information including all spans/generations."""
        if not self.langfuse_client.enabled:
            return None
            
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.langfuse_client.host}/api/public/traces/{trace_id}",
                    auth=self.langfuse_client._get_auth()
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Failed to get trace detail: {e}")
            return None


# Singleton
_service_instance = None
def get_observability_service():
    global _service_instance
    if _service_instance is None:
        _service_instance = ObservabilityService()
    return _service_instance
