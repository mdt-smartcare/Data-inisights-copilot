"""
Fast SQL Service — high-performance SQL pipeline.

Orchestrates the optimized SQL generation flow:
1. Template matching (instant, ~5ms) — skips LLM for common patterns
2. Memory recall (few-shot examples, ~20ms)
3. Unified LLM call (intent + relevance + SQL, ~1000ms)
4. CTE rewriting (deterministic transformation, ~10ms)
5. Execution + learning

Total latency: 50-200ms for template hits, ~1200ms for full LLM path
vs. original: ~3000-4000ms (multiple LLM calls + runtime introspection)

Key innovations:
- Pre-compiled manifest (like MDL) — no runtime schema discovery
- CTE injection — deterministic SQL transformation
- Query memory — self-learning from confirmed queries
- Single LLM call — collapsed intent/relevance/SQL
- Template engine — bypass LLM for common patterns
"""
import time
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from enum import Enum

from langchain_core.language_models import BaseChatModel

from app.core.utils.logging import get_logger
from .schema_manifest import SchemaManifest, get_or_build_manifest
from .cte_rewriter import CTERewriter, SQLDialect
from .query_memory import QueryMemory, format_few_shot_examples, LANCEDB_AVAILABLE
from .unified_sql_generator import (
    UnifiedSQLGenerator,
    QueryTemplateEngine,
    UnifiedSQLGeneratorFactory
)
from .schema_linker import SchemaLinker
from .schema_graph import SchemaGraph
from .data_dictionary import DataDictionary

logger = get_logger(__name__)


class ExecutionPath(str, Enum):
    """Which path was used to generate the SQL."""
    TEMPLATE = "template"  # QueryTemplateEngine hit — no LLM
    MEMORY = "memory"  # High-confidence memory recall — minimal LLM
    LLM = "llm"  # Full LLM generation
    HYBRID = "hybrid"  # Combined paths
    FALLBACK = "fallback"  # Legacy SQLService fallback


@dataclass
class FastSQLResult:
    """Result from FastSQLService."""
    # Core result
    sql: Optional[str]
    tables: List[str]
    is_successful: bool
    
    # Classification
    intent: str
    is_relevant: bool
    
    # Execution metadata
    execution_path: ExecutionPath
    confidence: float
    
    # Timing breakdown (all in ms)
    total_time_ms: float
    template_time_ms: float = 0
    memory_time_ms: float = 0
    llm_time_ms: float = 0
    rewrite_time_ms: float = 0
    
    # Query execution results (if executed)
    executed: bool = False
    result_data: Optional[Any] = None
    row_count: Optional[int] = None
    execution_time_ms: float = 0
    
    # Errors
    errors: List[str] = field(default_factory=list)
    
    # For learning
    question: str = ""
    few_shot_used: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "sql": self.sql,
            "tables": self.tables,
            "is_successful": self.is_successful,
            "intent": self.intent,
            "is_relevant": self.is_relevant,
            "execution_path": self.execution_path.value,
            "confidence": self.confidence,
            "timing": {
                "total_ms": self.total_time_ms,
                "template_ms": self.template_time_ms,
                "memory_ms": self.memory_time_ms,
                "llm_ms": self.llm_time_ms,
                "rewrite_ms": self.rewrite_time_ms,
                "execution_ms": self.execution_time_ms
            },
            "result": {
                "executed": self.executed,
                "row_count": self.row_count
            },
            "errors": self.errors
        }


