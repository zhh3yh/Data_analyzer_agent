"""Logger setup utility.

Initializes loguru-based logging from logging_config.yaml.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from loguru import logger


def setup_logging(logging_config: dict[str, Any]) -> None:
    """Initialize loguru logging based on the provided configuration dictionary.

    Args:
        logging_config: Dictionary loaded from logging_config.yaml.
    """
    # Remove default loguru handler
    logger.remove()

    config = logging_config.get("logging", logging_config)

    # Console handler
    console_cfg = config.get("console", {})
    if console_cfg.get("enabled", True):
        logger.add(
            sys.stderr,
            level=console_cfg.get("level", "DEBUG"),
            format=console_cfg.get(
                "format",
                "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
            ),
        )

    # File handler
    file_cfg = config.get("file", {})
    if file_cfg.get("enabled", False):
        log_path = Path(file_cfg.get("path", "logs/agent.log"))
        log_path.parent.mkdir(parents=True, exist_ok=True)
        logger.add(
            str(log_path),
            level=file_cfg.get("level", "INFO"),
            format=file_cfg.get(
                "format",
                "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            ),
            rotation=file_cfg.get("rotation", "10 MB"),
            retention=file_cfg.get("retention", "30 days"),
            compression=file_cfg.get("compression", "zip"),
        )

    logger.info("Logging initialized successfully.")
