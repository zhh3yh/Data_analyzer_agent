# Usage Guide

## Command Line Interface

### Basic Analysis

```bash
python src/main.py analyze --file <path_to_mat_file>
```

### Options

| Option         | Description                     | Default                    |
| -------------- | ------------------------------- | -------------------------- |
| `--file`       | Path to the MAT file to analyze | Required                   |
| `--config`     | Path to custom agent config     | `config/agent_config.yaml` |
| `--output-dir` | Output directory for reports    | `src/data/reports/`        |
| `--no-review`  | Skip human review steps         | `False`                    |

## Workflow Steps

1. **Data Loading**: The agent loads the specified MAT file.
2. **Quality Check**: Automated AOS quality checks are executed.
3. **Signal Analysis**: The LLM analyzes signal characteristics.
4. **Visualization**: Rerun logs signal data for inspection.
5. **Human Review** (optional): The Rerun viewer is launched for manual review.
6. **Report Generation**: A report is generated with findings and visualizations.

## Examples

### Analyze a single file

```bash
python src/main.py analyze --file src/data/converted_mat/test_drive_001.mat
```

### Analyze with custom config

```bash
python src/main.py analyze --file data.mat --config my_config.yaml
```

## Troubleshooting

- Ensure all paths in `.env` are correctly configured.
- Check `logs/agent.log` for detailed error information.
- Ensure `rerun-sdk` is installed (see `requirements.txt`) and the Rerun viewer is reachable for interactive review.
