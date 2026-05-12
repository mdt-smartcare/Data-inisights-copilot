"""
Multi-Candidate SQL Generator — Generate and rank multiple SQL candidates.

Instead of trusting a single LLM output, this generates N candidates
(typically 3-5) with slight temperature variation, then ranks them
by confidence to select the best one.

This implements the candidate generation pattern from NL2SQL best practices:
1. Generate N candidates with sampling (small temperature)
2. Parse each into structured format
3. Self-check each candidate against schema
4. Rank by confidence signals (validity, complexity, coverage)
5. Return best candidate

Benefits:
- Higher accuracy for complex queries
- More robust handling of ambiguous questions
- Better utilization of LLM reasoning diversity
"""
import asyncio
import hashlib
from typing import Optional, List, Dict, Any, Callable, Awaitable
from dataclasses import dataclass, field
from enum import Enum

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

from app.core.utils.logging import get_logger
from .structured_output import StructuredOutputParser, StructuredSQLOutput, get_structured_parser

logger = get_logger(__name__)


class CandidateStatus(str, Enum):
    """Status of a SQL candidate."""
    VALID = "valid"
    INVALID_SCHEMA = "invalid_schema"
    INVALID_SYNTAX = "invalid_syntax"
    SELF_CHECK_FAILED = "self_check_failed"
    UNTESTED = "untested"


@dataclass
class SQLCandidate:
    """A single SQL candidate with metadata."""
    sql: str
    thinking: str
    raw_response: str
    
    # Validation status
    status: CandidateStatus = CandidateStatus.UNTESTED
    validation_errors: List[str] = field(default_factory=list)
    
    # Scoring signals
    schema_coverage: float = 0.0  # % of query tables in schema
    complexity_score: float = 0.0  # Lower is simpler (better)
    self_check_passed: bool = False
    
    # Final confidence
    confidence: float = 0.0
    
    def compute_confidence(self):
        """Compute overall confidence score."""
        if self.status != CandidateStatus.VALID:
            self.confidence = 0.0
            return
        
        # Base confidence from schema coverage
        base = self.schema_coverage * 0.4
        
        # Bonus for passing self-check
        self_check_bonus = 0.3 if self.self_check_passed else 0.0
        
        # Penalty for complexity (prefer simpler queries)
        complexity_penalty = min(0.2, self.complexity_score * 0.05)
        
        # Bonus for having thinking section
        thinking_bonus = 0.1 if self.thinking else 0.0
        
        self.confidence = min(1.0, base + self_check_bonus + thinking_bonus - complexity_penalty)


@dataclass
class CandidateGenerationResult:
    """Result of multi-candidate generation."""
    best_candidate: Optional[SQLCandidate]
    all_candidates: List[SQLCandidate]
    generation_count: int
    valid_count: int
    
    @property
    def success(self) -> bool:
        return self.best_candidate is not None and self.best_candidate.status == CandidateStatus.VALID


