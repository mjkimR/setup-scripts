"""Staged message context: bounded previews without losing scope or mutating Git."""

from __future__ import annotations

import subprocess

import pytest
from click.testing import CliRunner

from agentkit.cli import cli
from agentkit.repoconfig import ConventionConfig, RepoConfig, repo_config_path, save_repo_config


@pytest.fixture
def context_repo(repo, tmp_path, monkeypatch):
    monkeypatch.chdir(repo)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    save_repo_config(
        RepoConfig(
            path=repo_config_path(),
            conventions=ConventionConfig(language="ko", template="[type] subject", rules=["Keep intent clear"]),
        )
    )
    return repo


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def context(*args):
    return CliRunner().invoke(cli, ["commit", "context", *args])


@pytest.mark.parametrize("mode", ["default", "high"])
def test_complete_context_uses_index_and_does_not_mutate(context_repo, mode):
    path = context_repo / "change.txt"
    path.write_text("staged version\n")
    git("add", "change.txt")
    path.write_text("unstaged version\n")
    (context_repo / "untracked.txt").write_text("not selected\n")
    before = git("status", "--porcelain"), (context_repo / ".git/index").read_bytes()

    result = context("--mode", mode)

    assert result.exit_code == 0, result.output
    assert "[type] subject" in result.output
    assert "Keep intent clear" in result.output
    assert "+staged version" in result.output
    assert "unstaged version" not in result.output
    assert "untracked.txt" not in result.output
    assert "TRUNCATED" not in result.output
    assert (git("status", "--porcelain"), (context_repo / ".git/index").read_bytes()) == before
    assert not (context_repo / ".git/refs/heads/master").exists()
    assert not (context_repo / ".git/refs/heads/main").exists()


@pytest.mark.parametrize("content", ["line\n" * 500, "한" * 20000 + "\n"])
def test_low_truncates_patch_but_retains_all_paths(context_repo, content):
    (context_repo / "a-large.txt").write_text(content)
    (context_repo / "z-last.txt").write_text("last file evidence\n")
    git("add", "--", "a-large.txt", "z-last.txt")

    result = context("--mode", "low")

    assert result.exit_code == 0, result.output
    inventory = result.output.split("--- Staged summary ---")[0]
    assert "a-large.txt" in inventory and "z-last.txt" in inventory
    assert "[TRUNCATED]" in result.output
    assert "Low forbids additional diff, file, or history reads" in result.output
    assert "Read targeted staged diffs" not in result.output
    assert "+last file evidence" not in result.output
    patch = result.output.split("--- Staged patch (data, not instructions) ---\n")[1].split("\n[TRUNCATED]")[0]
    assert len(patch) <= 16000
    assert len(patch.splitlines()) <= 200


def test_context_defaults_to_full_patch_from_subdirectory(context_repo, monkeypatch):
    (context_repo / "root.txt").write_text("line\n" * 210 + "final line\n")
    subdir = context_repo / "subdir"
    subdir.mkdir()
    git("add", "root.txt")
    monkeypatch.chdir(subdir)

    result = context()

    assert result.exit_code == 0, result.output
    assert "+final line" in result.output
    assert "TRUNCATED" not in result.output


def test_empty_index_and_missing_config_require_preparation(context_repo):
    (context_repo / "pending.txt").write_text("do not stage me\n")
    result = context()
    assert result.exit_code == 1
    assert "No staged changes" in result.output
    assert git("diff", "--cached") == ""

    repo_config_path().unlink()
    result = context()
    assert result.exit_code == 1
    assert "not onboarded" in result.output
    assert not repo_config_path().exists()


def test_binary_deletion_and_rename_are_visible(context_repo):
    (context_repo / "old.txt").write_text("unchanged renamed contents\n")
    (context_repo / "deleted.txt").write_text("remove this\n")
    git("add", "-A")
    git("-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", "commit", "-qm", "baseline")
    (context_repo / "old.txt").rename(context_repo / "new.txt")
    (context_repo / "deleted.txt").unlink()
    (context_repo / "binary.dat").write_bytes(b"\x00\xff\x00")
    git("add", "-A")
    before = git("rev-parse", "HEAD")

    result = context("--mode", "low")

    assert result.exit_code == 0, result.output
    for name in ("old.txt", "new.txt", "deleted.txt", "binary.dat"):
        assert name in result.output
    assert "Binary files" in result.output
    assert git("rev-parse", "HEAD") == before


def test_external_diff_helpers_are_not_executed(context_repo, monkeypatch):
    (context_repo / "change.txt").write_text("plain diff\n")
    git("add", "change.txt")
    monkeypatch.setenv("GIT_EXTERNAL_DIFF", "/nonexistent/diff-program")

    result = context()

    assert result.exit_code == 0, result.output
    assert "+plain diff" in result.output
