"""
Observability Service for Data Insights Copilot.

Manages:
- Runtime log level configuration
- Tracing provider toggling (Langfuse/OTEL)
- Usage metrics aggregation and cost tracking
"""
import logging
import json
import os
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import sqlite3
from pathlib import Path

from backend.config import get_settings
from backend.core.logging import get_logger, setup_logging
from backend.sqliteDb.db import get_db_service
from backend.services.settings_service import get_settings_service

settings = get_settings()
logger = get_logger(__name__)

# Get the SQLite database path (app.db in sqliteDb folder)
SQLITE_DB_PATH = Path(__file__).parent.parent / "sqliteDb" / "app.db"


class ObservabilityService:
    """Service for managing observability configuration and usage tracking."""
    
    def __init__(self):
        self.db_service = get_db_service()
        self.settings_service = get_settings_service()
        self.sqlite_db_path = str(SQLITE_DB_PATH)
        
    async def get_config(self) -> Dict[str, Any]:
        """Get current observability configuration."""
        try:
            obs_settings = self.settings_service.get_category_settings("observability")
            return obs_settings
        except Exception as e:
            logger.warning(f"Could not load observability settings: {e}")
            # Return defaults
            return {
                "log_level": settings.log_level,
                "langfuse_enabled": settings.enable_langfuse,
                "tracing_provider": "langfuse" if settings.enable_langfuse else "none",
                "log_destinations": ["console"]
            }
        
    async def update_config(self, updates: Dict[str, Any], updated_by: str = "system") -> Dict[str, Any]:
        """
        Update observability configuration and apply changes immediately.
        
        Args:
            updates: Dictionary of settings to update
            updated_by: Username making the update
            
        Returns:
            Updated configuration
        """
        try:
            current = await self.get_config()
            merged = {**current, **updates}
            
            # Update each setting individually
            for key, value in updates.items():
                self.settings_service.update_setting("observability", key, value, updated_by)
            
            # Apply changes to runtime
            self._apply_runtime_changes(updates)
            
            return merged
        except Exception as e:
            logger.error(f"Failed to update observability config: {e}")
            raise

    def _apply_runtime_changes(self, changes: Dict[str, Any]):
        """Apply configuration changes to running application."""
        
        # 1. Log Level
        if 'log_level' in changes:
            new_level = changes['log_level']
            logging.getLogger().setLevel(new_level)
            logger.info(f"Log level changed to {new_level}")
            
        # 2. Tracing Provider
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
                    
                logger.info(f"Tracing configuration updated: Langfuse={tm.langfuse_enabled}, OTEL={tm.otel_enabled}")
            except Exception as e:
                logger.warning(f"Could not update tracing config: {e}")

    async def track_usage(self, 
                          trace_id: str, 
                          operation_type: str, 
                          model_name: str, 
                          input_tokens: int, 
                          output_tokens: int,
                          duration_ms: int,
                          metadata: Dict[str, Any] = None,
                          user_id: Optional[str] = None):
        """
        Record usage metrics for an operation.
        """
        try:
            # Simple cost estimation
            cost = 0.0
            if "gpt-4" in model_name:
                cost = (input_tokens * 0.00003) + (output_tokens * 0.00006)
            elif "gpt-3.5" in model_name:
                cost = (input_tokens * 0.0000005) + (output_tokens * 0.0000015)
            elif "embedding" in operation_type:
                cost = (input_tokens * 0.0000001)
            
            query = """
                INSERT INTO usage_metrics 
                (trace_id, operation_type, model_name, input_tokens, output_tokens, total_tokens, 
                 estimated_cost_usd, duration_ms, metadata, user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            
            total_tokens = input_tokens + output_tokens
            params = (
                trace_id, operation_type, model_name, input_tokens, output_tokens, total_tokens,
                cost, duration_ms, json.dumps(metadata or {}), user_id
            )
            
            with sqlite3.connect(self.sqlite_db_path) as conn:
                conn.execute(query, params)
                conn.commit()
                
        except Exception as e:
            logger.error(f"Failed to track usage metrics: {e}")

    async def get_usage_stats(self, period: str = "24h") -> Dict[str, Any]:
        """
        Get aggregated usage statistics.
        
        Args:
            period: Time period ('1h', '24h', '7d', '30d')
            
        Returns:
            Aggregated stats dictionary
        """
        time_filter = "'-24 hours'"
        if period == "1h":
            time_filter = "'-1 hour'"
        elif period == "7d":
            time_filter = "'-7 days'"
        elif period == "30d":
            time_filter = "'-30 days'"
        
        stats = {
            "period": period,
            "llm": {"calls": 0, "tokens": 0, "cost": 0.0, "latency": 0},
            "embedding": {"calls": 0, "tokens": 0, "cost": 0.0, "latency": 0},
            "vector_search": {"calls": 0, "tokens": 0, "cost": 0.0, "latency": 0},
            "total_cost": 0.0
        }
        
        try:
            # Check if usage_metrics table exists
            with sqlite3.connect(self.sqlite_db_path) as conn:
                cursor = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='usage_metrics'"
                )
                if not cursor.fetchone():
                    logger.debug("usage_metrics table does not exist yet")
                    return stats
                
                query = f"""
                    SELECT 
                        operation_type,
                        COUNT(*) as call_count,
                        SUM(total_tokens) as total_tokens,
                        SUM(estimated_cost_usd) as total_cost,
                        AVG(duration_ms) as avg_duration
                    FROM usage_metrics
                    WHERE created_at >= datetime('now', {time_filter})
                    GROUP BY operation_type
                """
                
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(query)
                rows = cursor.fetchall()
                
                for row in rows:
                    op_type = (row["operation_type"] or "").lower()
                    
                    # Map operation types to UI categories
                    if "rag" in op_type or "pipeline" in op_type or "llm" in op_type or "chat" in op_type:
                        category = "llm"
                    elif "embed" in op_type:
                        category = "embedding"
                    elif "vector" in op_type or "search" in op_type:
                        category = "vector_search"
                    else:
                        # Default: count as LLM if it has tokens
                        category = "llm"
                    
                    # Accumulate stats (in case multiple operation types map to same category)
                    stats[category]["calls"] += row["call_count"] or 0
                    stats[category]["tokens"] += row["total_tokens"] or 0
                    stats[category]["cost"] += row["total_cost"] or 0.0
                    # For latency, we take the latest value (or could average)
                    if row["avg_duration"]:
                        stats[category]["latency"] = round(row["avg_duration"], 2)
                    stats["total_cost"] += row["total_cost"] or 0.0
                        
        except Exception as e:
            logger.error(f"Failed to get usage stats: {e}")
            
        return stats


# Singleton
_service_instance = None
def get_observability_service():
    global _service_instance
    if _service_instance is None:
        _service_instance = ObservabilityService()
    return _service_instance
