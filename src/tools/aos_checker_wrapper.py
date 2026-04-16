"""AOS Checker Wrapper tool.

Wraps the AOS (Automated Quality/Safety) checking tool for validating
signal quality and compliance.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic import BaseModel, Field


class AOSCheckerConfig(BaseModel):
    """Configuration for the AOS Checker."""

    executable_path: str = Field(..., description="Path to the AOS checker executable.")
    rules_path: str = Field(
        default="", description="Path to the checking rules/config file."
    )


class AOSCheckerWrapper:
    """Wrapper around the AOS quality/compliance checker."""

    def __init__(self, config: AOSCheckerConfig) -> None:
        self._config = config
        self._exe = Path(config.executable_path)
        logger.info(f"AOSCheckerWrapper initialized (exe={self._exe}).")

    def check(self, mat_file_path: str) -> dict[str, Any]:
        """Run quality checks on a converted MAT file.

        Args:
            mat_file_path: Path to the .mat file to check.

        Returns:
            Dictionary with check results: 'passed' (bool), 'issues' (list),
            and 'summary' (str).

        Raises:
            FileNotFoundError: If the MAT file does not exist.
            RuntimeError: If the checker crashes.
        """
        mat_path = Path(mat_file_path)
        if not mat_path.is_file():
            raise FileNotFoundError(f"MAT file not found: {mat_path}")

        cmd: list[str] = [str(self._exe), "--input", str(mat_path)]
        if self._config.rules_path:
            cmd.extend(["--rules", self._config.rules_path])

        logger.info(f"Running AOS checker: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)

        if result.returncode not in (0, 1):
            # 0 = all pass, 1 = some issues, other = crash
            logger.error(
                f"AOS checker crashed (rc={result.returncode}): {result.stderr}"
            )
            raise RuntimeError(f"AOS checker failed: {result.stderr}")

        passed = result.returncode == 0
        issues = [line for line in result.stdout.splitlines() if line.strip()]
        summary = "All checks passed." if passed else f"{len(issues)} issue(s) found."

        logger.info(f"AOS check result: {summary}")
        return {"passed": passed, "issues": issues, "summary": summary}
