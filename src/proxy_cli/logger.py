"""
Logging module for proxy-cli-tool

Copyright (c) 2026 cgnie chenguang.nie@icloud.com

Licensed under the MIT License.
"""


import logging
import os
from pathlib import Path
from logging.handlers import RotatingFileHandler

# Default log file path
DEFAULT_LOG_FILE = "~/.proxy-cli/proxy.log"
# Max log file size before rotation (10MB)
MAX_LOG_SIZE = 10 * 1024 * 1024
# Number of backup files to keep
BACKUP_COUNT = 3
# Log format
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s - %(message)s"
# Date format
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logger(
    name: str = "proxy_cli",
    level: str = "info",
    log_file: str = DEFAULT_LOG_FILE,
    verbose: bool = False,
) -> logging.Logger:
    """
    Set up logger with file and optional console handlers

    Args:
        name: Logger name (usually __name__ or module name)
        level: Logging level (debug, info, warning, error)
        log_file: Path to log file (supports ~ expansion)
        verbose: If True, also output to console at DEBUG level

    Returns:
        Configured logger instance

    Raises:
        ValueError: If invalid log level provided
    """
    # Map level string to logging constant
    level_map = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
    }

    if level.lower() not in level_map:
        raise ValueError(
            f"Invalid log level '{level}'. Must be one of: {', '.join(level_map.keys())}"
        )

    log_level = level_map[level.lower()]

    # Create or get logger
    logger = logging.getLogger(name)

    # Clear existing handlers to avoid duplicates
    logger.handlers.clear()

    # Set log level
    logger.setLevel(log_level)

    # Create formatter
    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    # Ensure log directory exists
    log_path = Path(log_file).expanduser()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Create rotating file handler
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=MAX_LOG_SIZE,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Add console handler if verbose mode is enabled
    if verbose:
        console_handler = logging.StreamHandler()
        # Console always uses DEBUG level in verbose mode
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger


def get_logger(name: str = "proxy_cli") -> logging.Logger:
    """
    Get an existing logger instance

    Args:
        name: Logger name

    Returns:
        Logger instance (or creates one with defaults if not exists)
    """
    logger = logging.getLogger(name)

    # If logger has no handlers, set up with defaults
    if not logger.handlers:
        return setup_logger(name=name)

    return logger


def redact_sensitive(message: str, *sensitive_values: str) -> str:
    """
    Redact sensitive information from log messages

    Args:
        message: Original log message
        *sensitive_values: Values to redact (e.g., passwords, tokens)

    Returns:
        Message with sensitive values replaced by [REDACTED]
    """
    result = message
    for value in sensitive_values:
        if value:
            result = result.replace(value, "[REDACTED]")
    return result


class SensitiveFilter(logging.Filter):
    """
    Logging filter that redacts sensitive information patterns
    """

    SENSITIVE_PATTERNS = [
        ("password", "password=[REDACTED]"),
        ("pwd", "pwd=[REDACTED]"),
        ("token", "token=[REDACTED]"),
        ("api_key", "api_key=[REDACTED]"),
        ("apikey", "apikey=[REDACTED]"),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Filter log record to redact sensitive information

        Args:
            record: Log record to filter

        Returns:
            True (always allow the record)
        """
        # Get the message
        msg = record.getMessage()

        for pattern, replacement in self.SENSITIVE_PATTERNS:
            if pattern.lower() in msg.lower():
                # Redact the value after the pattern
                import re

                # Build regex pattern: key=value (case insensitive)
                regex = re.compile(f"{pattern}\\s*=\\s*[^\\s]+", re.IGNORECASE)
                msg = regex.sub(replacement, msg)
                record.msg = msg
                record.args = ()  # Clear args to prevent re-formatting

        return True
