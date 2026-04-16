"""ByteSoup Converter Wrapper tool.

Wraps the ByteSoup data converter for transforming raw measurement files
into MAT format suitable for analysis and PlotStr visualization.
"""

import subprocess
from pathlib import Path

from loguru import logger
from pydantic import BaseModel, Field


class ByteSoupConverterConfig(BaseModel):
    """Configuration for the ByteSoup converter."""

    executable_path: str = Field(
        ..., description="Path to the ByteSoup converter executable."
    )
    output_dir: str = Field(
        default="src/data/converted_mat",
        description="Output directory for converted MAT files.",
    )


class ByteSoupConverterWrapper:
    """Wrapper around the ByteSoup converter tool."""

    def __init__(self, config: ByteSoupConverterConfig) -> None:
        self._config = config
        self._exe = Path(config.executable_path)
        self._output_dir = Path(config.output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"ByteSoupConverterWrapper initialized (exe={self._exe}).")

    def convert(
        self,
        input_path: str,
        output_name: str | None = None,
    ) -> str:
        """Convert a raw ByteSoup file to MAT format.

        Args:
            input_path: Path to the raw measurement file.
            output_name: Optional output file name (without extension).
                         Defaults to the input file stem.

        Returns:
            Full path to the generated .mat file.

        Raises:
            FileNotFoundError: If the input file does not exist.
            RuntimeError: If the converter exits with a non-zero code.
        """
        src = Path(input_path)
        if not src.is_file():
            raise FileNotFoundError(f"Input file not found: {src}")

        stem = output_name or src.stem
        output_path = self._output_dir / f"{stem}.mat"

        cmd: list[str] = [
            str(self._exe),
            "--input",
            str(src),
            "--output",
            str(output_path),
        ]

        logger.info(f"Running ByteSoup converter: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if result.returncode != 0:
            logger.error(
                f"ByteSoup converter failed (rc={result.returncode}): {result.stderr}"
            )
            raise RuntimeError(f"ByteSoup converter failed: {result.stderr}")

        logger.info(f"Conversion complete: {output_path}")
        return str(output_path)

    def batch_convert(self, input_dir: str, pattern: str = "*.raw") -> list[str]:
        """Convert all matching files in a directory.

        Args:
            input_dir: Directory containing raw files.
            pattern: Glob pattern to match input files.

        Returns:
            List of paths to the generated .mat files.
        """
        files = sorted(Path(input_dir).glob(pattern))
        if not files:
            logger.warning(f"No files matching '{pattern}' found in {input_dir}.")
            return []

        results = []
        for f in files:
            mat_path = self.convert(str(f))
            results.append(mat_path)
        return results
