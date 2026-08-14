"""The Antigravity adapter: allow-list handling and reading a finished run."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentkit.agy import permissions
from agentkit.agy.client import AgyRun
from agentkit.errors import PreflightError


def write(path: Path, document) -> Path:
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_rules_are_collected_from_both_files(tmp_path, monkeypatch):
    settings = write(tmp_path / "settings.json", {"permissions": {"allow": ["a"]}})
    config = write(tmp_path / "config.json", {"nested": {"deep": {"allow": ["b"]}}})
    monkeypatch.setattr(permissions, "SETTINGS_PATH", settings)
    monkeypatch.setattr(permissions, "CONFIG_PATH", config)

    assert permissions.granted_rules() == {"a", "b"}


def test_unreadable_files_are_skipped_not_fatal(tmp_path, monkeypatch):
    broken = tmp_path / "settings.json"
    broken.write_text("{ not json", encoding="utf-8")
    monkeypatch.setattr(permissions, "SETTINGS_PATH", broken)
    monkeypatch.setattr(permissions, "CONFIG_PATH", tmp_path / "absent.json")

    assert permissions.granted_rules() == set()


def test_missing_rules_preserves_the_requested_order(tmp_path, monkeypatch):
    settings = write(tmp_path / "settings.json", {"permissions": {"allow": ["b"]}})
    monkeypatch.setattr(permissions, "SETTINGS_PATH", settings)
    monkeypatch.setattr(permissions, "CONFIG_PATH", tmp_path / "absent.json")

    assert permissions.missing_rules(["a", "b", "c"]) == ["a", "c"]


def test_granting_backs_up_and_is_idempotent(tmp_path):
    settings = write(tmp_path / "settings.json", {"permissions": {"allow": ["a"]}})

    assert permissions.grant(["a", "b"], settings_path=settings) == ["b"]

    backup = json.loads(settings.with_suffix(".json.bak").read_text(encoding="utf-8"))
    assert backup["permissions"]["allow"] == ["a"]

    written = json.loads(settings.read_text(encoding="utf-8"))
    assert written["permissions"]["allow"] == ["a", "b"]

    assert permissions.grant(["a", "b"], settings_path=settings) == []


def test_granting_without_settings_explains_itself(tmp_path):
    with pytest.raises(PreflightError) as caught:
        permissions.grant(["a"], settings_path=tmp_path / "absent.json")

    assert "interactively" in " ".join(caught.value.hints)


def test_denied_commands_come_from_the_log_not_stdout():
    run = AgyRun(
        output="a tool required the command permission",
        log=(
            'permission check failed for command "git ls-files --others"\n'
            'permission check failed for command "git reset"\n'
            'permission check failed for command "git reset"\n'
        ),
    )

    assert run.denied_commands() == ["git ls-files --others", "git reset"]


def test_failure_modes_are_told_apart():
    denial = AgyRun(output="headless mode cannot prompt for permission", log="")
    auth = AgyRun(output="authentication failed or timed out", log="")
    quiet = AgyRun(output="I decided not to commit anything.", log="")

    assert denial.hit_permission_wall
    assert auth.looks_unauthenticated and not auth.hit_permission_wall
    assert not quiet.hit_permission_wall and not quiet.looks_unauthenticated
