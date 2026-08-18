"""Tests for the per-repository scratch space."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from click.testing import CliRunner

from agentkit import gitutil
from agentkit.cli import cli
from agentkit.errors import ConfigError
from agentkit.scratch import (
    DEFAULT_ROOT,
    MECHANISM_EXISTING,
    MECHANISM_GITIGNORE,
    MECHANISM_INFO_EXCLUDE,
    ScratchConfig,
    clean_scratch,
    load_scratch_config,
    parse_duration,
    resolve_scratch,
    save_scratch_config,
    scratch_config_path,
)


@pytest.fixture(autouse=True)
def _no_host_git_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """The host's global excludesFile must not decide what counts as ignored."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", "/dev/null")


def test_first_resolve_onboards_with_default(repo: Path) -> None:
    resolution = resolve_scratch(cwd=repo)

    assert resolution.in_repo
    assert resolution.onboarded
    assert resolution.mechanism == MECHANISM_INFO_EXCLUDE
    assert resolution.root == repo / DEFAULT_ROOT
    assert resolution.root.is_dir()

    exclude = (repo / ".git" / "info" / "exclude").read_text(encoding="utf-8")
    assert f"/{DEFAULT_ROOT}/" in exclude

    config = load_scratch_config(cwd=repo)
    assert config is not None
    assert config.root == DEFAULT_ROOT
    assert config.mechanism == MECHANISM_INFO_EXCLUDE


def test_scratch_files_never_reach_git_status(repo: Path) -> None:
    resolution = resolve_scratch(cwd=repo, subdir="handoff")
    (resolution.path / "2026-08-18-demo.md").write_text("x", encoding="utf-8")

    assert resolution.path == repo / DEFAULT_ROOT / "handoff"
    assert gitutil.pending(cwd=repo) == []


def test_second_resolve_is_not_an_onboarding(repo: Path) -> None:
    resolve_scratch(cwd=repo)
    again = resolve_scratch(cwd=repo)
    assert not again.onboarded


def test_resolve_respects_configured_root(repo: Path) -> None:
    save_scratch_config(ScratchConfig(root="work/scratch"), cwd=repo)

    resolution = resolve_scratch(cwd=repo)
    assert resolution.root == repo / "work" / "scratch"
    assert not resolution.onboarded
    # The configured root is excluded on resolve, so it stays out of status.
    (resolution.root / "note.md").write_text("x", encoding="utf-8")
    assert gitutil.pending(cwd=repo) == []


def test_already_ignored_root_leaves_exclude_untouched(repo: Path) -> None:
    (repo / ".gitignore").write_text(".agents/\n", encoding="utf-8")

    resolution = resolve_scratch(cwd=repo)
    assert resolution.mechanism == MECHANISM_EXISTING
    exclude = repo / ".git" / "info" / "exclude"
    assert f"/{DEFAULT_ROOT}/" not in exclude.read_text(encoding="utf-8")


def test_invalid_roots_and_subdirs_are_rejected(repo: Path) -> None:
    for bad in ("../outside", "/absolute", ".git/nested", ""):
        save_scratch_config(ScratchConfig(root=bad), cwd=repo)
        with pytest.raises(ConfigError):
            resolve_scratch(cwd=repo)

    scratch_config_path(cwd=repo).unlink()
    with pytest.raises(ConfigError):
        resolve_scratch(cwd=repo, subdir="../up")


def test_outside_a_repo_falls_back_under_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    workdir = tmp_path / "just-a-dir"
    workdir.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

    resolution = resolve_scratch(cwd=workdir, subdir="handoff")
    assert not resolution.in_repo
    assert not resolution.onboarded
    assert resolution.path.is_dir()
    assert resolution.path.is_relative_to(home / ".agents" / "tmp")
    assert resolution.path.name == "handoff"


def test_cli_path_prints_only_the_path(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    resolve_scratch(cwd=repo)  # onboard first so no [SETUP] note is emitted
    monkeypatch.chdir(repo)

    result = CliRunner().invoke(cli, ["scratch", "path", "handoff"])
    assert result.exit_code == 0
    assert result.output.strip() == str(repo / DEFAULT_ROOT / "handoff")


def test_cli_onboard_shared_writes_gitignore(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(repo)

    result = CliRunner().invoke(cli, ["scratch", "onboard", "--root", "tools/tmp", "--shared"])
    assert result.exit_code == 0
    assert "/tools/tmp/" in (repo / ".gitignore").read_text(encoding="utf-8")

    config = load_scratch_config(cwd=repo)
    assert config is not None
    assert config.root == "tools/tmp"
    assert config.mechanism == MECHANISM_GITIGNORE


def test_cli_onboard_refuses_silent_overwrite(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(repo)
    runner = CliRunner()

    runner.invoke(cli, ["scratch", "onboard"])
    unchanged = runner.invoke(cli, ["scratch", "onboard", "--root", "elsewhere"])
    assert unchanged.exit_code == 0
    config = load_scratch_config(cwd=repo)
    assert config is not None and config.root == DEFAULT_ROOT

    forced = runner.invoke(cli, ["scratch", "onboard", "--root", "elsewhere", "--force"])
    assert forced.exit_code == 0
    config = load_scratch_config(cwd=repo)
    assert config is not None and config.root == "elsewhere"


def test_parse_duration() -> None:
    assert parse_duration("30d") == 30 * 86400
    assert parse_duration("12h") == 12 * 3600
    assert parse_duration("15m") == 15 * 60
    assert parse_duration("45s") == 45
    assert parse_duration("60") == 60

    for bad in ("bad", "-5d", "30days", "10x", "", "   "):
        with pytest.raises(ConfigError):
            parse_duration(bad)


def test_clean_scratch_dry_run_and_delete(repo: Path) -> None:
    resolution = resolve_scratch(cwd=repo, subdir="handoff")
    old_file = resolution.path / "2026-07-01-old.md"
    old_file.write_text("old content", encoding="utf-8")
    past_time = time.time() - 40 * 86400
    os.utime(old_file, (past_time, past_time))

    new_file = resolution.path / "2026-08-18-new.md"
    new_file.write_text("new content", encoding="utf-8")

    # Dry-run does not delete anything
    affected = clean_scratch(30 * 86400, delete=False, cwd=repo)
    assert affected == [old_file]
    assert old_file.is_file()
    assert new_file.is_file()

    # Deletion removes old file, keeps new file, does not prune handoff dir because new file remains
    affected = clean_scratch(30 * 86400, delete=True, cwd=repo)
    assert affected == [old_file]
    assert not old_file.exists()
    assert new_file.is_file()
    assert resolution.path.is_dir()


def test_clean_scratch_prunes_empty_dirs(repo: Path) -> None:
    resolution = resolve_scratch(cwd=repo, subdir="nested/deep/handoff")
    old_file = resolution.path / "old.md"
    old_file.write_text("old", encoding="utf-8")
    past_time = time.time() - 40 * 86400
    os.utime(old_file, (past_time, past_time))

    clean_scratch(30 * 86400, delete=True, cwd=repo)
    assert not old_file.exists()
    # Pruned the nested empty directories, scratch root itself remains
    assert not (repo / DEFAULT_ROOT / "nested").exists()
    assert (repo / DEFAULT_ROOT).is_dir()


def test_cli_clean_dry_run_and_yes(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(repo)
    resolution = resolve_scratch(cwd=repo, subdir="handoff")
    old_file = resolution.path / "old.md"
    old_file.write_text("old", encoding="utf-8")
    past_time = time.time() - 40 * 86400
    os.utime(old_file, (past_time, past_time))

    runner = CliRunner()
    dry_result = runner.invoke(cli, ["scratch", "clean"])
    assert dry_result.exit_code == 0
    assert "handoff/old.md" in dry_result.output
    assert "Would remove 1 file (dry run; pass --yes to delete)." in dry_result.output
    assert old_file.is_file()

    yes_result = runner.invoke(cli, ["scratch", "clean", "--yes"])
    assert yes_result.exit_code == 0
    assert "handoff/old.md" in yes_result.output
    assert "Removed 1 file." in yes_result.output
    assert not old_file.exists()


def test_cli_clean_invalid_duration(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(repo)
    runner = CliRunner()
    result = runner.invoke(cli, ["scratch", "clean", "--older-than", "invalid"])
    assert result.exit_code != 0
    assert "invalid duration" in result.output


def test_cli_clean_empty_scratch(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(repo)
    runner = CliRunner()
    result = runner.invoke(cli, ["scratch", "clean"])
    assert result.exit_code == 0
    assert "Would remove 0 files (dry run; pass --yes to delete)." in result.output

    result_yes = runner.invoke(cli, ["scratch", "clean", "--yes"])
    assert result_yes.exit_code == 0
    assert "Removed 0 files." in result_yes.output
