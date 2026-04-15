"""
System default configurations.

Provides default settings for agent creation, including:
- Chunking configuration
- PII exclusion rules
- Medical context templates
- RAG parameters
- Embedding model defaults
- LLM provider defaults

New agents inherit these defaults and can customize them individually.
"""
from typing import Dict, Any, List
from dataclasses import dataclass, asdict


@dataclass
class ChunkingDefaults:
    """Default chunking configuration for new agents."""
    parent_chunk_size: int = 2000
    child_chunk_size: int = 400
    overlap: int = 200
    min_chunk_length: int = 50
    separators: List[str] = None
    
    def __post_init__(self):
        if self.separators is None:
            self.separators = ["\n\n", "\n", ". ", " ", ""]
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PIIDefaults:
    """Default PII exclusion rules for new agents."""
    exclude_patient_names: bool = True
    exclude_patient_ids: bool = False
    exclude_ssn: bool = True
    exclude_phone_numbers: bool = True
    exclude_emails: bool = False
    exclude_addresses: bool = True
    exclude_dob: bool = False
    exclude_medical_record_numbers: bool = False
    custom_patterns: List[str] = None
    
    def __post_init__(self):
        if self.custom_patterns is None:
            self.custom_patterns = []
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MedicalContextDefaults:
    """Default medical terminology and context settings."""
    include_icd_codes: bool = True
    include_cpt_codes: bool = True
    include_medications: bool = True
    include_lab_results: bool = True
    include_vital_signs: bool = True
    include_diagnoses: bool = True
    include_procedures: bool = True
    terminology_systems: List[str] = None
    
    def __post_init__(self):
        if self.terminology_systems is None:
            self.terminology_systems = ["ICD-10", "CPT", "SNOMED", "LOINC", "RxNorm"]
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RAGDefaults:
    """Default RAG (Retrieval Augmented Generation) parameters."""
    top_k: int = 5
    similarity_threshold: float = 0.7
    reranking_enabled: bool = False
    reranking_top_k: int = 10
    max_context_length: int = 4000
    use_parent_chunks: bool = True
    use_child_chunks: bool = True
    hybrid_search: bool = False
    hybrid_alpha: float = 0.5  # 0 = pure semantic, 1 = pure keyword
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EmbeddingDefaults:
    """Default embedding model configuration."""
    provider: str = "openai"
    model: str = "text-embedding-3-small"
    dimensions: int = 1536
    batch_size: int = 100
    max_input_tokens: int = 8191
    normalize: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LLMDefaults:
    """Default LLM configuration."""
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    temperature: float = 0.3
    max_tokens: int = 2000
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    streaming: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class VectorStoreDefaults:
    """Default vector store configuration."""
    provider: str = "chroma"
    collection_prefix: str = "agent"
    distance_metric: str = "cosine"  # cosine, l2, ip
    index_type: str = "hnsw"
    persist_directory: str = "./data/indexes"
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SystemPromptDefaults:
    """Default system prompt templates."""
    base_system_prompt: str = """You are a helpful AI assistant specialized in analyzing healthcare data.

You have access to clinical information and should:
1. Provide accurate, evidence-based responses
2. Cite specific data sources when possible
3. Acknowledge uncertainty when information is incomplete
4. Never fabricate or guess clinical information
5. Respect patient privacy and confidentiality

Always ground your responses in the provided context."""
    
    query_prefix: str = """Using the following clinical context, answer the user's question accurately and concisely.

Context:
{context}

Question: {question}

Answer:"""
    
    sql_system_prompt: str = """You are an expert SQL query generator for healthcare databases.

Generate safe, read-only SQL queries based on user questions. Follow these rules:
1. Only generate SELECT queries (no INSERT, UPDATE, DELETE, DROP)
2. Use proper JOINs and WHERE clauses
3. Include LIMIT clauses to prevent large result sets
4. Use descriptive column aliases
5. Add comments explaining complex logic

Always validate queries before execution."""
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ============================================
# Global Defaults Container
# ============================================

class SystemDefaults:
    """
    Container for all system default configurations.
    
    Provides access to default settings that new agents inherit.
    Individual agents can override these on a per-agent basis.
    """
    
    def __init__(self):
        self.chunking = ChunkingDefaults()
        self.pii = PIIDefaults()
        self.medical_context = MedicalContextDefaults()
        self.rag = RAGDefaults()
        self.embedding = EmbeddingDefaults()
        self.llm = LLMDefaults()
        self.vector_store = VectorStoreDefaults()
        self.system_prompts = SystemPromptDefaults()
    
    def to_dict(self) -> Dict[str, Any]:
        """Export all defaults as dictionary."""
        return {
            "chunking": self.chunking.to_dict(),
            "pii": self.pii.to_dict(),
            "medical_context": self.medical_context.to_dict(),
            "rag": self.rag.to_dict(),
            "embedding": self.embedding.to_dict(),
            "llm": self.llm.to_dict(),
            "vector_store": self.vector_store.to_dict(),
            "system_prompts": self.system_prompts.to_dict(),
        }
    
    def get_agent_creation_defaults(self) -> Dict[str, Any]:
        """
        Get default configuration for creating a new agent.
        
        Returns:
            Dictionary with all default configurations
        """
        return self.to_dict()


# ============================================
# Singleton Instance
# ============================================

_system_defaults: SystemDefaults = None


def get_system_defaults() -> SystemDefaults:
    """
    Get the global system defaults instance.
    
    Returns:
        SystemDefaults singleton
    
    Usage:
        defaults = get_system_defaults()
        new_agent_config = defaults.get_agent_creation_defaults()
    """
    global _system_defaults
    if _system_defaults is None:
        _system_defaults = SystemDefaults()
    return _system_defaults


def reset_system_defaults() -> None:
    """Reset system defaults to factory settings (mainly for testing)."""
    global _system_defaults
    _system_defaults = None
