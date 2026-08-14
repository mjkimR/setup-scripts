"""What can be handed off, and on what terms.

Adding a task is adding an entry here: the skill to invoke, the prompt, the
grants it needs, and whether the runner should drive it one unit at a time.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ..commitsafe import checked_identity, resolve
from ..repoconfig import load_repo_config

# Permission grants required by git commit handoff tasks.
COMMIT_GRANTS: tuple[str, ...] = (
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
    grants: tuple[str, ...] = ()
    per_unit: bool = False
    log_format: str = "%h  %s"
    date_format: str | None = None
    # Factory producing environment variables and display label for each run.
    env_factory: Callable[[], tuple[dict[str, str], str]] | None = field(default=None, repr=False)

    def prompt(self, repo_root: Path) -> str:
        repo_cfg = load_repo_config(cwd=repo_root)
        conventions_note = ""
        if repo_cfg is not None:
            lang_note = "Korean (한국어)" if repo_cfg.conventions.language == "ko" else "English"
            conventions_note = (
                f"\n\nRepository Commit Conventions:\n"
                f"- Preferred Language: {lang_note}\n"
                f"- Style: {repo_cfg.conventions.style}\n"
                f"- Template:\n{repo_cfg.conventions.template}\n"
            )

        return (
            f"{self.skill}\n\n"
            f"Work only in {repo_root} — that is the repository to commit.\n\n"
            f"{_GIT_ONLY}\n\n"
            f"{self.instructions}"
            f"{conventions_note}"
        )


def _commit_safe_env() -> tuple[dict[str, str], str]:
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

# Safe commit task with per-unit execution and timestamp injection.
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

TASKS: dict[str, HandoffTask] = {task.name: task for task in (COMMIT, COMMIT_SAFE)}


def get_task(name: str) -> HandoffTask:
    return TASKS[name]
