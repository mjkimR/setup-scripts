"""How git failures are classified.

`gitutil.run` is the one place a git invocation can go wrong, and the three
outcomes it separates need different things from the caller: a missing
repository is the user's to resolve, a held lock resolves itself, and anything
else stops the job.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from agentkit import gitutil
from agentkit.errors import ActionMode, ErrorCode, GitCommandError, GitLockError, NotAGitRepoError

LOCK_STDERR = (
    "fatal: Unable to create '/tmp/r/.git/index.lock': File exists.\n\n"
    "Another git process seems to be running in this repository, e.g.\n"
    "an editor opened by 'git commit'."
)


def _failing_git(monkeypatch, stderr: str) -> None:
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args, returncode=128, stdout="", stderr=stderr)

    monkeypatch.setattr(subprocess, "run", fake_run)


def test_a_held_index_lock_defers_instead_of_failing(monkeypatch):
    _failing_git(monkeypatch, LOCK_STDERR)

    with pytest.raises(GitLockError) as caught:
        gitutil.run(["status", "--porcelain"])

    error = caught.value
    assert error.code == ErrorCode.GIT_LOCK_HELD
    assert error.mode == ActionMode.DEFER
    rendered = "\n".join(error.advisory.lines(str(error)))
    assert "[WHEN]" in rendered
    assert "index.lock" in rendered


def test_an_unrecognised_git_failure_halts(monkeypatch):
    _failing_git(monkeypatch, "fatal: bad object HEAD~99")

    with pytest.raises(GitCommandError) as caught:
        gitutil.run(["rev-list", "--count", "HEAD~99..HEAD"])

    error = caught.value
    assert error.code == ErrorCode.GIT_COMMAND_FAILED
    assert error.mode == ActionMode.HALT
    assert "bad object" in str(error)
    # A lock is the only failure that gets to defer.
    assert not isinstance(error, GitLockError)


def test_outside_a_repository_the_user_decides_what_to_do(tmp_path: Path):
    with pytest.raises(NotAGitRepoError) as caught:
        gitutil.repo_root(cwd=tmp_path)

    error = caught.value
    assert error.code == ErrorCode.NOT_A_GIT_REPO
    assert error.mode == ActionMode.INTERACTION
    # `git init` would be improvising past the error, not repairing it, so it
    # must never reach [FIX] — where the caller runs whatever it is told.
    assert error.fix is None
