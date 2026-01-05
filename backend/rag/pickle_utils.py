"""Utilities for handling pickle files with module remapping."""
import pickle
import sys
import importlib
import logging


logger = logging.getLogger(__name__)


class ModuleRemappingUnpickler(pickle.Unpickler):
    """Custom unpickler that remaps 'src.*' modules to 'backend.*'."""
    
    def find_class(self, module, name):
        """Override find_class to remap module names."""
        if module.startswith('src.'):
            remapped_module = module.replace('src.', 'backend.')
            logger.info(f"Remapping pickle module: {module} -> {remapped_module}")
            
            try:
                # Import the remapped module
                mod = importlib.import_module(remapped_module)
                # Cache it under the old name too
                sys.modules[module] = mod
                return getattr(mod, name)
            except (ImportError, AttributeError) as e:
                logger.error(f"Failed to remap {module}.{name}: {e}")
                raise
        
        # Use default behavior for non-src modules
        return super().find_class(module, name)


def load_with_remapping(file_path: str):
    """Load a pickle file with module remapping from 'src' to 'backend'."""
    with open(file_path, 'rb') as f:
        unpickler = ModuleRemappingUnpickler(f)
        return unpickler.load()
