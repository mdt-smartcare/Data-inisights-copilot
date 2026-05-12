"""
Token Budget Manager for Context Assembly

Ensures schema context stays within LLM token limits by:
- Estimating token counts accurately
- Prioritizing important tables
- Truncating or summarizing when needed

Usage:
    from app.modules.chat.query.token_budget import TokenBudgetManager
    
    manager = TokenBudgetManager(max_tokens=8000)
    truncated = manager.fit_to_budget(schema_context, tables_priority)
"""
import re
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

from app.core.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class TokenEstimate:
    """Token count estimate for content."""
    text: str
    estimated_tokens: int
    char_count: int


class TokenBudgetManager:
    """
    Manages token budget for context assembly.
    
    Features:
    - Accurate token estimation using tiktoken (fallback to char-based)
    - Priority-based table selection
    - Intelligent truncation that preserves important columns
    """
    
    # Default tokens per character ratio
    DEFAULT_CHARS_PER_TOKEN = 4.0
    
    # Reserve tokens for prompt template, question, etc.
    RESERVED_TOKENS = 1000
    
    def __init__(
        self,
        max_tokens: int = 8000,
        use_tiktoken: bool = True
    ):
        """
        Initialize token budget manager.
        
        Args:
            max_tokens: Maximum total tokens for context
            use_tiktoken: Whether to use tiktoken for accurate counting
        """
        self.max_tokens = max_tokens
        self._encoder = None
        
        if use_tiktoken:
            try:
                import tiktoken
                self._encoder = tiktoken.get_encoding("cl100k_base")
                logger.debug("Using tiktoken for token counting")
            except ImportError:
                logger.debug("tiktoken not available, using char-based estimation")
    
    def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for text.
        
        Args:
            text: Text to estimate
            
        Returns:
            Estimated token count
        """
        if self._encoder:
            try:
                return len(self._encoder.encode(text))
            except Exception:
                pass
        
        # Fallback: character-based estimation
        return int(len(text) / self.DEFAULT_CHARS_PER_TOKEN)
    
    def fit_schema_to_budget(
        self,
        tables_ddl: Dict[str, str],
        table_priorities: Dict[str, float],
        additional_context: str = ""
    ) -> Tuple[str, List[str]]:
        """
        Fit schema DDL to token budget.
        
        Args:
            tables_ddl: Dict mapping table name to DDL string
            table_priorities: Dict mapping table name to priority score (higher = more important)
            additional_context: Additional context to include (data dictionary, etc.)
            
        Returns:
            Tuple of (fitted_schema_string, included_table_names)
        """
        available_budget = self.max_tokens - self.RESERVED_TOKENS
        
        # Account for additional context
        additional_tokens = self.estimate_tokens(additional_context)
        available_budget -= additional_tokens
        
        if available_budget <= 0:
            logger.warning("No token budget available for schema after additional context")
            return "", []
        
        # Sort tables by priority (highest first)
        sorted_tables = sorted(
            tables_ddl.keys(),
            key=lambda t: table_priorities.get(t, 0.0),
            reverse=True
        )
        
        included_ddl = []
        included_tables = []
        current_tokens = 0
        
        for table in sorted_tables:
            ddl = tables_ddl[table]
            ddl_tokens = self.estimate_tokens(ddl)
            
            if current_tokens + ddl_tokens <= available_budget:
                included_ddl.append(ddl)
                included_tables.append(table)
                current_tokens += ddl_tokens
            else:
                # Try to fit a truncated version
                truncated = self._truncate_ddl(ddl, available_budget - current_tokens)
                if truncated:
                    truncated_tokens = self.estimate_tokens(truncated)
                    if current_tokens + truncated_tokens <= available_budget:
                        included_ddl.append(truncated)
                        included_tables.append(f"{table} (truncated)")
                        current_tokens += truncated_tokens
                
                # If we couldn't fit even truncated, check if we should continue
                # looking for smaller tables
                continue
        
        logger.info(
            f"Token budget: {current_tokens}/{available_budget} tokens used, "
            f"{len(included_tables)}/{len(tables_ddl)} tables included"
        )
        
        return "\n\n".join(included_ddl), included_tables
    
    def _truncate_ddl(
        self,
        ddl: str,
        max_tokens: int,
        min_columns: int = 5
    ) -> Optional[str]:
        """
        Truncate DDL to fit within token limit.
        
        Preserves:
        - Table name
        - Primary key columns
        - First N columns
        - Closing parenthesis
        """
        if max_tokens <= 100:
            return None  # Too small to be useful
        
        lines = ddl.split("\n")
        
        if len(lines) <= 3:
            return None  # Already minimal
        
        # Keep first line (CREATE TABLE), a few columns, and last line
        header = lines[0]
        footer = lines[-1] if lines[-1].strip() in (");", ")") else ");"
        
        # Find column lines (typically start with whitespace and a column name)
        column_lines = [
            l for l in lines[1:-1]
            if l.strip() and not l.strip().startswith("--")
        ]
        
        # Prioritize PRIMARY KEY columns
        pk_lines = [l for l in column_lines if "PRIMARY KEY" in l.upper()]
        other_lines = [l for l in column_lines if l not in pk_lines]
        
        # Take PK columns plus first N others
        selected_lines = pk_lines + other_lines[:min_columns - len(pk_lines)]
        
        truncated = [header]
        truncated.extend(selected_lines)
        truncated.append(f"  -- ... {len(column_lines) - len(selected_lines)} more columns")
        truncated.append(footer)
        
        result = "\n".join(truncated)
        
        if self.estimate_tokens(result) <= max_tokens:
            return result
        
        return None
    
    def summarize_schema(
        self,
        tables_ddl: Dict[str, str],
        max_tokens: int
    ) -> str:
        """
        Create a summary of schema when full DDL doesn't fit.
        
        Args:
            tables_ddl: Dict mapping table name to DDL
            max_tokens: Maximum tokens for summary
            
        Returns:
            Summarized schema string
        """
        summary_lines = ["SCHEMA SUMMARY:"]
        
        for table, ddl in tables_ddl.items():
            # Count columns
            column_count = ddl.count(",") + 1  # Rough estimate
            
            # Extract column names
            column_names = re.findall(r'^\s+(\w+)\s+', ddl, re.MULTILINE)
            col_preview = ", ".join(column_names[:5])
            if len(column_names) > 5:
                col_preview += f", ... (+{len(column_names) - 5} more)"
            
            summary_lines.append(f"- {table}: {col_preview}")
            
            if self.estimate_tokens("\n".join(summary_lines)) > max_tokens:
                summary_lines.pop()
                summary_lines.append(f"... and {len(tables_ddl) - len(summary_lines) + 1} more tables")
                break
        
        return "\n".join(summary_lines)
    
    def get_available_budget(self, used_tokens: int = 0) -> int:
        """Calculate remaining token budget."""
        return max(0, self.max_tokens - self.RESERVED_TOKENS - used_tokens)


def get_token_budget_manager(max_tokens: int = 8000) -> TokenBudgetManager:
    """Factory function for TokenBudgetManager."""
    return TokenBudgetManager(max_tokens=max_tokens)
