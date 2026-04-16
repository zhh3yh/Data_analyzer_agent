# Data Analyzer Agent

## Overview

An LLM-powered Agent for automated SIT signal analysis within Bosch. The Agent handles data download, conversion, quality checks, visualization (using PlotStr), and report generation, with a human-in-the-loop for review.

## Features

- **Automated Data Download**: Uses Robocopy to retrieve raw ByteSoup data from network shares.
- **Data Conversion**: Converts raw ByteSoup data to MAT format for analysis.
- **Quality Checks**: Automated AOS quality checks on signal data.
- **Visualization**: Leverages the PlotStr tool for signal plotting and interactive review.
- **Report Generation**: Generates preliminary (PPTX) and final (PDF) reports.
- **Human-in-the-Loop**: Supports human review at critical decision points.

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment variables
cp .env.example .env
# Edit .env with your paths and API keys

# 3. Run the agent
python src/main.py analyze --file <path_to_mat_file>
```

## Project Structure

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed architecture documentation.

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) - System architecture and design
- [USAGE.md](USAGE.md) - Detailed usage instructions
- [CODING_RULES.md](CODING_RULES.md) - Coding standards and conventions
- [ENVIRONMENT_SETUP.md](ENVIRONMENT_SETUP.md) - Environment setup guide
