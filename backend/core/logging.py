"""
Structured logging configuration for the backend service.
"""
import logging
import sys
import json
from datetime import datetime
from typing import Any, Dict
from pathlib import Path


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        # Add extra fields
        if hasattr(record, "trace_id"):
            log_data["trace_id"] = record.trace_id
        
        if hasattr(record, "user_id"):
            log_data["user_id"] = record.user_id
        
        return json.dumps(log_data)


def setup_logging() -> logging.Logger:
    """
    Configure application logging with JSON formatting.
    
    Returns:
        Configured root logger
    """
    # Import here to avoid circular dependency
    from backend.config import get_settings
    settings = get_settings()
    
    # Resolve logs directory relative to project root (parent of backend/)
    backend_root = Path(__file__).parent.parent
    project_root = backend_root.parent if backend_root.name == "backend" else backend_root
    
    log_file_path = Path(settings.log_file)
    if not log_file_path.is_absolute():
        log_file_path = (backend_root.parent / settings.log_file).resolve()
    
    log_file_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Get root logger
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, settings.log_level))
    
    # Remove existing handlers
    logger.handlers.clear()
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, settings.log_level))
    
    if settings.log_format == "json":
        console_formatter = JSONFormatter()
    else:
        console_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
    
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # File handler
    file_handler = logging.FileHandler(str(log_file_path))
    file_handler.setLevel(getattr(logging, settings.log_level))
    file_handler.setFormatter(JSONFormatter())
    logger.addHandler(file_handler)
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a specific module.
    
    Args:
        name: Logger name (typically __name__)
    
    Returns:
        Logger instance
    """
    return logging.getLogger(name)


def get_embedding_logger() -> logging.Logger:
    """
    Get a specialized logger for embedding operations that writes to a dedicated log file.
    
    Returns:
        Configured embedding logger
    """
    # Import here to avoid circular dependency
    from backend.config import get_settings
    settings = get_settings()
    
    logger = logging.getLogger("embedding_processor")
    
    # If already has handlers (configured previously), just return it
    if logger.handlers:
        return logger
        
    logger.setLevel(getattr(logging, settings.log_level))
    
    # Console handler (inherited from root, but we can be explicit or just let it propagate)
    # Actually, we want it to go to the main log too, so we let it propagate to root by default.
    # But we also want a dedicated file.
    
    # Dedicated Embedding File handler
    backend_root = Path(__file__).parent.parent
    log_file_path = Path(settings.embedding_log_file)
    if not log_file_path.is_absolute():
        log_file_path = (backend_root.parent / settings.embedding_log_file).resolve()
        
    log_file_path.parent.mkdir(parents=True, exist_ok=True)
    
    file_handler = logging.FileHandler(str(log_file_path))
    file_handler.setLevel(getattr(logging, settings.log_level))
    file_handler.setFormatter(JSONFormatter())
    logger.addHandler(file_handler)
    
    # Ensure it also goes to console by allowing propagation (default is True)
    logger.propagate = True
    
    return logger
