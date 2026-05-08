"""
Observability API Routes.

Provides endpoints for:
- Configuration management (log level, tracing settings)
- Usage statistics from Langfuse
- Recent traces from Langfuse
- Test log emission
"""
from typing import Optional, Any, Dict, List
from datetime import datetime, timedelta, timezone
from enum import Enum
import re

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.auth.permissions import require_admin, get_current_user
from app.modules.users.schemas import User
from app.core.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/observability", tags=["Observability"])


# ============================================
# Pydantic Models
# ============================================

class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class ObservabilityConfig(BaseModel):
    """Observability configuration settings."""
    log_level: LogLevel = LogLevel.INFO
    tracing_provider: str = "langfuse"
    trace_sample_rate: float = 1.0
    log_destinations: List[str] = ["console", "file"]
    langfuse_enabled: bool = False
    langfuse_host: Optional[str] = None


class ObservabilityConfigUpdate(BaseModel):
    """Update observability configuration."""
    log_level: Optional[LogLevel] = None
    trace_sample_rate: Optional[float] = None
    log_destinations: Optional[List[str]] = None


class UsageSummary(BaseModel):
    """Summary of usage statistics."""
    total_traces: int = 0
    total_observations: int = 0
    total_generations: int = 0
    total_cost: float = 0.0
    total_tokens: int = 0


class ModelUsage(BaseModel):
    """Usage statistics per model."""
    model: str
    type: str = "llm"
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    avg_latency_ms: float = 0.0


class OperationUsage(BaseModel):
    """Usage by operation type."""
    calls: int = 0
    tokens: int = 0
    cost: float = 0.0
    avg_latency_ms: float = 0.0


class LatencyPercentiles(BaseModel):
    """Latency percentiles."""
    p50: float = 0.0
    p75: float = 0.0
    p90: float = 0.0
    p95: float = 0.0
    p99: float = 0.0


class UsageStats(BaseModel):
    """Complete usage statistics."""
    period: str
    from_timestamp: str
    to_timestamp: str
    langfuse_enabled: bool
    langfuse_host: Optional[str]
    summary: UsageSummary
    by_model: List[ModelUsage] = []
    by_operation: Dict[str, OperationUsage] = {
        "llm": OperationUsage(),
        "embedding": OperationUsage(),
        "retrieval": OperationUsage()
    }
    latency_percentiles: LatencyPercentiles = LatencyPercentiles()


class ChildObservation(BaseModel):
    """A child observation within a trace (e.g., SQL generation, follow-up)."""
    id: str
    name: str
    type: str  # "GENERATION", "SPAN", "CHAIN", etc.
    model: str = "unknown"
    input_preview: str = ""
    output_preview: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    latency_ms: float = 0.0
    level: str = "DEFAULT"  # DEBUG, DEFAULT, WARNING, ERROR


class RecentTrace(BaseModel):
    """A recent trace from Langfuse with hierarchical children."""
    id: str
    trace_id: str
    name: str
    model: str = "unknown"
    timestamp: str
    latency: float = 0.0
    user_query: str = ""
    final_answer: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    total_cost: float = 0.0
    status: str = "unknown"
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    # Hierarchical children for detailed breakdown
    children: List[ChildObservation] = []
    # Aggregated totals
    total_input_tokens: int = 0
    total_output_tokens: int = 0


# ============================================
# Helper Functions
# ============================================

def _get_langfuse_client():
    """Get Langfuse client if available."""
    try:
        from app.modules.chat.tracing import get_langfuse_client
        return get_langfuse_client()
    except Exception as e:
        logger.debug(f"Could not get Langfuse client: {e}")
        return None


def _parse_period(period: str) -> timedelta:
    """Parse period string to timedelta."""
    if period.endswith('h'):
        return timedelta(hours=int(period[:-1]))
    elif period.endswith('d'):
        return timedelta(days=int(period[:-1]))
    elif period.endswith('w'):
        return timedelta(weeks=int(period[:-1]))
    else:
        return timedelta(hours=24)


