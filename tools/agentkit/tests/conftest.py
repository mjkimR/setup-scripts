"""Fixtures shared by the agentkit tests.

Everything is isolated: a throwaway git repository, a stub `agy`, and agy
settings / commit-safe config / timestamp state redirected into tmp_path. No
test may read or write the machine's real ones.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from agentkit.agy import permissions
from agentkit.agy.client import AgyClient
from agentkit.commitsafe import config as safe_config

STUB = Path(__file__).parent / "stubs" / "agy_stub.py"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", ".")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "test")
    return root


@pytest.fixture
def pending_file(repo: Path):
    def add(name: str, content: str = "x") -> Path:
        path = repo / name
        path.write_text(content, encoding="utf-8")
        return path

    return add


@pytest.fixture
def granted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """agy settings holding every grant the handoff tasks need."""
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps(
            {
                "permissions": {
                    "allow": [
                        "command(git add)",
                        "command(git commit)",
                        "command(git ls-files)",
                        "command(git diff)",
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(permissions, "SETTINGS_PATH", settings)
    monkeypatch.setattr(permissions, "CONFIG_PATH", tmp_path / "absent.json")
    return settings


@pytest.fixture
def stub_agy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """An AgyClient wired to the stub, plus a reader for what it was asked."""
    calls = tmp_path / "agy-calls.jsonl"
    calls.touch()
    monkeypatch.setenv("AGY_STUB_CALLS", str(calls))

    class Stub:
        client = AgyClient(executable=str(STUB))

        @staticmethod
        def mode(value: str) -> None:
            monkeypatch.setenv("AGY_STUB_MODE", value)

        @staticmethod
        def calls() -> list:
            return [json.loads(line) for line in calls.read_text(encoding="utf-8").splitlines() if line.strip()]

    STUB.chmod(0o755)
    monkeypatch.setenv("AGY_STUB_MODE", "all")
    return Stub


@pytest.fixture
def safe_setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, repo: Path):
    """commit-safe config and timestamp state, both inside tmp_path."""
    config = tmp_path / "commit-safe.yaml"
    config.write_text(
        """
allowed_emails:
  - test@example.com

time:
  range:
    start: "19:00"
    end: "21:00"
  timezone: "Asia/Seoul"
  min_gap_seconds: 30
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.setenv(safe_config.CONFIG_ENV, str(config))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    # git_email() reads the identity of whatever directory the process is in.
    monkeypatch.chdir(repo)
    return config


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null"},
    ).stdout
