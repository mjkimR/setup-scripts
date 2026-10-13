"""What can be handed off, and on what terms.

Adding a task is adding an entry here: the skill to invoke, the prompt, the
grants it needs, and whether the runner should drive it one unit at a time.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

PERMITTED_GIT_COMMANDS: tuple[str, ...] = (*(f"git {verb}" for verb in ("log", "diff", "status", "ls-files", "add")),)


@dataclass(frozen=True)
class HandoffTask:
    """One delegable job."""

    name: str
    tag: str
    skill: str
    instructions: str
    grants: tuple[str, ...] = ()
    permitted: tuple[str, ...] = PERMITTED_GIT_COMMANDS
    per_unit: bool = False
    log_format: str = "%h  %s"
    date_format: str | None = None
    env_factory: Callable[[], tuple[dict[str, str], str]] | None = field(default=None, repr=False)

    def prompt(
        self,
        repo_root: Path,
        *,
        hints: tuple[str, ...] = (),
        tests: str | None = None,
        mode: str | None = None,
    ) -> str:
        return f"{self.skill}{' ' + mode if mode else ''}\n\nWork only in {repo_root}.\n\n{self.instructions}\n"


TASKS: dict[str, HandoffTask] = {}


def get_task(name: str) -> HandoffTask:
    return TASKS[name]