async def _fetch_langfuse_usage(client, from_time: datetime, to_time: datetime) -> Dict[str, Any]:
    """Fetch usage data from Langfuse API."""
    try:
        summary = UsageSummary()
        by_model: Dict[str, ModelUsage] = {}
        by_operation = {
            "llm": OperationUsage(),
            "embedding": OperationUsage(),
            "retrieval": OperationUsage()
        }
        latencies = []
        
        # SDK v3: Use client.api.observations.get_many() - paginate to get all observations
        if hasattr(client, 'api') and hasattr(client.api, 'observations'):
            try:
                obs_data = []
                page = 1
                while True:
                    result = client.api.observations.get_many(
                        page=page,
                        limit=100,
                        from_start_time=from_time,
                        to_start_time=to_time
                    )
                    page_data = result.data if hasattr(result, 'data') else []
                    if not page_data:
                        break
                    obs_data.extend(page_data)
                    if len(page_data) < 100:
                        break
                    page += 1
                    if page > 10:  # Safety limit: max 1000 observations
                        break
            except Exception as e:
                logger.debug(f"get_many failed: {e}")
                obs_data = []
            
            for obs in obs_data:
                summary.total_observations += 1
                
                obs_type = getattr(obs, 'type', 'SPAN')
                if obs_type == 'GENERATION':
                    summary.total_generations += 1
                
                # Model usage
                model_name = getattr(obs, 'model', None) or 'unknown'
                if model_name not in by_model:
                    by_model[model_name] = ModelUsage(model=model_name)
                
                model_usage = by_model[model_name]
                model_usage.calls += 1
                
                usage = getattr(obs, 'usage', None)
                if usage:
                    input_t = getattr(usage, 'input', 0) or 0
                    output_t = getattr(usage, 'output', 0) or 0
                    model_usage.input_tokens += input_t
                    model_usage.output_tokens += output_t
                    model_usage.total_tokens += input_t + output_t
                    summary.total_tokens += input_t + output_t
                
                cost = getattr(obs, 'calculated_total_cost', 0) or 0
                model_usage.total_cost += cost
                summary.total_cost += cost
                
                # Latency
                latency = getattr(obs, 'latency', None)
                if latency:
                    latencies.append(latency)
                    model_usage.avg_latency_ms = (
                        (model_usage.avg_latency_ms * (model_usage.calls - 1) + latency)
                        / model_usage.calls
                    )
                
                # Operation type
                if obs_type == 'GENERATION':
                    by_operation["llm"].calls += 1
                    if usage:
                        by_operation["llm"].tokens += (getattr(usage, 'input', 0) or 0) + (getattr(usage, 'output', 0) or 0)
                    by_operation["llm"].cost += cost
                elif 'embed' in model_name.lower():
                    by_operation["embedding"].calls += 1
        
        # SDK v3: Get trace count
        if hasattr(client, 'api') and hasattr(client.api, 'trace'):
            try:
                traces = client.api.trace.list(limit=100)
                summary.total_traces = len(traces.data) if hasattr(traces, 'data') else 0
            except Exception as e:
                logger.debug(f"Failed to get trace count: {e}")
        
        # Calculate latency percentiles
        percentiles = LatencyPercentiles()
        if latencies:
            latencies.sort()
            n = len(latencies)
            percentiles.p50 = latencies[int(n * 0.50)]
            percentiles.p75 = latencies[int(n * 0.75)]
            percentiles.p90 = latencies[int(n * 0.90)]
            percentiles.p95 = latencies[int(n * 0.95)]
            percentiles.p99 = latencies[min(int(n * 0.99), n - 1)]
        
        return {
            "summary": summary,
            "by_model": list(by_model.values()),
            "by_operation": by_operation,
            "latency_percentiles": percentiles
        }
        
    except Exception as e:
        logger.warning(f"Failed to fetch Langfuse usage: {e}")
        return None


