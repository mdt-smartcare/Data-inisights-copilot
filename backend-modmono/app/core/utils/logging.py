"""
Structured logging configuration using structlog.

Provides consistent JSON logging with context and correlation IDs.
Logs to both console (stdout) and file (logs/backend.log).
"""
import sys
import logging
import os
import re
from pathlib import Path
from logging.handlers import RotatingFileHandler
from typing import Optional
import structlog
from structlog.types import Processor

# Force unbuffered stdout for immediate log output
# This ensures logs appear immediately even if the request crashes
sys.stdout.reconfigure(line_buffering=True)

# Default log file path
DEFAULT_LOG_DIR = Path(__file__).parent.parent.parent.parent / "logs"
DEFAULT_LOG_FILE = "backend.log"


# =============================================================================
# Sensitive Data Filter for Access Logs
# =============================================================================

class SensitiveDataFilter(logging.Filter):
    """
    Filter to sanitize sensitive data from log messages.
    
    Removes or masks sensitive query parameters (e.g., JWT tokens)
    from Uvicorn access logs to prevent credential leakage.
    """
    
    # Pattern to match sensitive query parameters
    SENSITIVE_PARAMS_PATTERN = re.compile(
        r'(\?|&)(token|api_key|apikey|secret|password|auth)=[^&\s\]"]+',
        re.IGNORECASE
    )
    
    def filter(self, record: logging.LogRecord) -> bool:
        """
        Filter and sanitize the log record message.
        
        Returns True to allow the record through (after sanitization).
        """
        if record.msg and isinstance(record.msg, str):
            record.msg = self.SENSITIVE_PARAMS_PATTERN.sub(r'\1\2=[REDACTED]', record.msg)
        
        if record.args:
            sanitized_args = []
            for arg in record.args:
                if isinstance(arg, str):
                    arg = self.SENSITIVE_PARAMS_PATTERN.sub(r'\1\2=[REDACTED]', arg)
                sanitized_args.append(arg)
            record.args = tuple(sanitized_args)
        
        return True


def configure_logging(
    log_level: str = "INFO", 
    json_logs: bool = True,
    log_file: Optional[str] = None,
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5
) -> None:
    """
    Configure structured logging for the application.
    
    Logs to both console and file for persistence.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_logs: Whether to output JSON logs (True for production, False for dev)
        log_file: Path to log file (default: logs/backend.log)
        max_bytes: Max size of log file before rotation (default: 10MB)
        backup_count: Number of backup files to keep (default: 5)
    """
    # Determine log file path
    if log_file:
        log_path = Path(log_file)
    else:
        log_path = DEFAULT_LOG_DIR / DEFAULT_LOG_FILE
    
    # Create log directory if it doesn't exist
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Create sensitive data filter
    sensitive_filter = SensitiveDataFilter()
    
    # Console handler (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level.upper()))
    console_handler.setFormatter(logging.Formatter("%(message)s"))
    console_handler.addFilter(sensitive_filter)
    root_logger.addHandler(console_handler)
    
    # File handler with rotation
    try:
        file_handler = RotatingFileHandler(
            str(log_path),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(getattr(logging, log_level.upper()))
        file_handler.setFormatter(logging.Formatter("%(message)s"))
        file_handler.addFilter(sensitive_filter)
        root_logger.addHandler(file_handler)
        print(f"Logging to file: {log_path}")
    except Exception as e:
        print(f"Warning: Could not create log file {log_path}: {e}")
    
    # Suppress noisy loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    
    # Suppress SQLAlchemy warnings
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)
    
    # Apply sensitive data filter to Uvicorn loggers to redact tokens
    for logger_name in ["uvicorn", "uvicorn.error", "uvicorn.access", "uvicorn.asgi"]:
        uvicorn_logger = logging.getLogger(logger_name)
        uvicorn_logger.addFilter(sensitive_filter)
    
    # Processors for structlog
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]
    
    if json_logs:
        # JSON output for production
        processors = shared_processors + [
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer()
        ]
    else:
        # Pretty console output for development
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True)
        ]
    
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    Get a structured logger instance.
    
    Args:
        name: Logger name (usually __name__)
    
    Returns:
        Structured logger instance
    
    Usage:
        logger = get_logger(__name__)
        logger.info("User logged in", user_id="123", email="user@example.com")
    """
    return structlog.get_logger(name)


def bind_context(**kwargs) -> None:
    """
    Bind context variables that will be included in all subsequent logs.
    
    Usage:
        bind_context(request_id="abc-123", user_id="user-456")
        logger.info("Processing request")  # Will include request_id and user_id
    """
    structlog.contextvars.bind_contextvars(**kwargs)


def clear_context() -> None:
    """Clear all bound context variables."""
    structlog.contextvars.clear_contextvars()


def unbind_context(*keys: str) -> None:
    """
    Remove specific keys from the context.
    
    Args:
        *keys: Keys to remove from context
    """
    structlog.contextvars.unbind_contextvars(*keys)
