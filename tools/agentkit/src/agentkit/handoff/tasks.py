"""What can be handed off, and on what terms.

Adding a task is adding an entry here: the skill to invoke, the prompt, the
grants it needs, and whether the runner should drive it one unit at a time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

from ..commitsafe import checked_identity, resolve

# git ls-files is how the agent enumerates untracked files; without it a
# repository with any untracked path stalls the run. Read-only, like the
# log/diff/status rules that are usually already present.
COMMIT_GRANTS: Tuple[str, ...] = (
    "command(git add)",
    "command(git commit)",
    "command(git ls-files)",
)

# command(git reset) is deliberately absent. The agent reaches for
# `git add -N <path> && git diff <path> && git reset <path>` to inspect untracked
# files, but a prefix rule for `git reset` would also permit `git reset --hard`.
_GIT_ONLY = """Only git commands are permitted, and only these: log, diff, status, ls-files,
add, commit. Anything else — cat, ls, pwd, bash, and notably `git reset` — is
denied, and in a && chain one denied segment kills the whole command. To read an
untracked file, `git add` it and use `git diff --cached <path>`; never the
`git add -N` … `git reset` round trip. A denial is not a reason to stop: carry on
with git and finish the job."""


@dataclass(frozen=True)
class HandoffTask:
    """One delegable job."""

    name: str
    tag: str
    skill: str
    instructions: str
    grants: Tuple[str, ...] = ()
    per_unit: bool = False
    log_format: str = "%h  %s"
    date_format: Optional[str] = None
    # Called once per invocation, before agy starts. Returns the environment to
    # hand over plus a short label for the progress line. Raising here aborts
    # before any quota is spent, which is the point for the safe variant.
    env_factory: Optional[Callable[[], Tuple[Dict[str, str], str]]] = field(
        default=None, repr=False
    )

    def prompt(self, repo_root: Path) -> str:
        return (
            f"{self.skill}\n\n"
            f"Work only in {repo_root} — that is the repository to commit.\n\n"
            f"{_GIT_ONLY}\n\n"
            f"{self.instructions}"
        )


def _commit_safe_env() -> Tuple[Dict[str, str], str]:
    """Validate the identity and advance the timestamp for one unit."""
    config, _ = checked_identity()
    stamp = resolve(config)
    return stamp.as_env(), f"stamp: {stamp.format()}"


COMMIT = HandoffTask(
    name="commit",
    tag="handoff",
    skill="/git-commit",
    grants=COMMIT_GRANTS,
    instructions=(
        "Commit every pending change in that repository now.\n"
        "If you cannot tell whether some file belongs in a commit, leave it "
        "uncommitted\nand say so at the end."
    ),
)

# Delegates /git-commit, not /git-commit-safe: with the dates already resolved
# and exported by the runner, the safe skill's own workflow reduces to exactly
# what /git-commit does.
COMMIT_SAFE = HandoffTask(
    name="commit-safe",
    tag="handoff-safe",
    skill="/git-commit",
    grants=COMMIT_GRANTS,
    per_unit=True,
    log_format="%h  %ad  %s",
    date_format="%Y-%m-%d %H:%M:%S",
    env_factory=_commit_safe_env,
    instructions=(
        "GIT_AUTHOR_DATE and GIT_COMMITTER_DATE are already set in your "
        "environment. Do\nNOT resolve or override them — a plain `git add` and "
        "`git commit` inherits them.\n\n"
        "Commit EXACTLY ONE atomic unit of the pending changes, then stop. Leave "
        "every\nother change uncommitted; you will be called again for the next "
        "unit."
    ),
)

TASKS: Dict[str, HandoffTask] = {task.name: task for task in (COMMIT, COMMIT_SAFE)}


def get_task(name: str) -> HandoffTask:
    return TASKS[name]
