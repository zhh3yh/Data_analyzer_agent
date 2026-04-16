"""File operations utility.

Provides helper functions for common file system operations.
"""

import shutil
from pathlib import Path

from loguru import logger


def ensure_directory(path: str | Path) -> Path:
    """Create directory (and parents) if it does not exist. Returns the Path object."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    logger.debug(f"Ensured directory exists: {p}")
    return p


def copy_file(src: str | Path, dst: str | Path) -> Path:
    """Copy a single file from src to dst. Returns destination Path."""
    src, dst = Path(src), Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    logger.info(f"Copied {src} -> {dst}")
    return dst


def list_files(directory: str | Path, pattern: str = "*") -> list[Path]:
    """List files in a directory matching a glob pattern."""
    return sorted(Path(directory).glob(pattern))


def safe_delete(path: str | Path) -> None:
    """Delete a file or directory safely with logging."""
    p = Path(path)
    if p.is_file():
        p.unlink()
        logger.info(f"Deleted file: {p}")
    elif p.is_dir():
        shutil.rmtree(p)
        logger.info(f"Deleted directory: {p}")
    else:
        logger.warning(f"Path does not exist, nothing to delete: {p}")
