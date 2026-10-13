"""Fixtures shared by the agentkit tests.

Everything is isolated: a throwaway git repository, a stub `agy`, and agy
settings redirected into tmp_path. No test may read or write the machine's real ones.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from agentkit.agy import permissions
from agentkit.agy.client import AgyClient
from tests.support.git import _git

STUB = Path(__file__).parent / "stubs" / "agy_stub.py"


@pytest.fixture(scope="session")
def empty_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Initialize Git once; each test gets an independent copy, including its config."""
    root = tmp_path_factory.mktemp("empty-repo")
    _git(root, "init", "-q", ".")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "test")
    return root


@pytest.fixture
def repo(tmp_path: Path, empty_repo: Path) -> Path:
    return Path(shutil.copytree(empty_repo, tmp_path / "repo"))


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
                        "command(git ls-files)",
                        "command(git diff)",
                        "command(agentkit commit context)",
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
