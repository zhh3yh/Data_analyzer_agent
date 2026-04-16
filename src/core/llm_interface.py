"""LLM Interface module.

Handles communication with the LLM backend (e.g., AskBosch / OpenAI-compatible API).
"""

from typing import Any

from loguru import logger
from openai import OpenAI


class LLMInterface:
    """Wrapper around the LLM API for the Data Analyzer Agent."""

    def __init__(self, llm_config: dict[str, Any]) -> None:
        self._model = llm_config.get("model_name", "gpt-4-turbo")
        self._temperature = llm_config.get("temperature", 0.7)
        self._max_tokens = llm_config.get("max_tokens", 2000)
        self._client = OpenAI()  # Uses OPENAI_API_KEY or BOSCH_ASKBOSCH_API_KEY from env
        logger.info(f"LLMInterface initialized with model={self._model}")

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        """Send a chat completion request and return the assistant's reply.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            **kwargs: Additional parameters forwarded to the API call.

        Returns:
            The assistant's response text.
        """
        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=kwargs.get("temperature", self._temperature),
            max_tokens=kwargs.get("max_tokens", self._max_tokens),
        )
        reply = response.choices[0].message.content or ""
        logger.debug(f"LLM response (first 200 chars): {reply[:200]}")
        return reply

    def generate_tool_call(self, prompt: str, tools: list[dict], **kwargs: Any) -> dict:
        """Request the LLM to select and parameterize a tool call.

        Args:
            prompt: The user/system prompt describing the task.
            tools: List of tool schemas (OpenAI function-calling format).
            **kwargs: Additional parameters.

        Returns:
            Dictionary with 'tool_name' and 'arguments'.
        """
        messages = [{"role": "user", "content": prompt}]
        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            tools=tools,
            temperature=kwargs.get("temperature", self._temperature),
        )
        tool_call = response.choices[0].message.tool_calls
        if tool_call:
            fc = tool_call[0].function
            import json
            return {"tool_name": fc.name, "arguments": json.loads(fc.arguments)}
        return {"tool_name": None, "arguments": {}}
