"""Application logging that records diagnostic tracebacks outside the UI."""

from __future__ import annotations

import logging
from pathlib import Path


def log_directory() -> Path:
    """Return a stable user-local log directory, creating it when necessary."""
    root = Path.home() / ".solar-time-distance-explorer" / "logs"
    root.mkdir(parents=True, exist_ok=True)
    return root


def configure_logging() -> Path:
    """Configure a file and console logger once, returning the log file path."""
    destination = log_directory() / "app.log"
    root = logging.getLogger()
    if root.handlers:
        return destination
    root.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%Y-%m-%dT%H:%M:%S"
    )
    file_handler = logging.FileHandler(destination, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(formatter)
    root.addHandler(file_handler)
    root.addHandler(console)
    return destination
