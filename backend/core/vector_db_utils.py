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

def derive_vector_db_name(
    agent_id: Optional[int] = None, 
    connection_id: Optional[int] = None, 
    source_name: Optional[str] = None
) -> str:
    """
    Unifies the logic for deriving a default Vector DB name.
    Precedence: source_name > agent_id > connection_id > default
    """
    if source_name:
        # Standardize source_name: alphanumeric + underscores, lowercase
        formatted = re.sub(r'[^a-zA-Z0-9_]', '_', source_name).lower()
        # Clean up double underscores
        formatted = re.sub(r'_+', '_', formatted).strip('_')
        if formatted:
            return f"{formatted}_data"
            
    if agent_id:
        return f"agent_{agent_id}_data"
        
    if connection_id:
        return f"db_connection_{connection_id}_data"
        
    return "default_vector_db"
