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


def test_denied_commands_also_come_from_the_conversation_record(tmp_path):
    """agy 1.2.0 names the denied command only in the conversation record, with quotes escaped."""
    db = tmp_path / "8aef4894-5128-4f65-b2a8-18b4c4cbd3d4.db"
    db.write_bytes(
        b"\x00SQLite format 3\x00"
        b'permission check failed for command "git diff src/x.py | grep -E \\"^\\+(from|import)\\"": user denied'
        b"\x00\x00"
    )
    run = AgyRun(
        output="a tool required the command permission",
        log='I0910 session.go:172] Print mode: conversation=8aef4894-5128-4f65-b2a8-18b4c4cbd3d4, sending message\nsoft-denying tool confirmation "RunCommand" at step 2\n',
        conversation_db=db,
    )

    assert run.conversation_id == "8aef4894-5128-4f65-b2a8-18b4c4cbd3d4"
    assert run.denied_commands() == ['git diff src/x.py | grep -E "^\\+(from|import)"']
    assert run.evidence() == [f"Conversation: 8aef4894-5128-4f65-b2a8-18b4c4cbd3d4 ({db})"]


def test_a_run_keeps_its_log_and_finds_its_conversation(tmp_path, monkeypatch, stub_agy):
    from agentkit.agy import client as client_module

    monkeypatch.setattr(client_module, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(client_module, "CONVERSATIONS_DIR", tmp_path / "conversations")
    stub_agy.mode("none")
    monkeypatch.setenv("AGY_STUB_DENIED", "git ls-files --others")

    run = stub_agy.client.run("do it", add_dir=tmp_path)

    assert run.log_path is not None and run.log_path.parent == tmp_path / "logs"
    assert run.log_path.read_text(encoding="utf-8") == run.log
    assert run.denied_commands() == ["git ls-files --others"]
    assert any(line.startswith("Log: ") for line in run.evidence())


def test_pipelines_are_out_of_scope_when_any_segment_is():
    from agentkit.agy.diagnose import outside_scope, segments

    permitted = ("git diff", "git log")
    assert segments('git diff a.py | grep -E "x|y" && git log') == ["git diff a.py", 'grep -E "x', 'y"', "git log"]
    assert outside_scope(["git diff a.py"], permitted) == []
    assert outside_scope(["git diff a.py | grep import"], permitted) == ["git diff a.py | grep import"]
    assert outside_scope(["git log; git show"], permitted) == ["git log; git show"]
