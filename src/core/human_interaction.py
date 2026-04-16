"""Human Interaction module.

Manages human-in-the-loop review checkpoints: prompting, timeouts, and feedback collection.
"""

import time
from typing import Any

from loguru import logger


class HumanInteractionHandler:
    """Handles human review requests during the agent workflow."""

    def __init__(self, timeout_seconds: int = 3600) -> None:
        self._timeout = timeout_seconds
        logger.info(f"HumanInteractionHandler initialized (timeout={self._timeout}s).")

    def request_review(self, context: str, artifacts: Any = None) -> dict[str, Any]:
        """Prompt the human operator to review an intermediate result.

        Args:
            context: Description of what needs review.
            artifacts: Any data/artifacts the human should inspect.

        Returns:
            Dictionary with at least 'approved' (bool) and optional 'comments'.
        """
        logger.info(f"Requesting human review: {context}")
        print("\n" + "=" * 60)
        print("  HUMAN REVIEW REQUIRED")
        print("=" * 60)
        print(f"Context : {context}")
        if artifacts:
            print(f"Artifact: {artifacts}")
        print("=" * 60)

        start = time.time()
        while True:
            elapsed = time.time() - start
            if elapsed > self._timeout:
                logger.warning("Human review timed out.")
                return {"approved": False, "comments": "Review timed out."}

            response = (
                input("Approve? (y/n) [or 'c' to add comments]: ").strip().lower()
            )
            if response == "y":
                return {"approved": True, "comments": ""}
            if response == "n":
                comment = input("Reason for rejection: ").strip()
                return {"approved": False, "comments": comment}
            if response == "c":
                comment = input("Your comments: ").strip()
                approve = (
                    input("Approve after comments? (y/n): ").strip().lower() == "y"
                )
                return {"approved": approve, "comments": comment}
            print("Invalid input. Please enter 'y', 'n', or 'c'.")

    def notify(self, message: str) -> None:
        """Send an informational notification to the human operator."""
        logger.info(f"Notification to human: {message}")
        print(f"\n[AGENT NOTIFICATION] {message}\n")
