"""Thin git helpers.

Only what the rest of the package needs, and nothing that hides a failure: a
git call that goes wrong raises rather than returning an empty string that later
reads as "no changes".
"""

from __future__ import annotations

import contextlib
import os
import re
import subprocess
import sys
from collections.abc import Generator, Sequence
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
    """The current commit SHA, or empty string if repository has no commits yet."""
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


def config_bool(key: str, default: bool | None = None, cwd: Path | None = None) -> bool | None:
    """Return a git config value interpreted as boolean, or default if unset."""
    result = subprocess.run(
        ["git", "config", "--bool", key],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return default
    val = result.stdout.strip().lower()
    if val == "true":
        return True
    if val == "false":
        return False
    return default


@contextlib.contextmanager
def staged_snapshot(cwd: Path | None = None) -> Generator[None, None, None]:
    """Temporarily stash unstaged changes so commands run strictly against staged content.

    Restores the unstaged working tree in a finally block.
    """
    target = str(cwd) if cwd else None
    target_path = Path(target) if target else None

    # git stash requires at least one commit in the repository (fails on unborn branch)
    if not head_sha(target_path):
        yield
        return

    diff_proc = subprocess.run(
        ["git", "diff", "--quiet"],
        cwd=target,
        capture_output=True,
    )
    # returncode 0 means no unstaged changes in tracked files
    if diff_proc.returncode == 0:
        yield
        return

    stash_msg = f"agentkit-precommit-staged-{os.getpid()}"
    stash_push = subprocess.run(
        ["git", "stash", "push", "--keep-index", "-m", stash_msg],
        cwd=target,
        capture_output=True,
        text=True,
    )
    stashed = stash_push.returncode == 0
    try:
        yield
    finally:
        if stashed:
            pop_res = subprocess.run(
                ["git", "stash", "pop", "-q"],
                cwd=target,
                capture_output=True,
                text=True,
            )
            if pop_res.returncode != 0:
                sys.stderr.write(
                    f"[hook:pre-commit] [WARN] Failed to automatically pop unstaged changes stash: {pop_res.stderr.strip()}\n"
                    f"[hook:pre-commit] [WARN] Stashed changes preserved in: {stash_msg}\n"
                )