async def _fetch_langfuse_traces(client, limit: int) -> List[RecentTrace]:
    """Fetch recent traces from Langfuse with hierarchical children for cost/token breakdown."""
    try:
        traces = []
        
        # SDK v3: Use client.api.trace.list()
        if hasattr(client, 'api') and hasattr(client.api, 'trace'):
            result = client.api.trace.list(limit=limit)
            trace_data_list = result.data if hasattr(result, 'data') else []
            
            for trace in trace_data_list:
                trace_data = RecentTrace(
                    id=str(getattr(trace, 'id', '')),
                    trace_id=str(getattr(trace, 'id', '')),
                    name=getattr(trace, 'name', 'unknown'),
                    timestamp=str(getattr(trace, 'timestamp', datetime.utcnow())),
                    user_id=getattr(trace, 'user_id', None),
                    session_id=getattr(trace, 'session_id', None),
                    status="completed" if getattr(trace, 'level', None) != 'ERROR' else "error"
                )
                
                # Try to get metadata
                metadata = getattr(trace, 'metadata', {}) or {}
                if metadata.get('query_preview'):
                    trace_data.user_query = metadata['query_preview']
                if metadata.get('user_id'):
                    trace_data.user_id = metadata['user_id']
                if metadata.get('session_id'):
                    trace_data.session_id = metadata['session_id']
                
                # Try to get output - check various formats
                output = getattr(trace, 'output', None)
                if output and isinstance(output, dict):
                    # LangChain format: content field
                    content = output.get('content', '')
                    if content:
                        # Clean up if it's an LLM response with thinking tags
                        if '<query>' in content:
                            # Extract just the query part for SQL responses
                            query_match = re.search(r'<query>(.*?)</query>', content, re.DOTALL)
                            if query_match:
                                trace_data.final_answer = query_match.group(1).strip()[:200]
                            else:
                                trace_data.final_answer = content[:200]
                        else:
                            trace_data.final_answer = content[:200]
                    # Fallback to 'answer' key
                    elif output.get('answer'):
                        trace_data.final_answer = str(output.get('answer', ''))[:200]
                
                # Latency
                latency = getattr(trace, 'latency', None)
                if latency:
                    trace_data.latency = latency
                
                # Fetch observations to get hierarchical breakdown
                try:
                    observations = client.api.observations.get_many(
                        trace_id=trace.id,
                        limit=50  # Fetch more to capture all children
                    )
                    obs_list = observations.data if hasattr(observations, 'data') else []
                    
                    total_cost = 0.0
                    total_input = 0
                    total_output = 0
                    model_name = "unknown"
                    children = []
                    
                    for obs in obs_list:
                        obs_type = getattr(obs, 'type', 'SPAN')
                        obs_name = getattr(obs, 'name', 'unknown')
                        obs_model = getattr(obs, 'model', None) or 'unknown'
                        obs_level = getattr(obs, 'level', 'DEFAULT') or 'DEFAULT'
                        
                        # Get cost
                        cost = getattr(obs, 'calculated_total_cost', 0) or 0
                        total_cost += cost
                        
                        # Get tokens
                        obs_input_tokens = 0
                        obs_output_tokens = 0
                        usage = getattr(obs, 'usage', None)
                        if usage:
                            obs_input_tokens = getattr(usage, 'input', 0) or 0
                            obs_output_tokens = getattr(usage, 'output', 0) or 0
                            total_input += obs_input_tokens
                            total_output += obs_output_tokens
                        
                        # Get latency
                        obs_latency = getattr(obs, 'latency', 0) or 0
                        
                        # Extract input/output previews
                        input_preview = ""
                        output_preview = ""
                        
                        obs_input = getattr(obs, 'input', None)
                        if obs_input:
                            if isinstance(obs_input, str):
                                input_preview = obs_input[:100]
                            elif isinstance(obs_input, list) and len(obs_input) > 0:
                                # LangChain messages format - get last user message
                                last_msg = obs_input[-1] if obs_input else {}
                                if isinstance(last_msg, dict):
                                    input_preview = str(last_msg.get('content', ''))[:100]
                            elif isinstance(obs_input, dict):
                                # Dict input - try to extract question/query
                                input_preview = str(obs_input.get('question', obs_input.get('query', '')))[:100]
                        
                        obs_output = getattr(obs, 'output', None)
                        if obs_output:
                            if isinstance(obs_output, str):
                                output_preview = obs_output[:150]
                            elif isinstance(obs_output, dict):
                                content = obs_output.get('content', '')
                                if content:
                                    # Clean up SQL responses
                                    if '<query>' in content:
                                        query_match = re.search(r'<query>(.*?)</query>', content, re.DOTALL)
                                        if query_match:
                                            output_preview = query_match.group(1).strip()[:150]
                                        else:
                                            output_preview = content[:150]
                                    else:
                                        output_preview = content[:150]
                                else:
                                    output_preview = str(obs_output.get('answer', ''))[:150]
                        
                        # Set trace-level model from first GENERATION
                        if obs_type == 'GENERATION' and model_name == 'unknown' and obs_model != 'unknown':
                            model_name = obs_model
                        
                        # Get final answer from GENERATION if not set
                        if not trace_data.final_answer and obs_type == 'GENERATION' and output_preview:
                            trace_data.final_answer = output_preview[:200]
                        
                        # Get user query from input if not set
                        if not trace_data.user_query and input_preview:
                            trace_data.user_query = input_preview[:100]
                        
                        # Create child observation for the hierarchy
                        # Only include meaningful observations (with tokens, cost, or named operations)
                        if cost > 0 or obs_input_tokens > 0 or obs_type == 'GENERATION' or obs_name not in ['unknown', 'RunnableSequence']:
                            child = ChildObservation(
                                id=str(getattr(obs, 'id', '')),
                                name=_get_friendly_name(obs_name, obs_type),
                                type=obs_type,
                                model=obs_model,
                                input_preview=input_preview,
                                output_preview=output_preview,
                                input_tokens=obs_input_tokens,
                                output_tokens=obs_output_tokens,
                                cost=cost,
                                latency_ms=obs_latency,
                                level=obs_level,
                            )
                            children.append(child)
                    
                    # Sort children by type priority: GENERATION first, then CHAIN, then SPAN
                    type_order = {'GENERATION': 0, 'CHAIN': 1, 'SPAN': 2, 'TOOL': 3}
                    children.sort(key=lambda c: type_order.get(c.type, 4))
                    
                    trace_data.total_cost = total_cost
                    trace_data.input_tokens = total_input
                    trace_data.output_tokens = total_output
                    trace_data.total_input_tokens = total_input
                    trace_data.total_output_tokens = total_output
                    trace_data.model = model_name
                    trace_data.children = children
                    
                except Exception as e:
                    logger.debug(f"Failed to get observations for trace {trace.id}: {e}")
                
                traces.append(trace_data)
            
            return traces
        
        return []
        
    except Exception as e:
        logger.warning(f"Failed to fetch Langfuse traces: {e}")
        return []


