import re
from typing import Optional

def validate_vector_db_name(name: str) -> tuple[bool, str]:
    """
    Validates a Vector DB name.
    Returns (is_valid, error_message).
    """
    if not name:
        return False, "Name is required"
    
    if not re.match(r'^[a-zA-Z0-9_]+$', name):
        return False, "Only alphanumeric characters and underscores allowed"
    
    if len(name) < 3:
        return False, "Name must be at least 3 characters"
    
    if len(name) > 64:
        return False, "Name must be at most 64 characters"
    
    return True, "Name is valid"


def sanitize_name(name: str) -> str:
    """
    Sanitize a name for use in file paths and collection names.
    
    - Converts to lowercase
    - Replaces spaces and special chars with underscores
    - Removes consecutive underscores
    - Truncates to reasonable length
    """
    if not name:
        return ""
    
    # Lowercase and replace non-alphanumeric with underscores
    sanitized = re.sub(r'[^a-zA-Z0-9]', '_', name.lower())
    # Remove consecutive underscores
    sanitized = re.sub(r'_+', '_', sanitized)
    # Strip leading/trailing underscores
    sanitized = sanitized.strip('_')
    # Truncate to 30 chars to leave room for prefix
    return sanitized[:30]


def derive_vector_db_name(
    agent_id: Optional[str] = None,  # UUID as string 
    agent_name: Optional[str] = None,
    connection_id: Optional[int] = None, 
    source_name: Optional[str] = None
) -> str:
    """
    Derive a vector DB collection name.
    
    Standard format: agent_{id}_{sanitized_name}
    Example: agent_5_sales_analytics
    
    This provides clean, readable naming tied to the agent entity.
    All data (indexes, DuckDB files) for an agent lives under this namespace.
    
    Args:
        agent_id: The agent ID (primary identifier)
        agent_name: The agent's display name (for readability)
        connection_id: Database connection ID (fallback)
        source_name: Source file/dataset name (fallback)
        
    Returns:
        A valid vector DB name like "agent_5_sales_analytics"
    """
    if agent_id:
        if agent_name:
            sanitized_name = sanitize_name(agent_name)
            if sanitized_name:
                return f"agent_{agent_id}_{sanitized_name}"
        return f"agent_{agent_id}"
    
    if connection_id:
        return f"connection_{connection_id}"
    
    if source_name:
        sanitized = sanitize_name(source_name)
        if sanitized:
            return f"source_{sanitized}"
    
    return "default_collection"


def get_agent_data_path(agent_id: str, agent_name: Optional[str] = None) -> str:
    """
    Get the standard data path prefix for an agent.
    
    Used for both indexes and DuckDB files:
    - data/indexes/agent_{id}_{name}/
    - data/duckdb_files/agent_{id}_{name}/
    
    Args:
        agent_id: The agent's database ID (UUID as string)
        agent_name: The agent's display name (optional, for readability)
        
    Returns:
        Path prefix like "agent_5_sales_analytics"
    """
    if agent_name:
        sanitized_name = sanitize_name(agent_name)
        if sanitized_name:
            return f"agent_{agent_id}_{sanitized_name}"
    return f"agent_{agent_id}"
