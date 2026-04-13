"""
SQL Examples Vector Store for Few-Shot Learning.

Stores curated question-SQL pairs and retrieves similar examples
using vector similarity search to improve NL2SQL accuracy.

Supports both Qdrant (preferred) and ChromaDB backends with automatic fallback.

IMPORTANT: This store should NOT contain any actual patient data, names,
or identifiable information. Only store generic question patterns and SQL templates.

PER-AGENT SUPPORT:
- Each agent can have its own SQL examples scoped by agent_id
- Global examples (agent_id=None) serve as fallback for all agents
- Agent-specific examples are prioritized over global ones in retrieval
"""
import hashlib
import threading
from typing import List, Dict, Any, Optional

from app.core.utils.logging import get_logger
from app.core.settings import get_settings
from app.modules.embeddings.vector_stores.base import BaseVectorStore
from app.modules.embeddings.vector_stores.factory import (
    get_vector_store,
    get_vector_store_type,
    VectorStoreFactory
)

logger = get_logger(__name__)

# Collection name for SQL examples
SQL_EXAMPLES_COLLECTION = "sql_examples"

# Singleton instances per agent (None = global)
_sql_examples_store_instances: Dict[Optional[str], "SQLExamplesStore"] = {}
_sql_examples_store_lock = threading.Lock()


