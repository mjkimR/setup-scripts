"""Thin git helpers.

Only what the rest of the package needs, and nothing that hides a failure: a
git call that goes wrong raises rather than returning an empty string that later
reads as "no changes".
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path

from .errors import PreflightError


def run(args: Sequence[str], *, cwd: Path | None = None) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise PreflightError(f"git {' '.join(args)} failed: {result.stderr.strip() or result.returncode}")
    return result.stdout


def repo_root(cwd: Path | None = None) -> Path:
    try:
        return Path(run(["rev-parse", "--show-toplevel"], cwd=cwd).strip())
    except PreflightError as error:
        raise PreflightError("not inside a git repository.") from error


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
