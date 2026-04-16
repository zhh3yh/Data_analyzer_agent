"""Integration test – full workflow smoke test."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from src.core import AgentOrchestrator, HumanInteractionHandler, LLMInterface


@patch.object(LLMInterface, "__init__", lambda self, *a, **kw: None)
def test_orchestrator_registers_tools() -> None:
    llm = LLMInterface.__new__(LLMInterface)
    llm._client = MagicMock()
    llm._model = "test-model"
    llm._temperature = 0.5
    llm._max_tokens = 100

    human = HumanInteractionHandler(timeout_seconds=10)
    orch = AgentOrchestrator(llm, human, tools_config={}, agent_config={})

    mock_tool = MagicMock()
    orch.register_tool("test_tool", mock_tool)

    assert "test_tool" in orch._tools