class SQLExamplesStore:
    """
    Vector store for curated SQL Q&A pairs used in few-shot prompting.
    
    This service stores question-SQL pairs with embeddings for similarity search.
    When a new user question comes in, similar examples are retrieved and
    injected into the LLM prompt as few-shot examples to improve SQL generation.
    
    Features:
        - Supports both Qdrant (production) and ChromaDB (development) backends
        - Automatic fallback if primary backend unavailable
        - Deterministic IDs using SHA256 hash for deduplication
        - Category and tag-based filtering
        - Configurable similarity threshold
        - Per-agent example scoping with global fallback
    
    Example usage:
        # Get store for a specific agent
        store = get_sql_examples_store(agent_id="uuid-here")
        
        # Add a curated example for this agent
        await store.add_example(
            question="Show patient's initial and latest systolic pressure",
            sql="WITH PatientReadings AS (...) SELECT ...",
            category="blood_pressure",
            tags=["comparison", "temporal"],
            description="Compare first and last BP readings"
        )
        
        # Retrieve similar examples (includes agent-specific + global)
        examples = await store.get_similar_examples(
            question="Compare first and last BP readings",
            top_k=3,
            min_score=0.7
        )
    """
    
    def __init__(
        self,
        collection_name: str = SQL_EXAMPLES_COLLECTION,
        embedding_model: str = "text-embedding-ada-002",
        preferred_backend: Optional[str] = None,
        agent_id: Optional[str] = None
    ):
        """
        Initialize the SQL Examples Store.
        
        Args:
            collection_name: Name of the vector collection (default: "sql_examples")
            embedding_model: OpenAI embedding model to use (default: "text-embedding-ada-002")
            preferred_backend: Preferred vector store backend ("qdrant" or "chroma").
                             If None, uses VECTOR_STORE_TYPE env var.
            agent_id: Agent ID for scoping examples. None = global store.
        """
        self.agent_id = agent_id
        self.collection_name = collection_name
        self.embedding_model = embedding_model
        self.settings = get_settings()
        
        # Determine backend
        self.backend_type = preferred_backend or get_vector_store_type()
        
        # Initialize vector store with fallback
        self._vector_store: Optional[BaseVectorStore] = None
        self._init_vector_store()
        
        # OpenAI client for embeddings (lazy loaded)
        self._openai_client = None
        
        logger.info(
            "SQLExamplesStore initialized",
            collection=self.collection_name,
            backend=self.backend_type,
            embedding_model=self.embedding_model,
            agent_id=self.agent_id
        )
    
    def _init_vector_store(self) -> None:
        """Initialize the vector store with automatic fallback."""
        try:
            self._vector_store = get_vector_store(
                collection_name=self.collection_name,
                provider_type=self.backend_type
            )
            logger.info(f"Vector store initialized: {self.backend_type}")
        except Exception as e:
            logger.warning(
                f"Failed to initialize {self.backend_type} vector store: {e}. "
                f"Attempting fallback..."
            )
            # Try fallback
            fallback_type = "chroma" if self.backend_type == "qdrant" else "qdrant"
            try:
                self._vector_store = VectorStoreFactory.get_provider(
                    provider_type=fallback_type,
                    collection_name=self.collection_name
                )
                self.backend_type = fallback_type
                logger.info(f"Fallback to {fallback_type} vector store successful")
            except Exception as fallback_error:
                logger.error(
                    f"Both vector store backends failed. "
                    f"Primary ({self.backend_type}): {e}. "
                    f"Fallback ({fallback_type}): {fallback_error}"
                )
                raise RuntimeError(
                    f"Could not initialize any vector store backend: {e}"
                ) from e
    
    def _get_openai_client(self):
        """Get or create OpenAI client for embeddings."""
        if self._openai_client is None:
            try:
                from openai import OpenAI
                self._openai_client = OpenAI(api_key=self.settings.openai_api_key)
                logger.debug("OpenAI client initialized for embeddings")
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI client: {e}")
                raise
        return self._openai_client
    
    def _generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for a text string using OpenAI."""
        client = self._get_openai_client()
        response = client.embeddings.create(
            model=self.embedding_model,
            input=text
        )
        return response.data[0].embedding
    
    def _generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts in a single API call."""
        if not texts:
            return []
        
        client = self._get_openai_client()
        response = client.embeddings.create(
            model=self.embedding_model,
            input=texts
        )
        sorted_data = sorted(response.data, key=lambda x: x.index)
        return [item.embedding for item in sorted_data]
    
    @staticmethod
    def _generate_id(question: str, sql: str, agent_id: Optional[str] = None) -> str:
        """
        Generate a deterministic ID using SHA256 hash.
        
        Includes agent_id in hash to allow same Q&A for different agents.
        """
        agent_prefix = f"{agent_id}|" if agent_id else "global|"
        content = f"{agent_prefix}{question.strip().lower()}|{sql.strip()}"
        return hashlib.sha256(content.encode()).hexdigest()
    
    async def add_example(
        self,
        question: str,
        sql: str,
        category: str = "general",
        tags: Optional[List[str]] = None,
        description: str = "",
        agent_id: Optional[str] = None
    ) -> bool:
        """
        Add a single Q&A example to the store.
        
        Args:
            question: Natural language question
            sql: Corresponding SQL query
            category: Category for filtering
            tags: List of tags for additional filtering
            description: Optional description
            agent_id: Agent ID to scope this example. Uses store's agent_id if not provided.
            
        Returns:
            True if successful, False otherwise
        """
        try:
            effective_agent_id = agent_id if agent_id is not None else self.agent_id
            example_id = self._generate_id(question, sql, effective_agent_id)
            embedding = self._generate_embedding(question)
            
            metadata = {
                "question": question,
                "sql": sql,
                "category": category,
                "tags": ",".join(tags) if tags else "",
                "description": description,
                "agent_id": effective_agent_id or ""
            }
            
            await self._vector_store.upsert_batch(
                ids=[example_id],
                documents=[question],
                embeddings=[embedding],
                metadatas=[metadata]
            )
            
            logger.info(
                "Added SQL example",
                example_id=example_id[:12],
                category=category,
                question_preview=question[:50],
                agent_id=effective_agent_id
            )
            return True
            
        except Exception as e:
            logger.error(f"Failed to add SQL example: {e}", exc_info=True)
            return False
    
    async def add_examples_batch(
        self, 
        examples: List[Dict[str, Any]],
        agent_id: Optional[str] = None
    ) -> int:
        """Add multiple Q&A examples in batch."""
        if not examples:
            return 0
        
        try:
            default_agent_id = agent_id if agent_id is not None else self.agent_id
            
            valid_examples = []
            for ex in examples:
                if "question" not in ex or "sql" not in ex:
                    logger.warning(f"Skipping invalid example: {ex}")
                    continue
                valid_examples.append(ex)
            
            if not valid_examples:
                return 0
            
            questions = [ex["question"] for ex in valid_examples]
            embeddings = self._generate_embeddings_batch(questions)
            
            ids = []
            documents = []
            metadatas = []
            
            for ex, embedding in zip(valid_examples, embeddings):
                ex_agent_id = ex.get("agent_id", default_agent_id)
                example_id = self._generate_id(ex["question"], ex["sql"], ex_agent_id)
                ids.append(example_id)
                documents.append(ex["question"])
                
                tags = ex.get("tags", [])
                metadata = {
                    "question": ex["question"],
                    "sql": ex["sql"],
                    "category": ex.get("category", "general"),
                    "tags": ",".join(tags) if isinstance(tags, list) else str(tags),
                    "description": ex.get("description", ""),
                    "agent_id": ex_agent_id or ""
                }
                metadatas.append(metadata)
            
            await self._vector_store.upsert_batch(
                ids=ids,
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas
            )
            
            logger.info(f"Added {len(ids)} SQL examples in batch", agent_id=default_agent_id)
            return len(ids)
            
        except Exception as e:
            logger.error(f"Failed to add SQL examples batch: {e}", exc_info=True)
            return 0
    
    async def get_similar_examples(
        self,
        question: str,
        top_k: int = 3,
        category_filter: Optional[str] = None,
        min_score: float = 0.0,
        include_global: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Retrieve similar Q&A examples for few-shot prompting.
        
        Args:
            question: The user's natural language question
            top_k: Maximum number of examples to return
            category_filter: Optional category to filter by
            min_score: Minimum similarity score (0.0 to 1.0)
            include_global: Include global examples in addition to agent-specific ones
            
        Returns:
            List of example dicts with question, sql, category, tags, description, score, agent_id
        """
        try:
            query_embedding = self._generate_embedding(question)
            
            filter_dict = {}
            if category_filter:
                filter_dict["category"] = category_filter
            
            # Search vector store
            results = await self._vector_store.search(
                query_embedding=query_embedding,
                top_k=top_k * 2 if self.agent_id and include_global else top_k,
                filter_dict=filter_dict if filter_dict else None
            )
            
            examples = []
            for result in results:
                score = result.get("score", 0.0)
                if score < min_score:
                    continue
                
                metadata = result.get("metadata", {})
                result_agent_id = metadata.get("agent_id", "")
                
                # Filter by agent: include if matches agent_id or is global (when include_global)
                if self.agent_id:
                    if result_agent_id != self.agent_id and result_agent_id != "":
                        if not include_global:
                            continue
                        # Skip non-matching, non-global examples
                        if result_agent_id and result_agent_id != self.agent_id:
                            continue
                
                tags_str = metadata.get("tags", "")
                tags = [t.strip() for t in tags_str.split(",") if t.strip()]
                
                examples.append({
                    "question": metadata.get("question", ""),
                    "sql": metadata.get("sql", ""),
                    "category": metadata.get("category", "general"),
                    "tags": tags,
                    "description": metadata.get("description", ""),
                    "score": score,
                    "agent_id": result_agent_id
                })
            
            # Sort: agent-specific first, then by score
            if self.agent_id and include_global:
                examples.sort(key=lambda x: (
                    0 if x["agent_id"] == self.agent_id else 1,
                    -x["score"]
                ))
            
            examples = examples[:top_k]
            
            logger.debug(
                f"Retrieved {len(examples)} similar SQL examples",
                query_preview=question[:50],
                top_score=examples[0]["score"] if examples else 0,
                agent_id=self.agent_id
            )
            
            return examples
            
        except Exception as e:
            logger.error(f"Failed to retrieve similar SQL examples: {e}", exc_info=True)
            return []
    
    async def get_example_count(self) -> int:
        """Get the total number of examples in the store."""
        try:
            count = await self._vector_store.get_collection_count()
            return count
        except Exception as e:
            logger.error(f"Failed to get example count: {e}", exc_info=True)
            return 0
    
    async def clear(self, agent_only: bool = False) -> None:
        """
        Clear examples from the store.
        
        Args:
            agent_only: If True and agent_id is set, only clear agent-specific examples.
        """
        try:
            if agent_only and self.agent_id:
                logger.warning(f"Clearing examples for agent {self.agent_id}")
                # Note: Requires vector store to support delete_by_metadata
                if hasattr(self._vector_store, 'delete_by_metadata'):
                    await self._vector_store.delete_by_metadata({"agent_id": self.agent_id})
                else:
                    logger.warning("Vector store doesn't support filtered delete")
            else:
                await self._vector_store.delete_collection()
                self._init_vector_store()
            logger.info("Cleared SQL examples", agent_id=self.agent_id if agent_only else "ALL")
        except Exception as e:
            logger.error(f"Failed to clear SQL examples: {e}", exc_info=True)
            raise
    
    async def delete_example(self, question: str, sql: str, agent_id: Optional[str] = None) -> bool:
        """Delete a specific example by question and SQL."""
        try:
            effective_agent_id = agent_id if agent_id is not None else self.agent_id
            example_id = self._generate_id(question, sql, effective_agent_id)
            await self._vector_store.delete_by_source_ids([example_id])
            logger.info(f"Deleted SQL example: {example_id[:12]}", agent_id=effective_agent_id)
            return True
        except Exception as e:
            logger.error(f"Failed to delete SQL example: {e}", exc_info=True)
            return False
    
    async def health_check(self) -> Dict[str, Any]:
        """Check the health of the SQL examples store."""
        try:
            exists = await self._vector_store.collection_exists()
            count = await self._vector_store.get_collection_count() if exists else 0
            
            return {
                "healthy": True,
                "backend": self.backend_type,
                "collection": self.collection_name,
                "collection_exists": exists,
                "example_count": count,
                "embedding_model": self.embedding_model,
                "agent_id": self.agent_id
            }
        except Exception as e:
            return {
                "healthy": False,
                "backend": self.backend_type,
                "collection": self.collection_name,
                "agent_id": self.agent_id,
                "error": str(e)
            }


def get_sql_examples_store(
    agent_id: Optional[str] = None,
    collection_name: str = SQL_EXAMPLES_COLLECTION,
    embedding_model: str = "text-embedding-ada-002"
) -> SQLExamplesStore:
    """
    Get a SQLExamplesStore instance for the specified agent.
    
    Thread-safe singleton pattern ensures only one instance per agent_id.
    
    Args:
        agent_id: Agent ID for scoping examples. None = global store.
        collection_name: Name of the vector collection
        embedding_model: OpenAI embedding model to use
        
    Returns:
        SQLExamplesStore instance for the specified agent
    """
    global _sql_examples_store_instances
    
    with _sql_examples_store_lock:
        if agent_id not in _sql_examples_store_instances:
            _sql_examples_store_instances[agent_id] = SQLExamplesStore(
                collection_name=collection_name,
                embedding_model=embedding_model,
                agent_id=agent_id
            )
        return _sql_examples_store_instances[agent_id]


def reset_sql_examples_store(agent_id: Optional[str] = None) -> None:
    """
    Reset the store instance for a specific agent or all stores.
    
    Args:
        agent_id: Agent ID to reset. If None, resets ALL stores.
    """
    global _sql_examples_store_instances
    
    with _sql_examples_store_lock:
        if agent_id is None:
            _sql_examples_store_instances.clear()
            logger.info("All SQLExamplesStore instances reset")
        elif agent_id in _sql_examples_store_instances:
            del _sql_examples_store_instances[agent_id]
            logger.info(f"SQLExamplesStore reset for agent: {agent_id}")