class FastSQLService:
    """
    High-performance SQL generation service.
    
    Combines all optimizations:
    1. Pre-compiled manifest (vs runtime introspection)
    2. Template engine (skip LLM for common queries)
    3. Query memory (few-shot learning)
    4. Unified LLM (single call for intent+relevance+SQL)
    5. CTE rewriting (deterministic transformation)
    
    Usage:
        service = FastSQLService(agent_id, llm, schema_graph, data_dictionary)
        await service.initialize()
        
        result = await service.generate("How many active patients?")
        
        if result.is_successful:
            print(result.sql)
    """
    
    def __init__(
        self,
        agent_id: str,
        llm: BaseChatModel,
        schema_graph: SchemaGraph,
        data_dictionary: DataDictionary,
        dialect: SQLDialect = SQLDialect.DUCKDB,
        enable_templates: bool = True,
        enable_memory: bool = True,
        enable_learning: bool = True,
        strict_mode: bool = False
    ):
        """
        Initialize FastSQLService.
        
        Args:
            agent_id: Agent ID
            llm: LangChain LLM for generation
            schema_graph: Schema graph for the agent's database
            data_dictionary: Business definitions and synonyms
            dialect: SQL dialect (duckdb, postgres, etc.)
            enable_templates: Whether to use template matching
            enable_memory: Whether to use query memory
            enable_learning: Whether to store successful queries
            strict_mode: If True, reject queries with unknown tables
        """
        self.agent_id = agent_id
        self.llm = llm
        self.schema_graph = schema_graph
        self.data_dictionary = data_dictionary
        self.dialect = dialect
        self.enable_templates = enable_templates
        self.enable_memory = enable_memory
        self.enable_learning = enable_learning
        self.strict_mode = strict_mode
        
        # Components (initialized in initialize())
        self._manifest: Optional[SchemaManifest] = None
        self._rewriter: Optional[CTERewriter] = None
        self._memory: Optional[QueryMemory] = None
        self._template_engine: Optional[QueryTemplateEngine] = None
        self._schema_linker: Optional[SchemaLinker] = None
        self._generator: Optional[UnifiedSQLGenerator] = None
        
        self._initialized = False
    
    async def initialize(self, force_rebuild: bool = False) -> None:
        """
        Initialize all components.
        
        This should be called once when the service is created.
        It builds/loads the manifest and initializes memory.
        """
        start = time.time()
        
        # 1. Build or load manifest
        self._manifest = await get_or_build_manifest(
            self.agent_id,
            self.schema_graph,
            self.data_dictionary,
            force_rebuild=force_rebuild
        )
        
        # 2. Initialize CTE rewriter
        self._rewriter = CTERewriter(
            self._manifest,
            dialect=self.dialect,
            strict_mode=self.strict_mode
        )
        
        # 3. Initialize query memory (only if LanceDB is available)
        if self.enable_memory and LANCEDB_AVAILABLE:
            self._memory = QueryMemory(self.agent_id)
            await self._memory.index_schema(self._manifest, force_rebuild=force_rebuild)
        elif self.enable_memory:
            logger.info("QueryMemory disabled: LanceDB not available")
        
        # 4. Initialize template engine
        if self.enable_templates:
            self._template_engine = QueryTemplateEngine(self._manifest)
        
        # 5. Initialize schema linker
        self._schema_linker = SchemaLinker(
            self.schema_graph,
            self.data_dictionary,
            self.llm
        )
        
        self._initialized = True
        
        elapsed = (time.time() - start) * 1000
        logger.info(
            f"FastSQLService initialized in {elapsed:.0f}ms: "
            f"agent={self.agent_id}, "
            f"tables={self._manifest.table_count}, "
            f"templates={'on' if self.enable_templates else 'off'}, "
            f"memory={'on' if self.enable_memory else 'off'}"
        )
    
    async def generate(
        self,
        question: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        context: Optional[Dict[str, Any]] = None,
        skip_templates: bool = False,
        skip_memory: bool = False
    ) -> FastSQLResult:
        """
        Generate SQL for a question using the optimized pipeline.
        
        Pipeline:
        1. Template matching (instant) — try common patterns
        2. Schema linking — find relevant tables
        3. Memory recall — get few-shot examples
        4. Unified LLM — generate intent + SQL
        5. CTE rewriting — transform to executable SQL
        
        Args:
            question: User's question
            conversation_history: Previous messages for context
            context: Additional context (user_id, tenant_id, etc.)
            skip_templates: Force skip template matching
            skip_memory: Force skip memory recall
            
        Returns:
            FastSQLResult with SQL and metadata
        """
        if not self._initialized:
            await self.initialize()
        
        start = time.time()
        template_time = 0
        memory_time = 0
        llm_time = 0
        rewrite_time = 0
        
        # =====================================================================
        # Step 1: Template Matching (fastest path, ~5ms)
        # =====================================================================
        if self.enable_templates and self._template_engine and not skip_templates:
            template_start = time.time()
            template_result = self._template_engine.match(question)
            template_time = (time.time() - template_start) * 1000
            
            if template_result:
                # Template hit! Skip LLM entirely
                sql = template_result["sql"]
                tables = template_result["tables"]
                
                # Rewrite with CTEs
                rewrite_start = time.time()
                rewrite_result = self._rewriter.rewrite(sql)
                rewrite_time = (time.time() - rewrite_start) * 1000
                
                total_time = (time.time() - start) * 1000
                
                logger.info(
                    f"Template hit: {template_result['template_name']} "
                    f"({total_time:.0f}ms)"
                )
                
                return FastSQLResult(
                    sql=rewrite_result.rewritten_sql if rewrite_result.is_valid else sql,
                    tables=tables,
                    is_successful=True,
                    intent="sql",
                    is_relevant=True,
                    execution_path=ExecutionPath.TEMPLATE,
                    confidence=template_result["confidence"],
                    total_time_ms=total_time,
                    template_time_ms=template_time,
                    rewrite_time_ms=rewrite_time,
                    question=question
                )
        
        # =====================================================================
        # Step 2: Schema Linking (find relevant tables, ~10ms)
        # =====================================================================
        link_result = self._schema_linker.link(question)
        linked_tables = link_result.tables
        
        # =====================================================================
        # Step 3: Memory Recall (get few-shot examples, ~20ms)
        # =====================================================================
        few_shot_examples = ""
        few_shot_count = 0
        
        if self.enable_memory and self._memory and not skip_memory:
            memory_start = time.time()
            
            # Recall similar past queries
            recall_result = await self._memory.recall_queries(question, limit=3)
            if recall_result.items:
                few_shot_examples = format_few_shot_examples(recall_result.items)
                few_shot_count = len(recall_result.items)
            
            memory_time = (time.time() - memory_start) * 1000
        
        # =====================================================================
        # Step 4: Unified LLM Call (intent + relevance + SQL, ~1000ms)
        # =====================================================================
        llm_start = time.time()
        
        # Build generator with context (manifest provides schema context internally)
        generator = UnifiedSQLGeneratorFactory.get_generator(
            self.agent_id,
            self.llm,
            self._manifest,
            linked_tables
        )
        
        # Single LLM call
        llm_response = await generator.generate(
            question=question,
            few_shot_examples=few_shot_examples,
            conversation_history=conversation_history,
            context=context
        )
        
        llm_time = (time.time() - llm_start) * 1000
        
        # =====================================================================
        # Step 5: CTE Rewriting (deterministic transformation, ~10ms)
        # =====================================================================
        rewrite_result = None
        final_sql = llm_response.sql_query
        
        if llm_response.intent == "sql" and llm_response.sql_query:
            rewrite_start = time.time()
            
            # Apply CTE rewriting with context filters
            rewrite_result = self._rewriter.rewrite(
                llm_response.sql_query,
                extra_filters=self._build_context_filters(context)
            )
            
            if rewrite_result.is_valid:
                final_sql = rewrite_result.rewritten_sql
            else:
                logger.warning(f"CTE rewrite failed: {rewrite_result.errors}")
            
            rewrite_time = (time.time() - rewrite_start) * 1000
        
        total_time = (time.time() - start) * 1000
        
        # Build result
        result = FastSQLResult(
            sql=final_sql,
            tables=llm_response.tables_used or linked_tables,
            is_successful=llm_response.intent == "sql" and final_sql is not None,
            intent=llm_response.intent,
            is_relevant=llm_response.is_relevant,
            execution_path=ExecutionPath.LLM,
            confidence=llm_response.confidence,
            total_time_ms=total_time,
            template_time_ms=template_time,
            memory_time_ms=memory_time,
            llm_time_ms=llm_time,
            rewrite_time_ms=rewrite_time,
            question=question,
            few_shot_used=few_shot_count,
            errors=rewrite_result.errors if rewrite_result else []
        )
        
        logger.info(
            f"FastSQL generated in {total_time:.0f}ms "
            f"(template={template_time:.0f}, memory={memory_time:.0f}, "
            f"llm={llm_time:.0f}, rewrite={rewrite_time:.0f}): "
            f"intent={llm_response.intent}, confidence={llm_response.confidence:.2f}"
        )
        
        return result
    
    async def execute(
        self,
        result: FastSQLResult,
        executor: Any  # SQLExecutor or database connection
    ) -> FastSQLResult:
        """
        Execute the generated SQL and update result.
        
        Args:
            result: FastSQLResult from generate()
            executor: SQL executor or database connection
            
        Returns:
            Updated FastSQLResult with execution results
        """
        if not result.is_successful or not result.sql:
            return result
        
        exec_start = time.time()
        
        try:
            # Execute query
            if hasattr(executor, 'execute_raw'):
                # If it's our SQLExecutor
                exec_result = await executor.execute_raw(result.sql)
                result.result_data = exec_result.get("data")
                result.row_count = exec_result.get("row_count", 0)
            elif hasattr(executor, 'execute'):
                # Generic executor
                cursor = executor.execute(result.sql)
                result.result_data = cursor.fetchall()
                result.row_count = len(result.result_data)
            
            result.executed = True
            result.execution_time_ms = (time.time() - exec_start) * 1000
            
            # Learn from successful execution
            if self.enable_learning and result.row_count is not None:
                await self._learn_from_success(result)
            
        except Exception as e:
            result.errors.append(f"Execution error: {str(e)}")
            result.executed = False
            logger.error(f"SQL execution failed: {e}")
        
        return result
    
    async def _learn_from_success(self, result: FastSQLResult) -> None:
        """Store successful query for future recall."""
        if not self.enable_learning or not self._memory:
            return
        
        if not result.executed or result.row_count is None:
            return
        
        # Only learn from queries that returned reasonable results
        if result.row_count == 0:
            return
        
        try:
            await self._memory.store_query(
                question=result.question,
                sql=result.sql,
                tables_used=result.tables,
                feedback="positive",
                execution_time_ms=result.execution_time_ms,
                row_count=result.row_count
            )
        except Exception as e:
            logger.warning(f"Failed to store query in memory: {e}")
    
    async def provide_feedback(
        self,
        result: FastSQLResult,
        feedback: str,  # "positive", "negative"
        correction: Optional[str] = None
    ) -> None:
        """
        Record feedback for a query result.
        
        Args:
            result: The FastSQLResult to provide feedback for
            feedback: "positive" or "negative"
            correction: If negative, the correct SQL
        """
        if not self.enable_learning or not self._memory:
            return
        
        if feedback == "positive" and not result.executed:
            # Store if not already stored during execution
            await self._memory.store_query(
                question=result.question,
                sql=result.sql,
                tables_used=result.tables,
                feedback="positive"
            )
        elif feedback == "negative" and correction:
            # Store the correction as a positive example
            await self._memory.store_query(
                question=result.question,
                sql=correction,
                tables_used=result.tables,
                feedback="positive",
                tags=["corrected"]
            )
    
    def _build_context_filters(
        self,
        context: Optional[Dict[str, Any]]
    ) -> Dict[str, List[str]]:
        """Build extra filters from context (e.g., tenant_id)."""
        extra_filters = {}
        
        if not context:
            return extra_filters
        
        # Multi-tenant filter
        if "tenant_id" in context:
            tenant_id = context["tenant_id"]
            for model_name in self._manifest.models:
                model = self._manifest.models[model_name]
                if any(col.name == "tenant_id" for col in model.columns):
                    if model_name not in extra_filters:
                        extra_filters[model_name] = []
                    extra_filters[model_name].append(f"tenant_id = '{tenant_id}'")
        
        # Organization filter
        if "organization_id" in context:
            org_id = context["organization_id"]
            for model_name in self._manifest.models:
                model = self._manifest.models[model_name]
                if any(col.name == "organization_id" for col in model.columns):
                    if model_name not in extra_filters:
                        extra_filters[model_name] = []
                    extra_filters[model_name].append(f"organization_id = '{org_id}'")
        
        return extra_filters
    
    def get_stats(self) -> Dict[str, Any]:
        """Get service statistics."""
        stats = {
            "agent_id": self.agent_id,
            "initialized": self._initialized,
            "dialect": self.dialect.value,
            "features": {
                "templates": self.enable_templates,
                "memory": self.enable_memory,
                "learning": self.enable_learning,
                "strict_mode": self.strict_mode
            }
        }
        
        if self._manifest:
            stats["manifest"] = {
                "version": self._manifest.version,
                "tables": self._manifest.table_count,
                "columns": self._manifest.column_count,
                "relationships": self._manifest.relationship_count
            }
        
        if self._memory:
            stats["memory"] = self._memory.get_stats()
        
        return stats
    
    async def rebuild_manifest(self) -> None:
        """Force rebuild of manifest (e.g., after schema change)."""
        await self.initialize(force_rebuild=True)


