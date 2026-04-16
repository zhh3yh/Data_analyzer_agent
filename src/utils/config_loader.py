"""Configuration loader utility.

Loads YAML configuration files and resolves environment variables.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


class ConfigLoader:
    """Loads YAML configurations from the config/ directory and resolves environment variables."""

    def __init__(self, config_dir: str = "config") -> None:
        load_dotenv()
        self._config_dir = Path(config_dir)
        self._configs: dict[str, dict] = {}

    def load(self, config_name: str) -> dict[str, Any]:
        """Load a specific YAML config file and return its content as a dictionary.

        Args:
            config_name: Name of the config file (with or without .yaml extension).

        Returns:
            Dictionary with the configuration content.
        """
        if not config_name.endswith((".yaml", ".yml")):
            config_name += ".yaml"

        if config_name in self._configs:
            return self._configs[config_name]

        config_path = self._config_dir / config_name
        if not config_path.is_file():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        resolved = self._resolve_env_vars(raw)
        self._configs[config_name] = resolved
        return resolved

    def _resolve_env_vars(self, obj: Any) -> Any:
        """Recursively resolve ${ENV_VAR} placeholders in config values."""
        if isinstance(obj, str):
            return self._substitute(obj)
        if isinstance(obj, dict):
            return {k: self._resolve_env_vars(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._resolve_env_vars(item) for item in obj]
        return obj

    @staticmethod
    def _substitute(value: str) -> str:
        """Replace ${VAR_NAME} patterns with environment variable values."""
        import re

        pattern = re.compile(r"\$\{(\w+)\}")

        def replacer(match: re.Match) -> str:
            var_name = match.group(1)
            return os.environ.get(var_name, match.group(0))

        return pattern.sub(replacer, value)
