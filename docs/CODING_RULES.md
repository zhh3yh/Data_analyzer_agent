# Coding Rules

## General Standards

- **PEP 8**: All Python code must adhere to PEP 8 style guidelines.
- **Type Hints**: All function signatures must include type hints.
- **Docstrings**: All public functions, classes, and modules must have docstrings (Google style).
- **Maximum Line Length**: 120 characters.

## Error Handling

- Use specific exception types; avoid bare `except` clauses.
- All tool wrapper methods must catch and log errors before re-raising.
- External process calls (`subprocess`) must include timeout parameters.
- Never silently swallow exceptions.

## Security

- **No hardcoded credentials**: All secrets must come from environment variables or secure vaults.
- **Input validation**: All external inputs must be validated using Pydantic models.
- **Path sanitization**: File paths from user input must be sanitized to prevent path traversal.
- **Subprocess safety**: Never use `shell=True` with user-provided input in `subprocess` calls.

## Logging

- Use `loguru` for all logging.
- Log at appropriate levels: DEBUG for development details, INFO for workflow steps, WARNING for recoverable issues, ERROR for failures.
- Never log sensitive information (API keys, passwords).

## Testing

- All new code must include unit tests.
- Minimum code coverage target: 80%.
- Use `pytest` as the test framework.
- Mock external dependencies in unit tests.

## Version Control

- Commit messages should follow Conventional Commits format.
- Feature branches should be prefixed with `feature/`.
- Bug fix branches should be prefixed with `fix/`.

## Bosch-Specific

- Use Bosch-approved base images for Docker containers.
- Follow Bosch internal API guidelines for AskBosch integration.
- Ensure compliance with Bosch data handling policies for SIT signal data.
