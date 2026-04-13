"""
SQL Examples Vector Store for Few-Shot Learning.

Stores curated question-SQL pairs and retrieves similar examples
using vector similarity search to improve NL2SQL accuracy.

Supports both Qdrant (preferred) and ChromaDB backends with automatic fallback.

IMPORTANT: This store should NOT contain any actual patient data, names,
or identifiable information. Only store generic question patterns and SQL templates.
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

# Singleton instance
_sql_examples_store_instance: Optional["SQLExamplesStore"] = None
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
    
    Example usage:
        store = get_sql_examples_store()
        
        # Add a curated example
        store.add_example(
            question="Show patient's initial and latest systolic pressure",
            sql="WITH PatientReadings AS (...) SELECT ...",
            category="blood_pressure",
            tags=["comparison", "temporal"],
            description="Compare first and last BP readings"
        )
        
        # Retrieve similar examples for few-shot prompting
        examples = store.get_similar_examples(
            question="Compare first and last BP readings",
            top_k=3,
            min_score=0.7
        )
    """
    
    def __init__(
        self,
        collection_name: str = SQL_EXAMPLES_COLLECTION,
        embedding_model: str = "text-embedding-ada-002",
        preferred_backend: Optional[str] = None
    ):
        """
        Initialize the SQL Examples Store.
        
        Args:
            collection_name: Name of the vector collection (default: "sql_examples")
            embedding_model: OpenAI embedding model to use (default: "text-embedding-ada-002")
            preferred_backend: Preferred vector store backend ("qdrant" or "chroma").
                             If None, uses VECTOR_STORE_TYPE env var.
        """
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
            f"SQLExamplesStore initialized",
            collection=self.collection_name,
            backend=self.backend_type,
            embedding_model=self.embedding_model
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
        """
        Generate embedding for a text string using OpenAI.
        
        Args:
            text: Text to embed
            
        Returns:
            List of floats representing the embedding vector
        """
        client = self._get_openai_client()
        response = client.embeddings.create(
            model=self.embedding_model,
            input=text
        )
        return response.data[0].embedding
    
    def _generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in a single API call.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors
        """
        if not texts:
            return []
        
        client = self._get_openai_client()
        response = client.embeddings.create(
            model=self.embedding_model,
            input=texts
        )
        # Sort by index to maintain order
        sorted_data = sorted(response.data, key=lambda x: x.index)
        return [item.embedding for item in sorted_data]
    
    @staticmethod
    def _generate_id(question: str, sql: str) -> str:
        """
        Generate a deterministic ID using SHA256 hash.
        
        This ensures deduplication - adding the same question+sql pair
        twice will overwrite rather than create duplicates.
        
        Args:
            question: The natural language question
            sql: The SQL query
            
        Returns:
            SHA256 hash string
        """
        content = f"{question.strip().lower()}|{sql.strip()}"
        return hashlib.sha256(content.encode()).hexdigest()
    
    async def add_example(
        self,
        question: str,
        sql: str,
        category: str = "general",
        tags: Optional[List[str]] = None,
        description: str = ""
    ) -> bool:
        """
        Add a single Q&A example to the store.
        
        Args:
            question: Natural language question (e.g., "Show patient's BP readings")
            sql: Corresponding SQL query
            category: Category for filtering (e.g., "blood_pressure", "medications")
            tags: List of tags for additional filtering
            description: Optional description of what this example demonstrates
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Generate deterministic ID
            example_id = self._generate_id(question, sql)
            
            # Generate embedding for the question
            embedding = self._generate_embedding(question)
            
            # Build metadata
            metadata = {
                "question": question,
                "sql": sql,
                "category": category,
                "tags": ",".join(tags) if tags else "",
                "description": description
            }
            
            # Store in vector DB
            await self._vector_store.upsert_batch(
                ids=[example_id],
                documents=[question],
                embeddings=[embedding],
                metadatas=[metadata]
            )
            
            logger.info(
                f"Added SQL example",
                example_id=example_id[:12],
                category=category,
                question_preview=question[:50]
            )
            return True
            
        except Exception as e:
            logger.error(f"Failed to add SQL example: {e}", exc_info=True)
            return False
    
    async def add_examples_batch(self, examples: List[Dict[str, Any]]) -> int:
        """
        Add multiple Q&A examples in batch.
        
        More efficient than calling add_example repeatedly as it batches
        the embedding API calls.
        
        Args:
            examples: List of dicts with keys:
                - question (required): Natural language question
                - sql (required): SQL query
                - category (optional): Category string
                - tags (optional): List of tag strings
                - description (optional): Description string
                
        Returns:
            Number of examples successfully added
        """
        if not examples:
            return 0
        
        try:
            # Validate and prepare examples
            valid_examples = []
            for ex in examples:
                if "question" not in ex or "sql" not in ex:
                    logger.warning(f"Skipping invalid example (missing question or sql): {ex}")
                    continue
                valid_examples.append(ex)
            
            if not valid_examples:
                return 0
            
            # Extract questions for batch embedding
            questions = [ex["question"] for ex in valid_examples]
            
            # Generate embeddings in batch
            embeddings = self._generate_embeddings_batch(questions)
            
            # Prepare data for vector store
            ids = []
            documents = []
            metadatas = []
            
            for ex, embedding in zip(valid_examples, embeddings):
                example_id = self._generate_id(ex["question"], ex["sql"])
                ids.append(example_id)
                documents.append(ex["question"])
                
                tags = ex.get("tags", [])
                metadata = {
                    "question": ex["question"],
                    "sql": ex["sql"],
                    "category": ex.get("category", "general"),
                    "tags": ",".join(tags) if isinstance(tags, list) else str(tags),
                    "description": ex.get("description", "")
                }
                metadatas.append(metadata)
            
            # Upsert to vector store
            await self._vector_store.upsert_batch(
                ids=ids,
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas
            )
            
            logger.info(f"Added {len(ids)} SQL examples in batch")
            return len(ids)
            
        except Exception as e:
            logger.error(f"Failed to add SQL examples batch: {e}", exc_info=True)
            return 0
    
    async def get_similar_examples(
        self,
        question: str,
        top_k: int = 3,
        category_filter: Optional[str] = None,
        min_score: float = 0.0
    ) -> List[Dict[str, Any]]:
        """
        Retrieve similar Q&A examples for few-shot prompting.
        
        Args:
            question: The user's natural language question
            top_k: Maximum number of examples to return
            category_filter: Optional category to filter by
            min_score: Minimum similarity score (0.0 to 1.0)
            
        Returns:
            List of dicts containing:
                - question: The example question
                - sql: The example SQL
                - category: The category
                - tags: List of tags
                - description: Description
                - score: Similarity score (0.0 to 1.0)
        """
        try:
            # Generate embedding for the query
            query_embedding = self._generate_embedding(question)
            
            # Build filter if category specified
            filter_dict = None
            if category_filter:
                filter_dict = {"category": category_filter}
            
            # Search vector store
            results = await self._vector_store.search(
                query_embedding=query_embedding,
                top_k=top_k,
                filter_dict=filter_dict
            )
            
            # Process and filter results
            examples = []
            for result in results:
                score = result.get("score", 0.0)
                
                # Skip if below minimum score
                if score < min_score:
                    continue
                
                metadata = result.get("metadata", {})
                
                # Parse tags back to list
                tags_str = metadata.get("tags", "")
                tags = [t.strip() for t in tags_str.split(",") if t.strip()]
                
                examples.append({
                    "question": metadata.get("question", ""),
                    "sql": metadata.get("sql", ""),
                    "category": metadata.get("category", "general"),
                    "tags": tags,
                    "description": metadata.get("description", ""),
                    "score": score
                })
            
            logger.debug(
                f"Retrieved {len(examples)} similar SQL examples",
                query_preview=question[:50],
                top_score=examples[0]["score"] if examples else 0
            )
            
            return examples
            
        except Exception as e:
            logger.error(f"Failed to retrieve similar SQL examples: {e}", exc_info=True)
            return []
    
    async def get_example_count(self) -> int:
        """
        Get the total number of examples in the store.
        
        Returns:
            Number of stored examples
        """
        try:
            count = await self._vector_store.get_collection_count()
            return count
        except Exception as e:
            logger.error(f"Failed to get example count: {e}", exc_info=True)
            return 0
    
    async def clear(self) -> None:
        """
        Clear all examples from the store.
        
        WARNING: This deletes all stored Q&A pairs. Use with caution.
        """
        try:
            await self._vector_store.delete_collection()
            # Reinitialize the vector store
            self._init_vector_store()
            logger.info(f"Cleared all SQL examples from collection: {self.collection_name}")
        except Exception as e:
            logger.error(f"Failed to clear SQL examples: {e}", exc_info=True)
            raise
    
    async def delete_example(self, question: str, sql: str) -> bool:
        """
        Delete a specific example by question and SQL.
        
        Args:
            question: The question of the example to delete
            sql: The SQL of the example to delete
            
        Returns:
            True if deleted, False otherwise
        """
        try:
            example_id = self._generate_id(question, sql)
            await self._vector_store.delete_by_source_ids([example_id])
            logger.info(f"Deleted SQL example: {example_id[:12]}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete SQL example: {e}", exc_info=True)
            return False
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Check the health of the SQL examples store.
        
        Returns:
            Dict with health status information
        """
        try:
            exists = await self._vector_store.collection_exists()
            count = await self._vector_store.get_collection_count() if exists else 0
            
            return {
                "healthy": True,
                "backend": self.backend_type,
                "collection": self.collection_name,
                "collection_exists": exists,
                "example_count": count,
                "embedding_model": self.embedding_model
            }
        except Exception as e:
            return {
                "healthy": False,
                "backend": self.backend_type,
                "collection": self.collection_name,
                "error": str(e)
            }


def get_sql_examples_store(
    collection_name: str = SQL_EXAMPLES_COLLECTION,
    embedding_model: str = "text-embedding-ada-002"
) -> SQLExamplesStore:
    """
    Get the singleton SQLExamplesStore instance.
    
    Thread-safe singleton pattern ensures only one instance exists.
    
    Args:
        collection_name: Name of the vector collection
        embedding_model: OpenAI embedding model to use
        
    Returns:
        SQLExamplesStore singleton instance
    """
    global _sql_examples_store_instance
    
    with _sql_examples_store_lock:
        if _sql_examples_store_instance is None:
            _sql_examples_store_instance = SQLExamplesStore(
                collection_name=collection_name,
                embedding_model=embedding_model
            )
        return _sql_examples_store_instance


def reset_sql_examples_store() -> None:
    """
    Reset the singleton instance.
    
    Useful for testing or when configuration changes.
    """
    global _sql_examples_store_instance
    
    with _sql_examples_store_lock:
        _sql_examples_store_instance = None
        logger.info("SQLExamplesStore singleton reset")
