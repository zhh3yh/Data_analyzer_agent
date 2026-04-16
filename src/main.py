"""Data Analyzer Agent – entry point.

Provides a CLI interface to start the agent workflow.
"""

import sys
from pathlib import Path

import click
from loguru import logger

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core import AgentOrchestrator, HumanInteractionHandler, LLMInterface
from src.tools import PlotStrWrapper
from src.tools.plotstr_wrapper import PlotStrConfig
from src.utils.config_loader import ConfigLoader
from src.utils.logger_setup import setup_logging


def _build_agent(config_dir: str = "config") -> AgentOrchestrator:
    """Wire up all components and return a ready-to-run orchestrator."""
    loader = ConfigLoader(config_dir)

    # Logging
    log_cfg = loader.load("logging_config")
    setup_logging(log_cfg)

    # Configs
    agent_cfg = loader.load("agent_config")
    tools_cfg = loader.load("tools_config")

    # Core components
    llm = LLMInterface(agent_cfg.get("llm_settings", {}))
    human = HumanInteractionHandler(
        timeout_seconds=agent_cfg.get("human_review_timeout_seconds", 3600),
    )
    orchestrator = AgentOrchestrator(llm, human, tools_cfg, agent_cfg)

    # Register tools
    plotstr_section = tools_cfg.get("plotstr", {})
    if plotstr_section.get("plotstr_root"):
        plotstr_cfg = PlotStrConfig(
            plotstr_root=plotstr_section["plotstr_root"],
            matlab_executable=plotstr_section.get("matlab_executable", "matlab"),
            mdf_exporter_path=plotstr_section.get("mdf_exporter_path", ""),
            mdf_exporter_conda_env=plotstr_section.get(
                "mdf_exporter_conda_env", "mdf-exporter"
            ),
            regex_path=plotstr_section.get("regex_path", ""),
            replacement_list_path=plotstr_section.get("replacement_list_path", ""),
            output_dir=plotstr_section.get("output_dir", "src/data/plotstr_outputs"),
            config_dir=plotstr_section.get("config_dir", ""),
            max_parallel_jobs=plotstr_section.get("max_parallel_jobs", 4),
        )
        orchestrator.register_tool("plotstr", PlotStrWrapper(plotstr_cfg))

    return orchestrator


@click.group()
def cli() -> None:
    """Data Analyzer Agent – automated SIT signal analysis."""


@cli.command()
@click.option(
    "--file",
    "file_path",
    required=True,
    type=click.Path(exists=True),
    help="Path to input data file.",
)
@click.option("--config-dir", default="config", help="Path to configuration directory.")
def analyze(file_path: str, config_dir: str) -> None:
    """Run the full analysis workflow on a data file."""
    agent = _build_agent(config_dir)
    task = f"Analyze the measurement data in '{file_path}': convert, quality-check, visualize with PlotStr, and generate a report."
    result = agent.run(task)
    logger.info(f"Workflow finished: {result.get('status')}")
    click.echo(f"Done – status: {result.get('status')}")


@cli.command()
def version() -> None:
    """Print version information."""
    click.echo("Data Analyzer Agent v0.1.0")


if __name__ == "__main__":
    cli()