def _get_friendly_name(name: str, obs_type: str) -> str:
    """Convert observation names to user-friendly labels."""
    # Common LangChain operation names
    friendly_names = {
        'ChatOpenAI': 'LLM Call',
        'ChatPromptTemplate': 'Prompt Template',
        'RunnableSequence': 'Chain',
        'StrOutputParser': 'Output Parser',
        'ChatAnthropic': 'LLM Call (Claude)',
        'sql_generation': 'SQL Generation',
        'intent_classification': 'Intent Classification',
        'query_rewrite': 'Query Rewriting',
        'followup_generation': 'Follow-up Questions',
        'embedding': 'Embedding',
        'retrieval': 'Vector Search',
    }
    
    if name in friendly_names:
        return friendly_names[name]
    
    # Format based on type
    if obs_type == 'GENERATION':
        return f"LLM: {name}"
    elif obs_type == 'CHAIN':
        return f"Chain: {name}"
    
    return name


# ============================================
# Routes
# ============================================

@router.get("/config", response_model=ObservabilityConfig)
async def get_config(
    current_user: User = Depends(get_current_user)
) -> ObservabilityConfig:
    """
    Get current observability configuration.
    
    Returns tracing provider settings, log level, and Langfuse status.
    """
    settings = get_settings()
    
    return ObservabilityConfig(
        log_level=LogLevel.INFO,
        tracing_provider="langfuse" if settings.langfuse_enabled else "none",
        trace_sample_rate=1.0,
        log_destinations=["console", "file"],
        langfuse_enabled=settings.langfuse_enabled,
        langfuse_host=settings.langfuse_base_url or settings.langfuse_host if settings.langfuse_enabled else None
    )