class MultiCandidateGenerator:
    """
    Generates and ranks multiple SQL candidates.
    
    Usage:
        generator = MultiCandidateGenerator(llm=llm, schema_validator=validate_fn)
        result = await generator.generate(
            question="How many active patients?",
            schema_context="TABLE patient_tracker...",
            system_prompt="You are a SQL expert...",
            num_candidates=3
        )
        if result.success:
            use_sql(result.best_candidate.sql)
    """
    
    def __init__(
        self,
        llm: BaseChatModel,
        parser: Optional[StructuredOutputParser] = None,
        schema_validator: Optional[Callable[[str, str], Dict]] = None,
        self_check_fn: Optional[Callable[[str, str, str], Awaitable[bool]]] = None,
    ):
        """
        Initialize multi-candidate generator.
        
        Args:
            llm: LLM for generation (will be called with varying temperatures)
            parser: Structured output parser
            schema_validator: Function(sql, schema) -> {"valid": bool, "errors": [...]}
            self_check_fn: Async function(question, sql, schema) -> bool for self-check
        """
        self.llm = llm
        self.parser = parser or get_structured_parser()
        self.schema_validator = schema_validator
        self.self_check_fn = self_check_fn
    
    async def generate(
        self,
        question: str,
        schema_context: str,
        system_prompt: str,
        num_candidates: int = 3,
        temperatures: Optional[List[float]] = None,
        run_self_check: bool = True
    ) -> CandidateGenerationResult:
        """
        Generate multiple SQL candidates and rank them.
        
        Args:
            question: User's natural language question
            schema_context: Database schema
            system_prompt: System prompt with rules
            num_candidates: Number of candidates to generate
            temperatures: Temperature values for each candidate (default: [0.0, 0.2, 0.3])
            run_self_check: Whether to run self-check on candidates
            
        Returns:
            CandidateGenerationResult with ranked candidates
        """
        if temperatures is None:
            # First candidate at temp=0 (deterministic), others with slight variation
            temperatures = [0.0] + [0.2 + 0.1 * i for i in range(num_candidates - 1)]
        
        temperatures = temperatures[:num_candidates]
        
        logger.info(f"Generating {num_candidates} SQL candidates for: {question[:50]}...")
        
        # Generate candidates in parallel
        candidates = await self._generate_candidates(
            question=question,
            schema_context=schema_context,
            system_prompt=system_prompt,
            temperatures=temperatures
        )
        
        # Validate and score candidates
        for candidate in candidates:
            self._validate_candidate(candidate, schema_context)
            self._score_complexity(candidate)
        
        # Run self-check on valid candidates
        if run_self_check and self.self_check_fn:
            valid_candidates = [c for c in candidates if c.status == CandidateStatus.VALID]
            if valid_candidates:
                await self._run_self_checks(valid_candidates, question, schema_context)
        
        # Compute confidence and rank
        for candidate in candidates:
            candidate.compute_confidence()
        
        candidates.sort(key=lambda c: c.confidence, reverse=True)
        
        # Select best
        valid_candidates = [c for c in candidates if c.status == CandidateStatus.VALID]
        best = valid_candidates[0] if valid_candidates else None
        
        logger.info(
            f"Generated {len(candidates)} candidates, {len(valid_candidates)} valid, "
            f"best confidence: {best.confidence:.2f}" if best else "no valid candidates"
        )
        
        return CandidateGenerationResult(
            best_candidate=best,
            all_candidates=candidates,
            generation_count=len(candidates),
            valid_count=len(valid_candidates)
        )
    
    async def _generate_candidates(
        self,
        question: str,
        schema_context: str,
        system_prompt: str,
        temperatures: List[float]
    ) -> List[SQLCandidate]:
        """Generate candidates in parallel with different temperatures."""
        
        async def generate_one(temp: float) -> SQLCandidate:
            try:
                # Configure LLM with temperature
                llm_with_temp = self.llm.bind(temperature=temp)
                
                prompt = ChatPromptTemplate.from_messages([
                    ("system", system_prompt),
                    ("user", "{question}")
                ])
                
                chain = prompt | llm_with_temp
                
                response = await chain.ainvoke({
                    "schema": schema_context,
                    "question": question
                })
                
                # Parse structured output
                parsed = self.parser.parse(response.content)
                
                return SQLCandidate(
                    sql=parsed.query,
                    thinking=parsed.thinking,
                    raw_response=parsed.raw_response
                )
                
            except Exception as e:
                logger.warning(f"Candidate generation failed at temp={temp}: {e}")
                return SQLCandidate(
                    sql="",
                    thinking="",
                    raw_response=str(e),
                    status=CandidateStatus.INVALID_SYNTAX,
                    validation_errors=[str(e)]
                )
        
        # Generate all candidates in parallel
        tasks = [generate_one(t) for t in temperatures]
        candidates = await asyncio.gather(*tasks)
        
        return list(candidates)
    
    def _validate_candidate(self, candidate: SQLCandidate, schema_context: str):
        """Validate candidate against schema."""
        if not candidate.sql:
            candidate.status = CandidateStatus.INVALID_SYNTAX
            candidate.validation_errors.append("Empty SQL")
            return
        
        # Basic syntax check
        sql_upper = candidate.sql.upper().strip()
        if not (sql_upper.startswith('SELECT') or sql_upper.startswith('WITH')):
            candidate.status = CandidateStatus.INVALID_SYNTAX
            candidate.validation_errors.append("SQL must start with SELECT or WITH")
            return
        
        # Schema validation if validator provided
        if self.schema_validator:
            try:
                result = self.schema_validator(candidate.sql, schema_context)
                if result.get("valid", True):
                    candidate.status = CandidateStatus.VALID
                    candidate.schema_coverage = result.get("coverage", 1.0)
                else:
                    candidate.status = CandidateStatus.INVALID_SCHEMA
                    candidate.validation_errors.extend(result.get("errors", []))
            except Exception as e:
                logger.warning(f"Schema validation error: {e}")
                # Assume valid if validation fails
                candidate.status = CandidateStatus.VALID
                candidate.schema_coverage = 0.8
        else:
            # No validator, assume valid
            candidate.status = CandidateStatus.VALID
            candidate.schema_coverage = 0.9
    
    def _score_complexity(self, candidate: SQLCandidate):
        """Score query complexity (lower is better)."""
        sql = candidate.sql.upper()
        
        score = 0.0
        
        # Count JOINs
        score += sql.count(' JOIN ') * 1.0
        
        # Count subqueries
        score += sql.count('SELECT ') * 0.5  # Extra SELECTs indicate subqueries
        
        # Count CTEs (WITH clauses)
        score += sql.count(' AS (') * 0.3
        
        # Count window functions
        score += sql.count(' OVER ') * 0.5
        
        # Normalize (0-5 range typical)
        candidate.complexity_score = min(5.0, score)
    
    async def _run_self_checks(
        self,
        candidates: List[SQLCandidate],
        question: str,
        schema_context: str
    ):
        """Run self-check on candidates."""
        
        async def check_one(candidate: SQLCandidate):
            try:
                passed = await self.self_check_fn(question, candidate.sql, schema_context)
                candidate.self_check_passed = passed
                if not passed:
                    candidate.status = CandidateStatus.SELF_CHECK_FAILED
            except Exception as e:
                logger.warning(f"Self-check failed: {e}")
                candidate.self_check_passed = False
        
        tasks = [check_one(c) for c in candidates]
        await asyncio.gather(*tasks)
    
    def deduplicate_candidates(
        self,
        candidates: List[SQLCandidate]
    ) -> List[SQLCandidate]:
        """Remove duplicate SQL queries (keep first occurrence)."""
        seen_hashes = set()
        unique = []
        
        for c in candidates:
            # Normalize SQL for comparison
            sql_hash = hashlib.md5(
                c.sql.lower().replace(' ', '').encode()
            ).hexdigest()
            
            if sql_hash not in seen_hashes:
                seen_hashes.add(sql_hash)
                unique.append(c)
        
        return unique


