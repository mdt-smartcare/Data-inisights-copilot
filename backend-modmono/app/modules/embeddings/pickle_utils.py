"""
Utilities for handling pickle files with module remapping.

Handles loading old pickle docstores that were saved with different module paths
(e.g., 'src.*' modules that need to be remapped to 'backend.*' or 'app.*').
"""
import pickle
import sys
import importlib

from app.core.utils.logging import get_logger

logger = get_logger(__name__)


class ModuleRemappingUnpickler(pickle.Unpickler):
    """
    Custom unpickler that remaps module names for backward compatibility.
    
    Handles:
    - 'src.*' -> 'backend.*' (old backend format)
    - 'backend.*' -> 'app.*' (migration to backend-modmono)
    """
    
    # Module remapping rules: old_prefix -> new_prefix
    REMAP_RULES = [
        ('src.', 'backend.'),
        ('backend.pipeline.transform', 'app.modules.embeddings.transform'),
        ('backend.rag.retrieve', 'app.modules.embeddings.retrieve'),
        ('backend.services.embeddings', 'app.modules.embeddings.service'),
    ]
    
    def find_class(self, module, name):
        """Override find_class to remap module names."""
        original_module = module
        
        # Apply remapping rules
        for old_prefix, new_prefix in self.REMAP_RULES:
            if module.startswith(old_prefix):
                module = module.replace(old_prefix, new_prefix, 1)
                logger.debug(f"Remapping pickle module: {original_module} -> {module}")
                break
        
        # Special case: SimpleInMemoryStore might be in different locations
        if name == 'SimpleInMemoryStore':
            try:
                from app.modules.embeddings.transform import SimpleInMemoryStore
                return SimpleInMemoryStore
            except ImportError:
                pass
        
        try:
            # Import the (possibly remapped) module
            mod = importlib.import_module(module)
            # Cache it under the old name too for subsequent lookups
            if original_module != module:
                sys.modules[original_module] = mod
            return getattr(mod, name)
        except (ImportError, AttributeError) as e:
            logger.warning(f"Failed to remap {original_module}.{name}: {e}")
            # Fall back to default behavior
            return super().find_class(original_module, name)


def load_with_remapping(file_path: str):
    """
    Load a pickle file with module remapping for backward compatibility.
    
    Args:
        file_path: Path to the pickle file
        
    Returns:
        Unpickled object with modules remapped
    """
    logger.info(f"Loading pickle file with module remapping: {file_path}")
    
    with open(file_path, 'rb') as f:
        unpickler = ModuleRemappingUnpickler(f)
        obj = unpickler.load()
    
    logger.info(f"Successfully loaded pickle file: {type(obj).__name__}")
    return obj


def save_with_compatibility(obj, file_path: str):
    """
    Save an object to pickle with standard protocol for compatibility.
    
    Args:
        obj: Object to pickle
        file_path: Path to save the pickle file
    """
    with open(file_path, 'wb') as f:
        pickle.dump(obj, f, protocol=pickle.HIGHEST_PROTOCOL)
    
    logger.info(f"Saved pickle file: {file_path}")
