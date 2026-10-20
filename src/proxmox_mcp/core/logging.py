"""
Logging configuration for the Proxmox MCP server.

This module handles logging setup and configuration:
- Console (stderr) logging by default, optional size-bounded rotating file logging (0600)
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
from io import TextIOWrapper
from logging.handlers import RotatingFileHandler

from ..config.models import LoggingConfig
from ..utils.redaction import RedactingFilter

LOG_FILE_MAX_BYTES = 10 * 1024 * 1024
LOG_FILE_BACKUP_COUNT = 5  # total on disk is bounded to (1 + 5) * 10 MiB


class _PrivateRotatingFileHandler(RotatingFileHandler):
    """Rotating file handler whose active and rotated files are always mode 0600."""

    def _open(self) -> TextIOWrapper:
        fd = os.open(self.baseFilename, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        os.close(fd)
        os.chmod(self.baseFilename, 0o600)
        return super()._open()


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

    - Console logging (stderr):
      * Without a log file: everything at the configured level
      * With a log file: errors only
    - File logging is rotated (10 MiB x 5 backups) and files are 0600

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
    handlers: list[logging.Handler] = []

    if log_file:
        file_handler = _PrivateRotatingFileHandler(
            log_file,
            maxBytes=LOG_FILE_MAX_BYTES,
            backupCount=LOG_FILE_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        handlers.append(file_handler)

    # Console (stderr; stdout is the stdio MCP channel). Without a log file it carries
    # everything at the configured level (the Docker logging driver collects it);
    # with a log file only errors are mirrored.
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.ERROR if log_file else level)
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