class FastSQLServiceFactory:
    """
    Factory for creating FastSQLService instances.
    
    Manages service lifecycle and caching per agent.
    """
    
    _instances: Dict[str, FastSQLService] = {}
    
    @classmethod
    async def get_service(
        cls,
        agent_id: str,
        llm: BaseChatModel,
        schema_graph: SchemaGraph,
        data_dictionary: DataDictionary,
        **kwargs
    ) -> FastSQLService:
        """
        Get or create a FastSQLService for an agent.
        
        Services are cached per agent_id.
        """
        if agent_id not in cls._instances:
            service = FastSQLService(
                agent_id=agent_id,
                llm=llm,
                schema_graph=schema_graph,
                data_dictionary=data_dictionary,
                **kwargs
            )
            await service.initialize()
            cls._instances[agent_id] = service
        
        return cls._instances[agent_id]
    
    @classmethod
    def invalidate(cls, agent_id: str) -> None:
        """Remove cached service for an agent."""
        if agent_id in cls._instances:
            del cls._instances[agent_id]
    
    @classmethod
    def invalidate_all(cls) -> None:
        """Clear all cached services."""
        cls._instances.clear()


class IntegratedFastSQLServiceFactory:
    """
    Production factory for FastSQLService that integrates with repositories.
    
    This is the recommended way to create FastSQLService instances in the 
    application context. It handles:
    - Loading agent configuration from database
    - Building SchemaGraph from data source
    - Loading DataDictionary per agent
    - Creating the LLM instance
    - Caching services per agent
    
    Usage:
        factory = IntegratedFastSQLServiceFactory(
            config_repo=AgentConfigRepository(db),
            data_source_repo=DataSourceRepository(db),
            ai_model_repo=AIModelRepository(db)
        )
        
        # Get service for an agent (async)
        service = await factory.create(agent_id)
        
        # Or use __call__ shorthand
        service = await factory(agent_id)
    """
    
    _cache: Dict[str, FastSQLService] = {}
    
    def __init__(
        self,
        config_repo,  # AgentConfigRepository
        data_source_repo,  # DataSourceRepository
        ai_model_repo,  # AIModelRepository
    ):
        """
        Initialize factory with repository dependencies.
        
        Args:
            config_repo: AgentConfigRepository instance
            data_source_repo: DataSourceRepository instance
            ai_model_repo: AIModelRepository instance
        """
        self.config_repo = config_repo
        self.data_source_repo = data_source_repo
        self.ai_model_repo = ai_model_repo
    
    async def __call__(
        self,
        agent_id,  # UUID or str
        enable_fast_mode: bool = True
    ) -> Optional[FastSQLService]:
        """Primary factory method - create FastSQLService for an agent."""
        return await self.create(agent_id, enable_fast_mode)
    
    async def create(
        self,
        agent_id,  # UUID or str
        enable_fast_mode: bool = True,
        enable_templates: bool = True,
        enable_memory: bool = True,
        enable_learning: bool = True
    ) -> Optional[FastSQLService]:
        """
        Create a FastSQLService for the given agent.
        
        This method:
        1. Loads agent config from database
        2. Gets data source connection
        3. Builds SchemaGraph from database
        4. Loads DataDictionary for agent
        5. Creates LLM instance
        6. Initializes FastSQLService
        
        Args:
            agent_id: Agent UUID
            enable_fast_mode: Enable optimized pipeline (templates, memory)
            enable_templates: Enable template matching
            enable_memory: Enable query memory/few-shot
            enable_learning: Store successful queries
            
        Returns:
            FastSQLService instance or None if configuration failed
        """
        from uuid import UUID
        from sqlalchemy import create_engine
        
        agent_id_str = str(agent_id)
        logger.info(f"FastSQL create: agent_id={agent_id_str}")
        
        # Check cache first
        if agent_id_str in self._cache:
            logger.info("FastSQL: returning cached service")
            return self._cache[agent_id_str]
        
        try:
            # 1. Get agent config
            if isinstance(agent_id, str):
                agent_id = UUID(agent_id)
            
            logger.info(f"FastSQL: getting config for agent_id={agent_id}")
            config = await self.config_repo.get_active_config(agent_id)
            if not config:
                logger.warning(f"FastSQL: No active config for agent: {agent_id}")
                return None
            
            if not config.data_source_id:
                logger.warning("FastSQL: Agent config has no data_source_id")
                return None
            
            # 2. Get data source
            logger.info(f"FastSQL: getting data source {config.data_source_id}")
            data_source = await self.data_source_repo.get_by_id(config.data_source_id)
            if not data_source:
                logger.warning(f"FastSQL: Data source not found: {config.data_source_id}")
                return None
            
            # 3. Build database URL
            logger.info("FastSQL: building db_url")
            db_url = await self._get_db_url(data_source)
            if not db_url:
                logger.warning("FastSQL: Could not determine database URL for data source")
                return None
            
            # 4. Create SchemaGraph
            logger.info("FastSQL: creating SchemaGraph")
            engine = create_engine(db_url, pool_pre_ping=True, pool_size=1)
            schema_graph = SchemaGraph(engine)
            
            # 5. Load DataDictionary
            logger.info("FastSQL: loading DataDictionary")
            data_dictionary = await self._load_data_dictionary(config)
            
            # 6. Create LLM
            logger.info("FastSQL: creating LLM")
            llm = await self._create_llm(config)
            if not llm:
                logger.warning("FastSQL: Could not create LLM for agent")
                return None
            
            # 7. Determine dialect
            dialect = self._detect_dialect(db_url)
            logger.info(f"FastSQL: dialect={dialect.value}")
            
            # 8. Create FastSQLService
            logger.info("FastSQL: creating FastSQLService instance")
            service = FastSQLService(
                agent_id=agent_id_str,
                llm=llm,
                schema_graph=schema_graph,
                data_dictionary=data_dictionary,
                dialect=dialect,
                enable_templates=enable_templates if enable_fast_mode else False,
                enable_memory=enable_memory if enable_fast_mode else False,
                enable_learning=enable_learning if enable_fast_mode else False,
            )
            
            # 9. Initialize (builds manifest, indexes schema)
            logger.info("FastSQL: initializing service")
            await service.initialize()
            
            # 10. Cache and return
            self._cache[agent_id_str] = service
            
            logger.info(
                f"⚡ FastSQLService created for agent {agent_id}: "
                f"dialect={dialect.value}, "
                f"tables={service.get_stats().get('manifest', {}).get('tables', 0)}"
            )
            
            return service
            
        except Exception as e:
            logger.error(f"Failed to create FastSQLService: {e}", exc_info=True)
            return None
    
    async def _get_db_url(self, data_source) -> Optional[str]:
        """Get database URL from data source."""
        if data_source.source_type == "database":
            db_url = data_source.db_url
            if db_url and db_url.startswith("encrypted:"):
                from app.core.encryption import decrypt_value
                db_url = decrypt_value(db_url)
            return db_url
        
        elif data_source.source_type == "file":
            duckdb_path = data_source.duckdb_file_path
            if duckdb_path:
                from app.modules.data_sources.utils import resolve_duckdb_path
                resolved_path = resolve_duckdb_path(duckdb_path)
                return f"duckdb:///{resolved_path}"
        
        return None
    
    async def _load_data_dictionary(self, config) -> DataDictionary:
        """Load DataDictionary for agent config — agent JSON merged on top of global YAML."""
        from app.modules.chat.query.data_dictionary import get_agent_data_dictionary

        agent_id_str = str(config.agent_id) if hasattr(config, 'agent_id') else None
        config_json = config.data_dictionary if hasattr(config, 'data_dictionary') else None

        return get_agent_data_dictionary(
            agent_id=agent_id_str,
            config_json=config_json,
            merge_with_global=True,
        )
    
    async def _create_llm(self, config) -> Optional[BaseChatModel]:
        """Create LLM instance for SQL generation."""
        try:
            # Create LLM using helper
            from app.modules.chat.llm_helper import LLMHelper
            
            # For FastSQL, we want a low temperature for deterministic SQL
            llm_helper = LLMHelper(None, config.agent_id)  # None for db, will use default
            return await llm_helper.get_llm(temperature=0.1)
            
        except Exception as e:
            logger.error(f"Failed to create LLM: {e}")
            return None
    
    def _detect_dialect(self, db_url: str) -> SQLDialect:
        """Detect SQL dialect from database URL."""
        url_lower = db_url.lower()
        if "duckdb" in url_lower:
            return SQLDialect.DUCKDB
        elif "postgresql" in url_lower or "postgres" in url_lower:
            return SQLDialect.POSTGRES
        elif "mysql" in url_lower:
            return SQLDialect.MYSQL
        elif "sqlite" in url_lower:
            return SQLDialect.SQLITE
        else:
            return SQLDialect.DUCKDB
    
    def invalidate(self, agent_id: str) -> None:
        """Remove cached service for an agent."""
        agent_id_str = str(agent_id)
        if agent_id_str in self._cache:
            del self._cache[agent_id_str]
    
    def invalidate_all(self) -> None:
        """Clear all cached services."""
        self._cache.clear()


