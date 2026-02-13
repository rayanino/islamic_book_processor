"""Logging utilities for run-scoped logs."""

from __future__ import annotations

import logging
from pathlib import Path


def configure_run_logger(log_file: Path) -> logging.Logger:
    """Configure and return a simple file-backed run logger."""

    logger = logging.getLogger(f"ibp.{log_file}")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if logger.handlers:
        return logger

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger
