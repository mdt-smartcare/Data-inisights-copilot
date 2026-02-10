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

from backend.config import get_settings
from backend.core.logging import get_logger, setup_logging
from backend.sqliteDb.db import get_db_service
from backend.services.settings_service import get_settings_service

settings = get_settings()
logger = get_logger(__name__)

class ObservabilityService:
    """Service for managing observability configuration and usage tracking."""
    
    def __init__(self):
        self.db_service = get_db_service()
        self.settings_service = get_settings_service()
        
    async def get_config(self) -> Dict[str, Any]:
        """Get current observability configuration."""
        obs_settings = self.settings_service.get_settings_by_category("observability")
        return obs_settings
        
    async def update_config(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update observability configuration and apply changes immediately.
        
        Args:
            updates: Dictionary of settings to update
            
        Returns:
            Updated configuration
        """
        # Update settings in DB
        # We need to map the flat updates to the category structure expected by settings service
        # But settings service update takes a full object usually. 
        # Here we'll use the update_category_settings method if exposed or update individual keys.
        # Ideally, we should use settings_service.update_settings("observability", updates)
        
        # For now, let's assume we can update via settings service
        # Since settings_service.update_category_settings expects the Pydantic model
        # We fetch current, patch it, and save back.
        
        current = self.settings_service.get_settings_by_category("observability")
        merged = {**current, **updates}
        
        updated = self.settings_service.update_category_settings("observability", merged)
        
        # Apply changes to runtime
        self._apply_runtime_changes(updates)
        
        return updated

    def _apply_runtime_changes(self, changes: Dict[str, Any]):
        """Apply configuration changes to running application."""
        
        # 1. Log Level
        if 'log_level' in changes:
            new_level = changes['log_level']
            logging.getLogger().setLevel(new_level)
            logger.info(f"Log level changed to {new_level}")
            
        # 2. Tracing Provider
        if 'tracing_provider' in changes or 'langfuse_enabled' in changes:
            # We can't easily unload libraries, but we can set flags in TracingManager
            from backend.core.tracing import get_tracing_manager
            tm = get_tracing_manager()
            
            if 'langfuse_enabled' in changes:
                tm.langfuse_enabled = changes['langfuse_enabled']
                
            if 'tracing_provider' in changes:
                provider = changes['tracing_provider']
                tm.langfuse_enabled = provider in ['langfuse', 'both']
                tm.otel_enabled = provider in ['opentelemetry', 'both']
                
            logger.info(f"Tracing configuration updated: Langfuse={tm.langfuse_enabled}, OTEL={tm.otel_enabled}")

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
        
        Args:
            trace_id: Unique trace identifier
            operation_type: 'llm', 'embedding', 'vector_search'
            model_name: Name of the model used
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            duration_ms: Duration in milliseconds
            metadata: Additional metadata
            user_id: User who triggered the operation
        """
        try:
            # simple cost estimation (placeholders)
            # In a real app, this would use a pricing catalog
            cost = 0.0
            if "gpt-4" in model_name:
                cost = (input_tokens * 0.00003) + (output_tokens * 0.00006)
            elif "gpt-3.5" in model_name:
                cost = (input_tokens * 0.0000005) + (output_tokens * 0.0000015)
            elif "embedding" in operation_type:
                 cost = (input_tokens * 0.0000001) # Very cheap
            
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
            
            # Using direct SQLite connection for speed/simplicity independent of main DB session
            # Or use the db_service if it supports raw queries well
            # For logging/metrics, fire-and-forget is often best, but here we'll await
            
            with sqlite3.connect(settings.sqlite_db_path) as conn:
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
        if period == "1h": time_filter = "'-1 hour'"
        elif period == "7d": time_filter = "'-7 days'"
        elif period == "30d": time_filter = "'-30 days'"
        
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
        
        stats = {
            "period": period,
            "llm": {"calls": 0, "tokens": 0, "cost": 0.0, "latency": 0},
            "embedding": {"calls": 0, "tokens": 0, "cost": 0.0, "latency": 0},
            "vector_search": {"calls": 0, "tokens": 0, "cost": 0.0, "latency": 0},
            "total_cost": 0.0
        }
        
        try:
            with sqlite3.connect(settings.sqlite_db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(query)
                rows = cursor.fetchall()
                
                for row in rows:
                    op_type = row["operation_type"]
                    # Map rag_pipeline to a category or ignore
                    category = "llm" if "llm" in op_type else op_type
                    if "vector" in op_type: category = "vector_search"
                    
                    if category in stats:
                        stats[category]["calls"] = row["call_count"]
                        stats[category]["tokens"] = row["total_tokens"] or 0
                        stats[category]["cost"] = row["total_cost"] or 0.0
                        stats[category]["latency"] = round(row["avg_duration"] or 0, 2)
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
