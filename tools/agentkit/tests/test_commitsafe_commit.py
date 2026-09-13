"""`agentkit commit-safe commit` — the wrapper that owns the git invocation.

The eval form it replaced needed a permission prompt from every agent CLI and
leaked this CLI's exit code; these cover what the replacement must not lose.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from click.testing import CliRunner

from agentkit.cli import cli
from agentkit.commitsafe import load_config, state_path


def _log(repo: Path, fmt: str) -> str:
    return subprocess.run(
        ["git", "log", "-1", f"--format={fmt}"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def test_it_commits_and_stamps_the_configured_window(safe_setup, repo, pending_file):
    pending_file("a.txt")
    subprocess.run(["git", "add", "a.txt"], cwd=str(repo), check=True)

    result = CliRunner().invoke(cli, ["commit-safe", "commit", "-m", "subject", "-m", "- body"])

    assert result.exit_code == 0, result.output
    assert _log(repo, "%s") == "subject"
    assert _log(repo, "%b").strip() == "- body"
    hour = int(_log(repo, "%ad").split()[3].split(":")[0])
    assert 9 <= hour <= 18, _log(repo, "%ad")


def test_a_preset_date_is_inherited_without_consuming_a_stamp(safe_setup, repo, pending_file, monkeypatch):
    """A handoff runner stamps in the parent; a second stamp here would drift."""
    pending_file("a.txt")
    subprocess.run(["git", "add", "a.txt"], cwd=str(repo), check=True)
    preset = "2020-01-02 03:04:05 +0900"
    monkeypatch.setenv("GIT_AUTHOR_DATE", preset)
    monkeypatch.setenv("GIT_COMMITTER_DATE", preset)

    result = CliRunner().invoke(cli, ["commit-safe", "commit", "-m", "inherited"])

    assert result.exit_code == 0, result.output
    assert _log(repo, "%ad") == "Thu Jan 2 03:04:05 2020 +0900"
    assert not state_path(load_config()).exists()


def test_a_rejected_identity_never_reaches_git(safe_setup, repo, pending_file):
    pending_file("a.txt")
    subprocess.run(["git", "add", "a.txt"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.email", "stranger@example.com"], cwd=str(repo), check=True)

    result = CliRunner().invoke(cli, ["commit-safe", "commit", "-m", "should not land"])

    assert result.exit_code != 0
    assert subprocess.run(["git", "log", "-1"], cwd=str(repo), capture_output=True).returncode != 0


def test_a_failing_commit_propagates_gits_exit_code(safe_setup, repo):
    # Nothing staged: git exits 1, and the wrapper must not report success.
    result = CliRunner().invoke(cli, ["commit-safe", "commit", "-m", "empty"])

    assert result.exit_code == 1


def test_a_message_is_required_so_no_editor_opens(safe_setup, repo, pending_file):
    pending_file("a.txt")
    subprocess.run(["git", "add", "a.txt"], cwd=str(repo), check=True)

    result = CliRunner().invoke(cli, ["commit-safe", "commit"])

    assert result.exit_code == 64, result.output


def test_amend_rewrites_rather_than_adding_a_commit(safe_setup, repo, pending_file):
    pending_file("a.txt")
    subprocess.run(["git", "add", "a.txt"], cwd=str(repo), check=True)
    CliRunner().invoke(cli, ["commit-safe", "commit", "-m", "first"])

    result = CliRunner().invoke(cli, ["commit-safe", "commit", "--amend", "-m", "revised"])

    assert result.exit_code == 0, result.output
    assert _log(repo, "%s") == "revised"
    count = subprocess.run(
        ["git", "rev-list", "--count", "HEAD"], cwd=str(repo), capture_output=True, text=True, check=True
    )
    assert count.stdout.strip() == "1"


def test_no_verify_skips_the_hook_that_would_block_the_commit(safe_setup, repo, pending_file):
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)
    pending_file("a.txt")
    subprocess.run(["git", "add", "a.txt"], cwd=str(repo), check=True)

    blocked = CliRunner().invoke(cli, ["commit-safe", "commit", "-m", "blocked"])
    allowed = CliRunner().invoke(cli, ["commit-safe", "commit", "--no-verify", "-m", "allowed"])

    assert blocked.exit_code == 1
    assert allowed.exit_code == 0, allowed.output
    assert _log(repo, "%s") == "allowed"


def test_it_takes_no_command_from_the_caller(safe_setup, repo):
    """`command(agentkit)` is a granted prefix — it must not reach arbitrary shell."""
    result = CliRunner().invoke(cli, ["commit-safe", "commit", "--", "rm", "-rf", "/tmp/nope"])

    assert result.exit_code == 64, result.output
    assert json.dumps(result.output)  # output is a string, not a crash


def test_commit_safe_auto_push(safe_setup, repo, pending_file, monkeypatch):
    from agentkit.repoconfig import PushConfig, RepoConfig, repo_config_path, save_repo_config

    pending_file("a.txt")
    subprocess.run(["git", "add", "a.txt"], cwd=str(repo), check=True)

    pushed_args = []
    real_run = subprocess.run

    def fake_subprocess_run(args, *pargs, **kwargs):
        if args and args[0] == "git" and len(args) > 1 and args[1] == "push":
            pushed_args.append(list(args))
            import collections

            Completed = collections.namedtuple("Completed", ["returncode"])
            return Completed(0)
        return real_run(args, *pargs, **kwargs)

    monkeypatch.setattr(subprocess, "run", fake_subprocess_run)

    # 1. Config push is disabled, but --push flag passed
    result = CliRunner().invoke(cli, ["commit-safe", "commit", "-m", "test push flag", "--push"])
    assert result.exit_code == 0
    assert len(pushed_args) == 1
    assert pushed_args[0] == ["git", "push"]

    # 2. Config push is enabled, no flag passed -> auto-pushes
    from agentkit.repoconfig import WhitelistConfig

    save_repo_config(
        RepoConfig(
            path=repo_config_path(cwd=repo),
            whitelist=WhitelistConfig(enabled=False),
            push=PushConfig(enabled=True, remote="origin"),
        ),
        cwd=repo,
    )
    pending_file("b.txt")
    subprocess.run(["git", "add", "b.txt"], cwd=str(repo), check=True)

    result2 = CliRunner().invoke(cli, ["commit-safe", "commit", "-m", "test config push"])
    assert result2.exit_code == 0
    assert len(pushed_args) == 2
    assert pushed_args[1] == ["git", "push", "origin"]

    # 3. Config push is enabled, but --no-push flag passed -> does not push
    pending_file("c.txt")
    subprocess.run(["git", "add", "c.txt"], cwd=str(repo), check=True)

    result3 = CliRunner().invoke(cli, ["commit-safe", "commit", "-m", "test no-push", "--no-push"])
    assert result3.exit_code == 0
    assert len(pushed_args) == 2
