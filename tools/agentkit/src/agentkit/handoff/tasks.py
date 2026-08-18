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
# The same six verbs _GIT_ONLY spells out in prose, as command prefixes: what
# the task actually authorizes the receiver to run. A denial outside this set
# is a prompt bug (the receiver was steered to a command it may never run),
# not a missing grant — the two need different fixes.
PERMITTED_GIT_COMMANDS: tuple[str, ...] = tuple(
    f"git {verb}" for verb in ("log", "diff", "status", "ls-files", "add", "commit")
)

_GIT_ONLY = """Only git commands are permitted, and only these: log, diff, status, ls-files,
add, commit. Anything else — cat, ls, pwd, bash, and notably `git reset` — is
denied, and in a && chain one denied segment kills the whole command. To read an
untracked file, `git add` it and use `git diff --cached <path>`; never the
`git add -N` … `git reset` round trip. A denial is not a reason to stop: carry on
with git and finish the job."""

# Shared grouping rules for both commit tasks. Only git is permitted, so
# per-commit greenness is nothing the receiver could verify anyway — stating
# that explicitly stops it from trying, or from apologizing for not trying.
_GROUPING_RULES = """Grouping rules:
- A file's entire change belongs to exactly one commit. Never split one file's
  changes across commits — no partial staging. When one file carries several
  concerns, put it whole into the commit of its dominant concern (tie-break:
  the earliest commit that needs it) and note the piggybacked change in that
  commit's body.
- Intermediate commits of a multi-commit split do not need to keep tests or
  the build green. Only the last commit must leave the tree exactly as it is
  now. Spend no effort verifying or ordering for per-commit greenness.
- Never run tests, builds or linters — committing is the whole job, and
  nothing but git is permitted anyway."""

# What the tests attestation authorizes the receiver to assume. The caller
# vouches for the tree it hands off; the receiver acts on the claim without
# repeating the work — that is the entire point of carrying it over.
_TESTS_NOTES = {
    "passed": (
        "Tests: the caller ran the test suite on exactly this tree and it "
        "passed.\n  Trust that — do not re-run, re-verify, or hedge about it."
    ),
    "failed": (
        "Tests: the caller reports the test suite failing on this tree. Commit"
        "\n  anyway; fixing tests is not your job and not a reason to hold back."
    ),
    "not-run": (
        "Tests: the caller did not run tests on this tree. Do not run them"
        "\n  either, and do not speculate about their state."
    ),
}


def _caller_context(hints: tuple[str, ...], tests: str | None, *, per_unit: bool) -> str:
    """The caller's knowledge of the work, carried into the receiver's prompt.

    Hints are advisory by design: the caller writes them from memory of the
    work, and memory can lag the tree (manual edits after the fact). The diff
    stays the ground truth, so a mismatch degrades gracefully instead of
    forcing padded or withheld commits.
    """
    if not hints and tests is None:
        return ""

    lines: list[str] = ["", "Caller context — written by the agent that did the work:"]
    if hints:
        lines.append("- Suggested commit units, in order:")
        lines.extend(f"  {i}. {hint}" for i, hint in enumerate(hints, start=1))
        lines.append(
            "- The hints are grouping labels, not final subjects: write every\n"
            "  commit subject yourself, following the repository conventions.\n"
            "- The diff is the ground truth. Where the tree does not match a hint,\n"
            "  follow the diff: never create an empty or padded commit to satisfy\n"
            "  the hint count, never leave a change uncommitted because no hint\n"
            "  covers it, and report the mismatch at the end."
        )
        if per_unit:
            # Name the exact permitted command: told merely to "check git log",
            # the receiver reaches for `git show` — which is denied — to see
            # what earlier commits covered, and stalls the whole unit on it.
            lines.append(
                "- Earlier units of this handoff are already committed. See what they\n"
                "  covered with `git log --oneline --name-only -20` — use exactly that\n"
                "  command (`git show` is denied) — then take the first hint whose\n"
                "  work is still uncommitted."
            )
    if tests is not None:
        lines.append(f"- {_TESTS_NOTES[tests]}")
    return "\n".join(lines) + "\n"


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
    # Factory producing environment variables and display label for each run.
    env_factory: Callable[[], tuple[dict[str, str], str]] | None = field(default=None, repr=False)

    def prompt(
        self,
        repo_root: Path,
        *,
        hints: tuple[str, ...] = (),
        tests: str | None = None,
    ) -> str:
        repo_cfg = load_repo_config(cwd=repo_root)
        conventions_note = ""
        hooks_note = ""
        if repo_cfg is not None:
            lang_note = "Korean (한국어)" if repo_cfg.conventions.language == "ko" else "English"
            conventions_note = (
                f"\n\nRepository Commit Conventions:\n"
                f"- Preferred Language: {lang_note}\n"
                f"- Style: {repo_cfg.conventions.style}\n"
                f"- Template:\n{repo_cfg.conventions.template}\n"
            )
            # Only bypass-intermediate reaches this point: the runner's
            # preflight refuses every other policy value before delegating.
            if repo_cfg.hooks.policy == "bypass-intermediate":
                hooks_note = (
                    "\nHook policy (bypass-intermediate): a commit that leaves further "
                    "changes\nuncommitted gets `git commit --no-verify`. The commit that "
                    "makes the working\ntree clean is a plain `git commit`, so hooks run "
                    "once, on the final state.\nThis is configured, not yours to decide — "
                    "never add --no-verify anywhere else.\n"
                )

        return (
            f"{self.skill}\n\n"
            f"Work only in {repo_root} — that is the repository to commit.\n\n"
            f"{_GIT_ONLY}\n\n"
            f"{_GROUPING_RULES}\n"
            f"{hooks_note}\n"
            f"{self.instructions}\n"
            f"{_caller_context(hints, tests, per_unit=self.per_unit)}"
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