def create_schema_validator(query_validator) -> Callable[[str, str], Dict]:
    """
    Create a schema validator function from QueryValidator.
    
    Args:
        query_validator: QueryValidator instance
        
    Returns:
        Function suitable for MultiCandidateGenerator
    """
    def validate(sql: str, schema_context: str) -> Dict:
        result = query_validator.validate_sql(sql, schema_context)
        
        errors = []
        if result.invalid_tables:
            errors.extend([f"Unknown table: {t}" for t in result.invalid_tables])
        if result.invalid_columns:
            errors.extend([f"Unknown column: {t}.{c}" for t, c in result.invalid_columns])
        if result.fhir_violations:
            errors.extend(result.fhir_violations)
        
        return {
            "valid": result.is_valid,
            "errors": errors,
            "coverage": 1.0 - (len(result.invalid_tables) * 0.2)
        }
    
    return validate


async def create_self_check_fn(llm: BaseChatModel) -> Callable:
    """
    Create a self-check function using LLM.
    
    The self-check asks the LLM: "Does this SQL correctly answer the question?"
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are a SQL validator. Given a question, SQL query, and schema,
determine if the SQL correctly answers the question.

Respond with ONLY "yes" or "no".

Check for:
1. Does the query use the right tables for the question?
2. Does the query have correct joins?
3. Does the query have appropriate filters?
4. Does the query return the right columns?
"""),
        ("user", """Question: {question}

Schema:
{schema}

SQL:
{sql}

Does this SQL correctly answer the question? (yes/no)""")
    ])
    
    chain = prompt | llm
    
    async def self_check(question: str, sql: str, schema: str) -> bool:
        try:
            response = await chain.ainvoke({
                "question": question,
                "sql": sql,
                "schema": schema[:2000]  # Limit schema size
            })
            answer = response.content.strip().lower()
            return answer.startswith("yes")
        except Exception as e:
            logger.warning(f"Self-check LLM call failed: {e}")
            return True  # Assume valid on error
    
    return self_check