@router.put("/config", response_model=ObservabilityConfig)
async def update_config(
    config_update: ObservabilityConfigUpdate,
    current_user: User = Depends(require_admin)
) -> ObservabilityConfig:
    """
    Update observability configuration.
    
    Requires admin privileges.
    Note: Some settings (like Langfuse keys) require restart to take effect.
    """
    settings = get_settings()
    
    # Log level changes can be applied dynamically
    if config_update.log_level:
        logger.info(f"Log level update requested: {config_update.log_level}")
        # In a real implementation, this would update the logging configuration
    
    return ObservabilityConfig(
        log_level=config_update.log_level or LogLevel.INFO,
        tracing_provider="langfuse" if settings.langfuse_enabled else "none",
        trace_sample_rate=config_update.trace_sample_rate or 1.0,
        log_destinations=config_update.log_destinations or ["console", "file"],
        langfuse_enabled=settings.langfuse_enabled,
        langfuse_host=settings.langfuse_base_url or settings.langfuse_host if settings.langfuse_enabled else None
    )


@router.get("/usage", response_model=UsageStats)
async def get_usage(
    period: str = Query(default="24h", description="Time period (e.g., 24h, 7d, 30d)"),
    current_user: User = Depends(get_current_user)
) -> UsageStats:
    """
    Get usage statistics from Langfuse.
    
    Returns token usage, costs, and latency metrics for the specified period.
    """
    settings = get_settings()
    
    now = datetime.now(timezone.utc)
    delta = _parse_period(period)
    from_time = now - delta
    
    base_stats = UsageStats(
        period=period,
        from_timestamp=from_time.isoformat() + "Z",
        to_timestamp=now.isoformat() + "Z",
        langfuse_enabled=settings.langfuse_enabled,
        langfuse_host=settings.langfuse_base_url or settings.langfuse_host if settings.langfuse_enabled else None,
        summary=UsageSummary(),
        by_model=[],
        by_operation={
            "llm": OperationUsage(),
            "embedding": OperationUsage(),
            "retrieval": OperationUsage()
        },
        latency_percentiles=LatencyPercentiles()
    )
    
    if not settings.langfuse_enabled:
        logger.debug("Langfuse not enabled, returning empty stats")
        return base_stats
    
    client = _get_langfuse_client()
    if not client:
        logger.debug("Langfuse client not available")
        return base_stats
    
    usage_data = await _fetch_langfuse_usage(client, from_time, now)
    
    if usage_data:
        return UsageStats(
            period=period,
            from_timestamp=from_time.isoformat() + "Z",
            to_timestamp=now.isoformat() + "Z",
            langfuse_enabled=True,
            langfuse_host=settings.langfuse_base_url or settings.langfuse_host,
            summary=usage_data.get("summary", UsageSummary()),
            by_model=usage_data.get("by_model", []),
            by_operation=usage_data.get("by_operation", {
                "llm": OperationUsage(),
                "embedding": OperationUsage(),
                "retrieval": OperationUsage()
            }),
            latency_percentiles=usage_data.get("latency_percentiles", LatencyPercentiles())
        )
    
    return base_stats


@router.get("/traces", response_model=List[RecentTrace])
async def get_traces(
    limit: int = Query(default=10, ge=1, le=100, description="Number of traces to return"),
    current_user: User = Depends(get_current_user)
) -> List[RecentTrace]:
    """
    Get recent traces from Langfuse.
    
    Returns the most recent traces with basic metadata.
    """
    settings = get_settings()
    
    if not settings.langfuse_enabled:
        return []
    
    client = _get_langfuse_client()
    if not client:
        return []
    
    return await _fetch_langfuse_traces(client, limit)


@router.post("/test-log")
async def test_log_emission(
    level: str = Query(default="INFO", description="Log level (DEBUG, INFO, WARNING, ERROR)"),
    message: str = Query(default="Test log message", description="Log message"),
    current_user: User = Depends(require_admin)
) -> Dict[str, str]:
    """
    Emit a test log message.
    
    Useful for testing log pipeline and observability setup.
    Requires admin privileges.
    """
    log_message = f"[TEST] {message}"
    
    level_upper = level.upper()
    if level_upper == "DEBUG":
        logger.debug(log_message)
    elif level_upper == "WARNING":
        logger.warning(log_message)
    elif level_upper == "ERROR":
        logger.error(log_message)
    else:
        logger.info(log_message)
    
    return {
        "status": "success",
        "level": level_upper,
        "message": log_message,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }
