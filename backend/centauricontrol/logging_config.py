"""
CentauriControl – Comprehensive logging configuration.

Provides structured logging for all components with file rotation,
timestamped entries, and per-component log levels.
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path
from typing import Optional

_LOG_DIR: Optional[Path] = None
_LOGGERS: dict[str, logging.Logger] = {}


def initialize_logging(
    log_dir: Path | str = "data/logs",
    level: int = logging.INFO,
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5,
) -> None:
    """Initialize logging with file rotation.

    Args:
        log_dir: Directory for log files
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
        max_bytes: Max bytes per log file before rotation
        backup_count: Number of rotated backup files to keep
    """
    global _LOG_DIR
    log_dir_path = Path(log_dir)
    log_dir_path.mkdir(parents=True, exist_ok=True)
    _LOG_DIR = log_dir_path

    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Capture everything; handlers filter

    # Remove existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Console handler (INFO level)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # File handler (DEBUG level) with rotation
    file_handler = logging.handlers.RotatingFileHandler(
        log_dir_path / "centauricontrol.log",
        maxBytes=max_bytes,
        backupCount=backup_count,
    )
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)


def get_logger(name: str, level: Optional[int] = None) -> logging.Logger:
    """Get or create a logger for a component.

    Args:
        name: Logger name (typically __name__ from calling module)
        level: Optional override level for this logger

    Returns:
        Configured logger instance
    """
    if name not in _LOGGERS:
        logger = logging.getLogger(name)
        if level is not None:
            logger.setLevel(level)
        _LOGGERS[name] = logger
    return _LOGGERS[name]


# Convenience module-level logger
logger = logging.getLogger(__name__)
