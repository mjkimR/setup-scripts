import subprocess
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from devkit import clipboard
from devkit.cli import cli, write_export


def git(*args):
    return subprocess.check_output(["git", *args], text=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    git("init", "-q")
    git("config", "user.name", "Test")
    git("config", "user.email", "test@example.com")
    git("config", "commit.gpgsign", "false")
    git("config", "core.hooksPath", "/dev/null")
    (tmp_path / "file.txt").write_text("initial\n")
    git("add", ".")
    git("commit", "-qm", "Initial")
    return tmp_path


def test_export_preserves_partial_staging_and_includes_lockfile(repo):
    (repo / "file.txt").write_text("staged\n")
    (repo / "uv.lock").write_text("locked\n")
    git("add", ".")
    (repo / "file.txt").write_text("unstaged\n")
    (repo / "new.txt").write_text("untracked\n")
    before = git("diff", "--cached")
    status = git("status", "--porcelain")
    result = CliRunner().invoke(cli, ["copy-diff", "--no-copy"])
    assert result.exit_code == 0, result.output
    exported = Path(result.output.strip()).read_text()
    assert "+staged" in exported and "+unstaged" not in exported
    assert "uv.lock" in exported and "new.txt" not in exported
    assert git("diff", "--cached") == before
    assert git("status", "--porcelain") == status


def test_head_from_subdirectory_and_exclusion(repo, monkeypatch):
    (repo / "file.txt").write_text("modified\n")
    (repo / "uv.lock").write_text("lock\n")
    git("add", "uv.lock")
    (repo / "sub").mkdir()
    monkeypatch.chdir(repo / "sub")
    result = CliRunner().invoke(cli, ["prompt", "review", "--head", "--exclude", "uv.lock", "--stdout"])
    assert result.exit_code == 0, result.output
    assert "+modified" in result.output and "uv.lock" not in result.output


def test_last_handles_initial_commit(repo):
    result = CliRunner().invoke(cli, ["prompt", "review", "--last", "--stdout"])
    assert result.exit_code == 0, result.output
    assert "+initial" in result.output


def test_staged_before_initial_commit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    git("init", "-q")
    (tmp_path / "first").write_text("hello\n")
    git("add", "first")
    result = CliRunner().invoke(cli, ["prompt", "commit", "-l", "Korean", "--stdout"])
    assert result.exit_code == 0, result.output
    assert "**Korean**" in result.output and "+hello" in result.output


def test_empty_and_conflicting_options(repo):
    result = CliRunner().invoke(cli, ["copy-diff", "--no-copy"])
    assert result.exit_code != 0 and "No staged changes" in result.output
    result = CliRunner().invoke(cli, ["prompt", "review", "--head", "--last"])
    assert result.exit_code != 0 and "mutually exclusive" in result.output


def test_outside_repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(cli, ["copy-diff"])
    assert result.exit_code != 0 and "git repository" in result.output


def test_clipboard_failure_preserves_prompt(repo, monkeypatch):
    def fail(text):
        raise RuntimeError("no clipboard")

    monkeypatch.setattr(clipboard, "copy_text", fail)
    result = CliRunner().invoke(cli, ["prompt", "review", "--last"])
    assert result.exit_code == 0
    assert "no clipboard" in result.output and "+initial" in result.output


def test_file_clipboard_failure_preserves_export(repo, monkeypatch):
    def fail(path):
        raise RuntimeError("no clipboard")

    monkeypatch.setattr(clipboard, "copy_file", fail)
    result = CliRunner().invoke(cli, ["copy-diff", "--last"])
    assert result.exit_code == 0
    assert Path(result.output.splitlines()[0]).exists()
    assert "File saved" in result.output


def test_exports_are_unique_and_filename_cannot_escape():
    a = write_export("one", "review")
    b = write_export("two", "review")
    assert a.name == "review.txt" and a != b
    assert a.read_text() == "one" and b.read_text() == "two"
    for name in ["../escape", "/tmp/escape", ".", ".."]:
        with pytest.raises(click.BadParameter, match="filename without directories"):
            write_export("bad", name)


def test_macos_file_path_is_an_argument(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(clipboard.sys, "platform", "darwin")
    monkeypatch.setattr(clipboard.subprocess, "run", lambda *a, **kw: calls.append((a, kw)))
    path = tmp_path / 'a"quoted\\file.txt'
    clipboard.copy_file(path)
    command = calls[0][0][0]
    assert command[-1] == str(path)
    assert str(path) not in command[2]


def test_wayland_falls_back_when_unavailable(monkeypatch):
    monkeypatch.setattr(clipboard.sys, "platform", "linux")
    monkeypatch.setattr(clipboard.shutil, "which", lambda name: name if name in {"wl-copy", "xclip"} else None)
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if command[0] == "wl-copy":
            raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(clipboard.subprocess, "run", run)
    clipboard.copy_text("hello")
    assert [c[0] for c in calls] == ["wl-copy", "xclip"]


@pytest.mark.parametrize(
    "args", [["--help"], ["copy-diff", "--help"], ["prompt", "--help"], ["prompt", "review", "--help"]]
)
def test_help_exits_successfully(args):
    result = CliRunner().invoke(cli, args)
    assert result.exit_code == 0, result.output
    assert "Error:" not in result.output
