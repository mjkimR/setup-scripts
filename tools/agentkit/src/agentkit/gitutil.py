"""Thin git helpers.

Only what the rest of the package needs, and nothing that hides a failure: a
git call that goes wrong raises rather than returning an empty string that later
reads as "no changes".
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Sequence
from pathlib import Path

from .errors import GitCommandError, GitLockError, NotAGitRepoError

# `fatal: Unable to create '<path>/index.lock': File exists.` followed by
# `Another git process seems to be running in this repository`.
_LOCK_MARKER = re.compile(r"\.lock': File exists|another git process", re.IGNORECASE)


def run(args: Sequence[str], *, cwd: Path | None = None) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or str(result.returncode)
        command = f"git {' '.join(args)}"
        if _LOCK_MARKER.search(detail):
            # Somebody else is mid-write. Nothing here is broken and nothing to
            # repair — the lock clears on its own once they finish.
            raise GitLockError(
                f"{command} could not take the index lock.",
                retry_after="the other git process releases the lock (usually seconds)",
                what_to_report="Another git process is holding the repository lock, so nothing could run.",
                details=[detail],
            )
        raise GitCommandError(
            f"{command} failed: {detail}",
            what_to_report=f"A git command failed unexpectedly: {command}.",
            details=[detail],
        )
    return result.stdout


def repo_root(cwd: Path | None = None) -> Path:
    try:
        return Path(run(["rev-parse", "--show-toplevel"], cwd=cwd).strip())
    except GitCommandError as error:
        raise NotAGitRepoError(
            "not inside a git repository.",
            what_to_report=(
                "This directory is not inside a git repository. Ask the user where to run, "
                "or whether to create one — do not run `git init` on your own."
            ),
            details=[str(error)],
        ) from error


def head_sha(cwd: Path | None = None) -> str:
    """The current commit, or "" in a repository that has none yet.

    --verify --quiet matters: a bare `git rev-parse HEAD` on an unborn branch
    echoes the literal string "HEAD" to stdout before failing, and that string
    then compares as though it were a commit.
    """
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", "HEAD"],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def pending(cwd: Path | None = None) -> list[str]:
    output = run(["status", "--porcelain"], cwd=cwd)
    return [line for line in output.splitlines() if line.strip()]


def commit_range(before: str, after: str) -> str:
    """`before..after`, or just `after` when there was no commit to start from."""
    return f"{before}..{after}" if before else after


def count(rev_range: str, cwd: Path | None = None) -> int:
    return int(run(["rev-list", "--count", rev_range], cwd=cwd).strip())


def log(
    rev_range: str,
    fmt: str,
    *,
    date_format: str | None = None,
    cwd: Path | None = None,
) -> list[str]:
    args = ["log", f"--format={fmt}"]
    if date_format:
        args.append(f"--date=format:{date_format}")
    args.append(rev_range)
    return run(args, cwd=cwd).splitlines()


def config_value(key: str, cwd: Path | None = None) -> str:
    result = subprocess.run(
        ["git", "config", key],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()
