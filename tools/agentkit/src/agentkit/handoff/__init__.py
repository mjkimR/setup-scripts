"""Delegating a job to another agent and verifying it from the outcome.

The shape is deliberately general: a task says what to ask for, what permissions
the ask needs, and whether it should be driven one unit at a time. The runner
knows nothing about commits — only that it snapshots the world, asks, and looks
again.
"""

from .runner import run_handoff
from .tasks import TASKS, HandoffTask, get_task

__all__ = ["TASKS", "HandoffTask", "get_task", "run_handoff"]
