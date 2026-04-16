"""Robocopy Wrapper tool.

Wraps the Windows robocopy.exe utility for bulk file/directory copying.
"""

import subprocess
from pathlib import Path

from loguru import logger
from pydantic import BaseModel, Field


class RobocopyConfig(BaseModel):
    """Configuration model for Robocopy."""

    path: str = Field(
        default="robocopy.exe", description="Path to robocopy executable."
    )
    default_flags: str = Field(
        default="/COPYALL /DCOPY:T /E /R:1 /W:1",
        description="Default robocopy flags.",
    )


class RobocopyWrapper:
    """Wrapper around Windows robocopy for batch file transfers."""

    def __init__(self, config: RobocopyConfig) -> None:
        self._config = config
        logger.info("RobocopyWrapper initialized.")

    def copy_directory(
        self,
        source: str,
        destination: str,
        extra_flags: str | None = None,
    ) -> str:
        """Copy a directory tree from source to destination using robocopy.

        Args:
            source: Source directory path.
            destination: Destination directory path.
            extra_flags: Additional robocopy flags to append.

        Returns:
            Summary message with the robocopy exit code.

        Raises:
            RuntimeError: If robocopy returns an error-level exit code (>= 8).
        """
        src = Path(source)
        dst = Path(destination)
        if not src.is_dir():
            raise FileNotFoundError(f"Source directory not found: {src}")

        flags = self._config.default_flags
        if extra_flags:
            flags += f" {extra_flags}"

        cmd = f'"{self._config.path}" "{src}" "{dst}" {flags}'
        logger.info(f"Running robocopy: {cmd}")

        result = subprocess.run(
            cmd, capture_output=True, text=True, shell=True, timeout=600
        )

        # Robocopy exit codes: 0-7 = success/info, >=8 = error
        if result.returncode >= 8:
            logger.error(f"Robocopy failed (rc={result.returncode}): {result.stderr}")
            raise RuntimeError(
                f"Robocopy error (rc={result.returncode}): {result.stderr}"
            )

        msg = f"Robocopy completed (rc={result.returncode}). {src} -> {dst}"
        logger.info(msg)
        return msg
