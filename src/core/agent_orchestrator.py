"""Agent Orchestrator module.

Coordinates the overall workflow: task planning, tool invocation, and human review loops.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from .human_interaction import HumanInteractionHandler
from .llm_interface import LLMInterface


class AgentOrchestrator:
    """Central orchestrator that drives the Data Analyzer Agent workflow."""

    def __init__(
        self,
        llm: LLMInterface,
        human_handler: HumanInteractionHandler,
        tools_config: dict[str, Any],
        agent_config: dict[str, Any],
    ) -> None:
        self._llm = llm
        self._human = human_handler
        self._tools_config = tools_config
        self._agent_config = agent_config
        self._persona = agent_config.get(
            "agent_persona",
            "You are a professional SIT signal analysis expert.",
        )
        self._tools: dict[str, Any] = {}
        logger.info("AgentOrchestrator initialized.")

    def register_tool(self, name: str, tool: Any) -> None:
        """Register an external tool (wrapper instance) by name."""
        self._tools[name] = tool
        logger.info(f"Tool registered: {name}")

    def run(self, task_description: str) -> dict[str, Any]:
        """Execute an end-to-end analysis task.

        Args:
            task_description: Natural-language description of the analysis task.

        Returns:
            Dictionary with workflow results and status.
        """
        logger.info(f"Starting task: {task_description[:120]}...")

        # Step 1 – Ask LLM to create a plan
        plan = self._plan(task_description)
        logger.info(f"Plan created with {len(plan)} steps.")

        results: list[dict[str, Any]] = []
        for i, step in enumerate(plan, 1):
            logger.info(
                f"Executing step {i}/{len(plan)}: {step.get('action', 'unknown')}"
            )

            # Step 2 – Execute tool if applicable
            tool_name = step.get("tool")
            if tool_name and tool_name in self._tools:
                tool_result = self._execute_tool(tool_name, step.get("params", {}))
                results.append({"step": i, "tool": tool_name, "result": tool_result})
            else:
                results.append(
                    {"step": i, "action": step.get("action"), "result": "no-tool"}
                )

            # Step 3 – Human review checkpoint (if flagged)
            if step.get("needs_review", False):
                feedback = self._human.request_review(
                    context=f"Step {i}: {step.get('action', '')}",
                    artifacts=results[-1],
                )
                if not feedback.get("approved", False):
                    logger.warning(f"Step {i} not approved by human. Halting.")
                    return {
                        "status": "halted",
                        "reason": "human_rejected",
                        "results": results,
                    }

        logger.info("Task completed successfully.")
        return {"status": "completed", "results": results}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _plan(self, task: str) -> list[dict[str, Any]]:
        """Ask the LLM to break *task* into sequential steps."""
        messages = [
            {"role": "system", "content": self._persona},
            {
                "role": "user",
                "content": (
                    f"Break the following task into concrete steps. "
                    f"For each step output JSON with keys: action, tool (optional), params (optional), needs_review (bool).\n\n"
                    f"Task: {task}"
                ),
            },
        ]
        raw = self._llm.chat(messages)
        # Expecting a JSON list; fall back to a single-step plan on parse error.
        import json

        try:
            plan = json.loads(raw)
            if isinstance(plan, dict):
                plan = [plan]
        except json.JSONDecodeError:
            logger.warning("LLM returned non-JSON plan; wrapping as single step.")
            plan = [{"action": raw, "needs_review": True}]
        return plan

    def _execute_tool(self, tool_name: str, params: dict) -> Any:
        """Invoke a registered tool with the given parameters."""
        tool = self._tools[tool_name]
        method_name = params.pop("method", "run")
        method = getattr(tool, method_name, None)
        if method is None:
            raise AttributeError(f"Tool '{tool_name}' has no method '{method_name}'.")
        return method(**params)
