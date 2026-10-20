"""
Logging configuration for the Proxmox MCP server.

This module handles logging setup and configuration:
- File and console logging handlers
- Log level management
- Format customization
- Handler lifecycle management

The logging system supports:
- Configurable log levels
- File-based logging with path resolution
- Console logging for errors
- Custom format strings
- Multiple handler management
"""
import logging
import os
from typing import Optional
from ..config.models import LoggingConfig
from ..utils.redaction import RedactingFilter


def _resolve_level(name: str) -> int:
    """Map a level name to its numeric value, raising ValueError for unknown names."""
    level = logging.getLevelName(str(name).strip().upper())
    if not isinstance(level, int):
        raise ValueError(f"Invalid log level: {name!r}")
    return level


def setup_logging(config: LoggingConfig) -> logging.Logger:
    """Configure and initialize logging system.

    Sets up a comprehensive logging system with:
    - File logging (if configured):
      * Handles relative/absolute paths
      * Uses configured log level
      * Applies custom format
    
    - Console logging:
      * Always enabled for errors
      * Ensures critical issues are visible
    
    - Handler Management:
      * Removes existing handlers
      * Configures new handlers
      * Sets up formatters
    
    Args:
        config: Logging configuration containing:
               - Log level (e.g., "INFO", "DEBUG")
               - Format string
               - Optional log file path

    Returns:
        Configured logger instance for "proxmox-mcp"
        with appropriate handlers and formatting

    Example config:
        {
            "level": "INFO",
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            "file": "/path/to/log/file.log"  # Optional
        }
    """
    level = _resolve_level(config.level)

    # Convert relative path to absolute
    log_file = config.file
    if log_file and not os.path.isabs(log_file):
        log_file = os.path.join(os.getcwd(), log_file)

    # Create handlers
    handlers = []

    if log_file:
        # Create with 0600 (umask-independent) and tighten any pre-existing file.
        fd = os.open(log_file, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        os.close(fd)
        os.chmod(log_file, 0o600)
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        handlers.append(file_handler)

    # Console handler for errors only
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.ERROR)
    handlers.append(console_handler)

    # Configure formatters and secret redaction on every handler
    formatter = logging.Formatter(config.format)
    for handler in handlers:
        handler.setFormatter(formatter)
        handler.addFilter(RedactingFilter())

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove any existing handlers (closing file handlers we opened earlier)
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        if isinstance(handler, logging.FileHandler):
            handler.close()

    # Add new handlers
    for handler in handlers:
        root_logger.addHandler(handler)

    # Create and return server logger
    logger = logging.getLogger("proxmox-mcp")
    return logger
