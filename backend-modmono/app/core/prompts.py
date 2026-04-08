"""
Prompt Loader Utility

Centralized utility for loading prompt templates from markdown files.
All prompts should be stored in agent_spec/prompt_templates/ directory.
"""
import os
from pathlib import Path
from functools import lru_cache
from typing import Optional

from app.core.utils.logging import get_logger

logger = get_logger(__name__)

# Base path for prompt templates
_PROMPT_TEMPLATES_DIR: Optional[Path] = None


def _get_templates_dir() -> Path:
    """Get the prompt templates directory path."""
    global _PROMPT_TEMPLATES_DIR
    
    if _PROMPT_TEMPLATES_DIR is not None:
        return _PROMPT_TEMPLATES_DIR
    
    # Try multiple possible locations
    possible_paths = [
        # From backend-modmono/app/core/
        Path(__file__).parent.parent.parent.parent / "agent_spec" / "prompt_templates",
        # From workspace root
        Path.cwd() / "agent_spec" / "prompt_templates",
        # Parent directory
        Path.cwd().parent / "agent_spec" / "prompt_templates",
    ]
    
    for path in possible_paths:
        if path.exists() and path.is_dir():
            _PROMPT_TEMPLATES_DIR = path
            logger.info(f"Prompt templates directory found: {path}")
            return path
    
    # Fallback to first option even if it doesn't exist
    _PROMPT_TEMPLATES_DIR = possible_paths[0]
    logger.warning(f"Prompt templates directory not found, using: {_PROMPT_TEMPLATES_DIR}")
    return _PROMPT_TEMPLATES_DIR


@lru_cache(maxsize=32)
def load_prompt(template_name: str, fallback: Optional[str] = None) -> str:
    """
    Load a prompt template from a markdown file.
    
    Args:
        template_name: Name of the template file (with or without .md extension)
        fallback: Optional fallback text if the file is not found
        
    Returns:
        The prompt template content as a string
        
    Example:
        >>> prompt = load_prompt("sql_generator")
        >>> prompt = load_prompt("intent_router", fallback="You are a helpful assistant.")
    """
    # Ensure .md extension
    if not template_name.endswith(".md"):
        template_name = f"{template_name}.md"
    
    template_path = _get_templates_dir() / template_name
    
    try:
        if template_path.exists():
            content = template_path.read_text(encoding="utf-8")
            logger.debug(f"Loaded prompt template: {template_name}")
            return content
        else:
            logger.warning(f"Prompt template not found: {template_path}")
            if fallback:
                return fallback
            raise FileNotFoundError(f"Prompt template not found: {template_name}")
    except Exception as e:
        logger.error(f"Failed to load prompt template {template_name}: {e}")
        if fallback:
            return fallback
        raise


def clear_prompt_cache():
    """Clear the prompt cache. Useful for testing or hot-reloading."""
    load_prompt.cache_clear()
    logger.info("Prompt cache cleared")


# Convenience functions for commonly used prompts
def get_sql_generator_prompt() -> str:
    """Get the SQL generator prompt."""
    return load_prompt("sql_generator", fallback="You are a SQL expert. Generate a PostgreSQL query.")


def get_intent_router_prompt() -> str:
    """Get the intent router prompt."""
    return load_prompt("intent_router", fallback="You are an intent classifier.")


def get_followup_generator_prompt() -> str:
    """Get the follow-up questions generator prompt."""
    return load_prompt("followup_generator", fallback="You are a helpful assistant that suggests follow-up questions.")


def get_data_analyst_prompt() -> str:
    """Get the data analyst response prompt."""
    return load_prompt("data_analyst", fallback="You are a helpful data analyst.")


def get_rag_synthesis_prompt() -> str:
    """Get the RAG synthesis prompt."""
    return load_prompt("rag_synthesis", fallback="You are a helpful assistant. Answer based on the provided context.")


def get_chart_generator_prompt() -> str:
    """Get the chart generation rules prompt."""
    return load_prompt("chart_generator", fallback="Generate chart JSON when data is suitable for visualization.")


def get_query_planner_prompt() -> str:
    """Get the query planner prompt."""
    return load_prompt("query_planner", fallback="You are a SQL Query Planner.")


def get_reflection_critique_prompt() -> str:
    """Get the reflection/critique prompt."""
    return load_prompt("reflection_critique", fallback="You are a Senior SQL Expert and Security Auditor.")


def get_query_rewriter_prompt() -> str:
    """Get the query rewriter prompt."""
    return load_prompt("query_rewriter", fallback="You are a query rewriter.")


def get_base_system_prompt() -> str:
    """Get the base system prompt."""
    return load_prompt("base_system", fallback="You are a helpful AI assistant.")
