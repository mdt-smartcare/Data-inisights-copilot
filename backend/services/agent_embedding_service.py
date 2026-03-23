"""
Agent Embedding Service - Per-agent embedding model management.

This service handles:
- Per-agent embedding model configuration
- Collection name generation (unique per agent + model combination)
- Embedding model resolution for queries
- Model change tracking and reindex triggering
"""
import hashlib
from typing import Dict, Any, Optional, List

from backend.core.logging import get_logger
from backend.database.db import get_db_service
from backend.services.embedding_registry import get_embedding_registry

logger = get_logger(__name__)


# Default embedding configuration
DEFAULT_EMBEDDING_CONFIG = {
    "provider": "sentence-transformers",
    "model_name": "BAAI/bge-m3",
    "model_path": "./models/bge-m3",
    "dimension": 1024,
    "batch_size": 128
}


def generate_collection_name(agent_id: int, model_name: str) -> str:
    """
    Generate a unique collection name for an agent + embedding model combination.
    
    Format: agent_{agent_id}_{model_hash_short}
    This ensures each agent has its own isolated vector space.
    """
    model_hash = hashlib.md5(model_name.encode()).hexdigest()[:8]
    return f"agent_{agent_id}_{model_hash}"


class AgentEmbeddingService:
    """
    Service for managing per-agent embedding configurations.
    
    Each agent can have its own embedding model, which determines:
    - Which embedding provider to use for document indexing
    - Which vector collection to store/query embeddings
    - The vector dimension for the collection
    """
    
    def __init__(self):
        self._registry = get_embedding_registry()
    
    def get_agent_embedding_config(self, agent_id: int) -> Dict[str, Any]:
        """
        Get the embedding configuration for a specific agent.
        
        Returns the agent's configured embedding model settings,
        or defaults if not configured.
        """
        db = get_db_service()
        
        # Try to get from agent_embedding_configs table
        config = db.execute_query(
            """
            SELECT provider, model_name, model_path, dimension, batch_size, 
                   collection_name, last_embedded_at, document_count, requires_reindex
            FROM agent_embedding_configs
            WHERE agent_id = %s
            """,
            (agent_id,),
            fetch_one=True
        )
        
        if config:
            return {
                "agent_id": agent_id,
                "provider": config["provider"],
                "model_name": config["model_name"],
                "model_path": config.get("model_path"),
                "dimension": config["dimension"],
                "batch_size": config["batch_size"],
                "collection_name": config["collection_name"] or generate_collection_name(agent_id, config["model_name"]),
                "last_embedded_at": config.get("last_embedded_at"),
                "document_count": config.get("document_count", 0),
                "requires_reindex": bool(config.get("requires_reindex", 0))
            }
        
        # Fallback: check agents table for basic config
        agent = db.execute_query(
            """
            SELECT embedding_model, embedding_dimension, embedding_provider
            FROM agents WHERE id = %s
            """,
            (agent_id,),
            fetch_one=True
        )
        
        if agent and agent.get("embedding_model"):
            model_name = agent["embedding_model"]
            return {
                "agent_id": agent_id,
                "provider": agent.get("embedding_provider", DEFAULT_EMBEDDING_CONFIG["provider"]),
                "model_name": model_name,
                "model_path": DEFAULT_EMBEDDING_CONFIG["model_path"] if model_name == "bge-m3" else None,
                "dimension": agent.get("embedding_dimension", DEFAULT_EMBEDDING_CONFIG["dimension"]),
                "batch_size": DEFAULT_EMBEDDING_CONFIG["batch_size"],
                "collection_name": generate_collection_name(agent_id, model_name),
                "last_embedded_at": None,
                "document_count": 0,
                "requires_reindex": False
            }
        
        # Return defaults with agent-specific collection
        default_config = DEFAULT_EMBEDDING_CONFIG.copy()
        default_config["agent_id"] = agent_id
        default_config["collection_name"] = generate_collection_name(agent_id, default_config["model_name"])
        default_config["last_embedded_at"] = None
        default_config["document_count"] = 0
        default_config["requires_reindex"] = False
        return default_config
    
    def set_agent_embedding_config(
        self,
        agent_id: int,
        provider: str,
        model_name: str,
        dimension: int,
        model_path: Optional[str] = None,
        batch_size: int = 128,
        updated_by: str = "system"
    ) -> Dict[str, Any]:
        """
        Set or update the embedding configuration for an agent.
        
        If the model changes, marks requires_reindex=True and logs the change.
        """
        db = get_db_service()
        
        # Get current config to detect changes
        current_config = self.get_agent_embedding_config(agent_id)
        model_changed = (
            current_config.get("provider") != provider or
            current_config.get("model_name") != model_name
        )
        
        collection_name = generate_collection_name(agent_id, model_name)
        
        # Upsert the configuration
        db.execute_query(
            """
            INSERT INTO agent_embedding_configs 
                (agent_id, provider, model_name, model_path, dimension, batch_size, 
                 collection_name, requires_reindex, updated_at, updated_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, %s)
            ON CONFLICT(agent_id) DO UPDATE SET
                provider = excluded.provider,
                model_name = excluded.model_name,
                model_path = excluded.model_path,
                dimension = excluded.dimension,
                batch_size = excluded.batch_size,
                collection_name = excluded.collection_name,
                requires_reindex = excluded.requires_reindex,
                updated_at = CURRENT_TIMESTAMP,
                updated_by = excluded.updated_by
            """,
            (agent_id, provider, model_name, model_path, dimension, batch_size,
             collection_name, 1 if model_changed else 0, updated_by)
        )
        
        # Also update the agents table for quick access
        db.execute_query(
            """
            UPDATE agents 
            SET embedding_model = %s, embedding_dimension = %s, embedding_provider = %s
            WHERE id = %s
            """,
            (model_name, dimension, provider, agent_id)
        )
        
        # Log the change if model changed
        if model_changed:
            db.execute_query(
                """
                INSERT INTO agent_embedding_history
                    (agent_id, previous_provider, previous_model, previous_dimension,
                     new_provider, new_model, new_dimension, change_reason, changed_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    agent_id,
                    current_config.get("provider"),
                    current_config.get("model_name"),
                    current_config.get("dimension"),
                    provider,
                    model_name,
                    dimension,
                    "Embedding model configuration updated",
                    updated_by
                )
            )
            logger.info(
                f"Agent {agent_id} embedding model changed from "
                f"{current_config.get('model_name')} to {model_name}. Reindex required."
            )
        
        return {
            "success": True,
            "agent_id": agent_id,
            "provider": provider,
            "model_name": model_name,
            "dimension": dimension,
            "collection_name": collection_name,
            "requires_reindex": model_changed,
            "previous_model": current_config.get("model_name") if model_changed else None
        }
    
    def get_collection_name_for_agent(self, agent_id: int) -> str:
        """Get the vector collection name for a specific agent."""
        config = self.get_agent_embedding_config(agent_id)
        return config["collection_name"]
    
    def get_embedding_provider_for_agent(self, agent_id: int):
        """
        Get an embedding provider instance configured for a specific agent.
        
        This creates or retrieves a provider matching the agent's configuration.
        """
        config = self.get_agent_embedding_config(agent_id)
        
        # Check if the global registry has the same provider active
        active_type = self._registry.get_active_provider_type()
        
        if active_type == config["provider"]:
            # Can use the global provider
            return self._registry.get_active_provider()
        
        # Need to create a provider for this specific config
        from backend.services.embedding_providers import create_embedding_provider
        
        provider_config = {
            "model_name": config["model_name"],
            "batch_size": config["batch_size"]
        }
        if config.get("model_path"):
            provider_config["model_path"] = config["model_path"]
        
        return create_embedding_provider(config["provider"], provider_config)
    
    def mark_agent_indexed(
        self,
        agent_id: int,
        document_count: int,
        job_id: Optional[str] = None
    ) -> None:
        """Mark an agent as having been indexed (reindex complete)."""
        db = get_db_service()
        
        db.execute_query(
            """
            UPDATE agent_embedding_configs
            SET requires_reindex = 0,
                last_embedded_at = CURRENT_TIMESTAMP,
                document_count = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE agent_id = %s
            """,
            (document_count, agent_id)
        )
        
        # Update history if job_id provided
        if job_id:
            db.execute_query(
                """
                UPDATE agent_embedding_history
                SET reindex_triggered = 1, reindex_job_id = %s
                WHERE agent_id = %s AND reindex_job_id IS NULL
                ORDER BY changed_at DESC LIMIT 1
                """,
                (job_id, agent_id)
            )
        
        logger.info(f"Agent {agent_id} marked as indexed with {document_count} documents")
    
    def list_agents_requiring_reindex(self) -> List[Dict[str, Any]]:
        """List all agents that require reindexing due to model changes."""
        db = get_db_service()
        
        results = db.execute_query(
            """
            SELECT aec.agent_id, a.name as agent_name, aec.provider, aec.model_name,
                   aec.dimension, aec.collection_name, aec.last_embedded_at
            FROM agent_embedding_configs aec
            JOIN agents a ON a.id = aec.agent_id
            WHERE aec.requires_reindex = 1
            """,
            fetch_all=True
        )
        
        return [dict(r) for r in results] if results else []
    
    def get_embedding_history(self, agent_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Get the embedding model change history for an agent."""
        db = get_db_service()
        
        results = db.execute_query(
            """
            SELECT previous_provider, previous_model, previous_dimension,
                   new_provider, new_model, new_dimension,
                   change_reason, changed_by, changed_at,
                   reindex_triggered, reindex_job_id
            FROM agent_embedding_history
            WHERE agent_id = %s
            ORDER BY changed_at DESC
            LIMIT %s
            """,
            (agent_id, limit),
            fetch_all=True
        )
        
        return [dict(r) for r in results] if results else []


# Singleton instance
_agent_embedding_service: Optional[AgentEmbeddingService] = None


def get_agent_embedding_service() -> AgentEmbeddingService:
    """Get the singleton AgentEmbeddingService instance."""
    global _agent_embedding_service
    if _agent_embedding_service is None:
        _agent_embedding_service = AgentEmbeddingService()
    return _agent_embedding_service
