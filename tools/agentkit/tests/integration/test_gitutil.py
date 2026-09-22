from __future__ import annotations

from pathlib import Path

import pytest

from agentkit import gitutil
from agentkit.errors import ActionMode, ErrorCode, NotAGitRepoError


def test_outside_a_repository_the_user_decides_what_to_do(tmp_path: Path):
    with pytest.raises(NotAGitRepoError) as caught:
        gitutil.repo_root(cwd=tmp_path)

    error = caught.value
    assert error.code == ErrorCode.NOT_A_GIT_REPO
    assert error.mode == ActionMode.INTERACTION
    # `git init` would be improvising past the error, not repairing it, so it
    # must never reach [FIX] — where the caller runs whatever it is told.
    assert error.fix is None
