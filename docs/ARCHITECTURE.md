# Architecture

## System Overview

The Data Analyzer Agent is a modular Python application that orchestrates various tools for SIT signal analysis. It is designed with a Harness Engineer mindset for long-term maintenance and deployment.

## Components

### 1. Agent Orchestrator (`src/core/agent_orchestrator.py`)

- Central coordination of the analysis workflow.
- Manages tool execution order and data flow.
- Handles error recovery and retry logic.

### 2. LLM Interface (`src/core/llm_interface.py`)

- Abstraction layer for LLM communication (AskBosch / OpenAI-compatible API).
- Manages prompt construction, token limits, and response parsing.

### 3. Human Interaction (`src/core/human_interaction.py`)

- Handles human-in-the-loop review steps.
- Manages timeouts and fallback behavior.

### 4. Tools (`src/tools/`)

- **PlotStr Wrapper**: Interface to the PlotStr visualization tool (compiled MATLAB).
- **Robocopy Wrapper**: Manages data downloads from network shares.
- **ByteSoup Converter Wrapper**: Converts raw data to MAT format.
- **AOS Checker Wrapper**: Runs automated quality checks.
- **Report Generator**: Produces PPTX and PDF reports.

### 5. Utilities (`src/utils/`)

- **Config Loader**: Loads YAML configurations with environment variable resolution.
- **Logger Setup**: Initializes structured logging via Loguru.
- **File Operations**: Common file system utilities.

## Data Flow

```
Raw ByteSoup Data (Network Share)
        |
        v  [Robocopy Wrapper]
Local Raw Data (src/data/raw_bytesoup/)
        |
        v  [ByteSoup Converter]
MAT Files (src/data/converted_mat/)
        |
        v  [AOS Checker]
Quality Report
        |
        v  [PlotStr Wrapper]
Visualization Outputs (src/data/plotstr_outputs/)
        |
        v  [Report Generator]
Final Reports (src/data/reports/)
```

## Configuration

All configuration is managed via YAML files in the `config/` directory:

- `agent_config.yaml` - Core agent settings
- `logging_config.yaml` - Logging configuration
- `tools_config.yaml` - Tool-specific settings

Environment variables are stored in `.env` and resolved at runtime.