# =============================================================================
# Example Usage
# =============================================================================
"""
Example 1: Basic Query Generation
---------------------------------
from app.modules.chat.query.fast_sql_service import IntegratedFastSQLServiceFactory

# Create factory (typically done once at app startup)
factory = IntegratedFastSQLServiceFactory(
    config_repo=AgentConfigRepository(db),
    data_source_repo=DataSourceRepository(db),
    ai_model_repo=AIModelRepository(db)
)

# Get service for an agent
service = await factory(agent_id)

# Generate SQL
result = await service.generate("How many active patients are there?")

if result.is_successful:
    print(f"SQL: {result.sql}")
    print(f"Path: {result.execution_path}")  # TEMPLATE, MEMORY, or LLM
    print(f"Time: {result.total_time_ms}ms")


Example 2: With Execution
-------------------------
result = await service.generate("What are the top 10 sites by patient count?")

if result.is_successful:
    # Execute the SQL
    result = await service.execute(result, sql_executor)
    
    print(f"Rows: {result.row_count}")
    print(f"Data: {result.result_data}")


Example 3: FHIR Healthcare Queries
----------------------------------
# Template-matched queries (instant, ~5ms)
result = await service.generate("Show me all active patients")
result = await service.generate("How many screenings this month?")
result = await service.generate("List encounters by type")

# Complex queries (LLM path, ~1200ms)
result = await service.generate(
    "What is the average time between patient enrollment and first screening?"
)

# The UnifiedResponse includes:
# - intent: "sql", "vector", "hybrid", "general", "clarification"
# - is_relevant: True/False (relevance check)
# - sql_query: The generated SQL
# - confidence: 0.0-1.0


Example 4: Learning from Feedback
---------------------------------
result = await service.generate("Count patients by gender")

# User confirms result is correct
await service.provide_feedback(result, "positive")

# OR user provides correction
await service.provide_feedback(
    result, 
    "negative", 
    correction="SELECT gender, COUNT(*) FROM patient_tracker GROUP BY gender"
)


Example 5: Integration with ChatService
---------------------------------------
# In ChatService._handle_sql_intent():

# Check if FastSQL mode is enabled
if self._use_fast_sql:
    fast_service = await self._fast_sql_factory(request.agent_id)
    if fast_service:
        result = await fast_service.generate(query)
        
        if result.is_successful and result.intent == "sql":
            # Execute via existing SQLService
            execution_result = await sql_service.execute_raw_async(result.sql)
            return execution_result, result.to_dict()
        elif result.intent in ("vector", "hybrid"):
            # Route to vector search
            return await self._handle_vector_intent(...)
        else:
            # Clarification or general query
            return result.errors[0] if result.errors else "Please clarify your question."
"""
