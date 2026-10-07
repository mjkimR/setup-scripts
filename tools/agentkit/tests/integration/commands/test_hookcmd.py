"""Integration tests for git hook commands in agentkit."""

from __future__ import annotations

import os
import subprocess

import pytest
from click.testing import CliRunner

from agentkit.cli import cli
from agentkit.repoconfig import (
    ConventionConfig,
    HooksConfig,
    PushConfig,
    RepoConfig,
    TimelineConfig,
    VerifyConfig,
    WhitelistConfig,
    repo_config_path,
    save_repo_config,
)


@pytest.fixture
def hook_repo(repo, tmp_path, monkeypatch):
    monkeypatch.chdir(repo)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    cfg = RepoConfig(
        path=repo_config_path(),
        whitelist=WhitelistConfig(enabled=True, allowed_emails=["test@example.com"]),
        hooks=HooksConfig(policy="bypass-intermediate", installed=False),
        conventions=ConventionConfig(style="conventional", language="en"),
    )
    save_repo_config(cfg)
    return repo


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def test_hook_install_uninstall_and_status(hook_repo):
    runner = CliRunner()
    result = runner.invoke(cli, ["hook", "status"])
    assert result.exit_code == 0
    assert "[NOT INSTALLED]" in result.output

    # Install
    result = runner.invoke(cli, ["hook", "install"])
    assert result.exit_code == 0
    assert "[SUCCESS] Installed git hooks" in result.output

    hooks_dir = hook_repo / ".git" / "hooks"
    pre_commit = hooks_dir / "pre-commit"
    commit_msg = hooks_dir / "commit-msg"
    post_commit = hooks_dir / "post-commit"
    assert pre_commit.exists()
    assert commit_msg.exists()
    assert post_commit.exists()
    assert os.access(pre_commit, os.X_OK)
    assert os.access(commit_msg, os.X_OK)
    assert os.access(post_commit, os.X_OK)

    # Status shows installed
    result = runner.invoke(cli, ["hook", "status"])
    assert result.exit_code == 0
    assert "[INSTALLED: managed by agentkit]" in result.output

    # Uninstall
    result = runner.invoke(cli, ["hook", "uninstall"])
    assert result.exit_code == 0
    assert not pre_commit.exists()
    assert not commit_msg.exists()
    assert not post_commit.exists()


def test_run_pre_commit_passes_clean_repo(hook_repo):
    runner = CliRunner()
    (hook_repo / "clean.txt").write_text("ordinary text\n")
    git("add", "clean.txt")

    # Quiet by default: no stdout noise on success
    result = runner.invoke(cli, ["hook", "run-pre-commit"])
    assert result.exit_code == 0
    assert result.output.strip() == ""

    # Verbose mode: prints ok status
    result_verbose = runner.invoke(cli, ["hook", "run-pre-commit", "--verbose"])
    assert result_verbose.exit_code == 0
    assert "[OK] All checks passed." in result_verbose.output


def test_run_pre_commit_blocks_secret(hook_repo):
    runner = CliRunner()
    # Fake secret matching Anthropic API key format
    secret_file = hook_repo / "leaked.txt"
    secret_file.write_text("sk-ant-api03-" + "a" * 50 + "\n")
    git("add", "leaked.txt")

    result = runner.invoke(cli, ["hook", "run-pre-commit"])
    assert result.exit_code != 0
    assert (
        "credential" in result.output.lower() or "secret" in result.output.lower() or "blocked" in result.output.lower()
    )


def test_run_commit_msg_empty_fails(hook_repo):
    runner = CliRunner()
    msg_path = hook_repo / "empty_msg.txt"
    msg_path.write_text("# only comments\n# second comment\n")

    result = runner.invoke(cli, ["hook", "run-commit-msg", str(msg_path)])
    assert result.exit_code != 0
    assert "Commit message cannot be empty" in result.output


def test_run_commit_msg_valid_succeeds(hook_repo):
    runner = CliRunner()
    msg_path = hook_repo / "good_msg.txt"
    msg_path.write_text("feat: add new feature\n\nDetailed explanation here.\n")

    # Quiet by default: silent on valid message
    result = runner.invoke(cli, ["hook", "run-commit-msg", str(msg_path)])
    assert result.exit_code == 0
    assert result.output.strip() == ""

    # Verbose mode: reports verified
    result_verbose = runner.invoke(cli, ["hook", "run-commit-msg", str(msg_path), "--verbose"])
    assert result_verbose.exit_code == 0
    assert "[OK] Commit message verified." in result_verbose.output


def test_run_pre_commit_isolates_staged_changes(hook_repo):
    runner = CliRunner()
    test_file = hook_repo / "file.py"
    test_file.write_text("print('clean')\n")
    git("add", "file.py")
    git("commit", "-m", "initial commit")

    cfg = RepoConfig(
        path=repo_config_path(),
        whitelist=WhitelistConfig(enabled=True, allowed_emails=["test@example.com"]),
        hooks=HooksConfig(policy="strict", installed=True),
        verify=VerifyConfig(
            enabled=True,
            test="python3 -c \"assert 'BROKEN' not in open('file.py').read()\"",
        ),
    )
    save_repo_config(cfg)

    # Staged change is clean
    test_file.write_text("print('clean modified')\n")
    git("add", "file.py")

    # Working tree has unstaged broken changes
    test_file.write_text("print('BROKEN')\n")

    # Pre-commit should pass because staged changes are isolated
    result = runner.invoke(cli, ["hook", "run-pre-commit", "--verbose"])
    assert result.exit_code == 0
    assert "[OK] All checks passed." in result.output

    # Working tree unstaged changes must be preserved
    assert "BROKEN" in test_file.read_text()


def test_run_pre_commit_bypassed_via_git_config(hook_repo):
    runner = CliRunner()
    cfg = RepoConfig(
        path=repo_config_path(),
        whitelist=WhitelistConfig(enabled=True, allowed_emails=["test@example.com"]),
        hooks=HooksConfig(policy="strict", installed=True),
        verify=VerifyConfig(
            enabled=True,
            test='python3 -c "raise SystemExit(1)"',
        ),
    )
    save_repo_config(cfg)

    (hook_repo / "clean.txt").write_text("ok\n")
    git("add", "clean.txt")

    git("config", "agentkit.verify", "false")

    # Quiet by default
    result = runner.invoke(cli, ["hook", "run-pre-commit"])
    assert result.exit_code == 0
    assert result.output.strip() == ""

    # Verbose mode reports bypass reason
    result_verbose = runner.invoke(cli, ["hook", "run-pre-commit", "--verbose"])
    assert result_verbose.exit_code == 0
    assert "Verification bypassed via git config" in result_verbose.output
    assert "[OK] All checks passed." in result_verbose.output


def test_run_pre_commit_blocks_unauthorized_email(hook_repo):
    runner = CliRunner()
    cfg = RepoConfig(
        path=repo_config_path(),
        whitelist=WhitelistConfig(enabled=True, allowed_emails=["allowed@dev.com"]),
        hooks=HooksConfig(policy="strict", installed=True),
    )
    save_repo_config(cfg)

    git("config", "user.email", "intruder@evil.com")
    (hook_repo / "clean.txt").write_text("ok\n")
    git("add", "clean.txt")

    result = runner.invoke(cli, ["hook", "run-pre-commit"])
    assert result.exit_code != 0
    assert "[BLOCKED]" in result.output
    assert "intruder@evil.com" in result.output


def test_run_post_commit_applies_timeline(hook_repo):
    runner = CliRunner()
    cfg = RepoConfig(
        path=repo_config_path(),
        whitelist=WhitelistConfig(enabled=True, allowed_emails=["test@example.com"]),
        timeline=TimelineConfig(enabled=True, start="19:00", end="23:00", timezone="Asia/Seoul"),
        hooks=HooksConfig(policy="strict", installed=True),
    )
    save_repo_config(cfg)

    (hook_repo / "clean.txt").write_text("content\n")
    git("add", "clean.txt")
    git("commit", "-m", "feat: initial commit")

    # Quiet by default: silent
    result = runner.invoke(cli, ["hook", "run-post-commit"])
    assert result.exit_code == 0
    assert result.output.strip() == ""

    commit_date = git("log", "-1", "--format=%cd", "--date=format:%H:%M").strip()
    hour = int(commit_date.split(":")[0])
    assert 19 <= hour <= 23

    # Verbose mode prints notification
    result_verbose = runner.invoke(cli, ["hook", "run-post-commit", "--verbose"])
    assert result_verbose.exit_code == 0
    assert "[hook:post-commit] Applying virtual timeline" in result_verbose.output


def test_git_commit_triggers_post_commit_timeline_automatically(hook_repo):
    runner = CliRunner()
    # Install hooks including post-commit
    runner.invoke(cli, ["hook", "install"])

    cfg = RepoConfig(
        path=repo_config_path(),
        whitelist=WhitelistConfig(enabled=True, allowed_emails=["test@example.com"]),
        timeline=TimelineConfig(enabled=True, start="19:00", end="23:00", timezone="Asia/Seoul"),
        hooks=HooksConfig(policy="strict", installed=True),
    )
    save_repo_config(cfg)

    (hook_repo / "clean.txt").write_text("content\n")
    git("add", "clean.txt")
    git("commit", "-m", "feat: auto post commit")

    commit_date = git("log", "-1", "--format=%cd", "--date=format:%H:%M").strip()
    hour = int(commit_date.split(":")[0])
    assert 19 <= hour <= 23


def test_run_pre_commit_distills_failed_verify_output(hook_repo):
    runner = CliRunner()
    script = (
        "python3 -c \""
        "import sys; "
        "[print(f'passing step {i}') for i in range(50)]; "
        "sys.stderr.write('fatal test failure: assertion failed\\n'); "
        "sys.exit(1)\""
    )
    cfg = RepoConfig(
        path=repo_config_path(),
        whitelist=WhitelistConfig(enabled=True, allowed_emails=["test@example.com"]),
        hooks=HooksConfig(policy="strict", installed=True, verbosity="quiet"),
        verify=VerifyConfig(enabled=True, test=script),
    )
    save_repo_config(cfg)

    (hook_repo / "clean.txt").write_text("content\n")
    git("add", "clean.txt")

    result = runner.invoke(cli, ["hook", "run-pre-commit"])
    assert result.exit_code != 0
    assert "[hook:pre-commit] [FAIL] 'test' check failed" in result.output
    assert "--- Output (last 25 lines of" in result.output
    assert "fatal test failure: assertion failed" in result.output
    assert "[hint] To re-run this check directly" in result.output
    assert "[hint] To bypass verify for intermediate commit" in result.output


def test_run_pre_commit_compact_mode(hook_repo):
    runner = CliRunner()
    cfg = RepoConfig(
        path=repo_config_path(),
        whitelist=WhitelistConfig(enabled=True, allowed_emails=["test@example.com"]),
        hooks=HooksConfig(policy="strict", installed=True, verbosity="compact"),
        verify=VerifyConfig(enabled=True, test="python3 -c 'print(\"ok\")'"),
    )
    save_repo_config(cfg)

    (hook_repo / "clean.txt").write_text("content\n")
    git("add", "clean.txt")

    result = runner.invoke(cli, ["hook", "run-pre-commit"])
    assert result.exit_code == 0
    assert "✓ test passed" in result.output
    assert "[hook:pre-commit] [OK] All checks passed." in result.output


def test_run_post_commit_auto_push_successful(hook_repo, monkeypatch):
    runner = CliRunner()
    cfg = RepoConfig(
        path=repo_config_path(),
        whitelist=WhitelistConfig(enabled=True, allowed_emails=["test@example.com"]),
        hooks=HooksConfig(policy="strict", installed=True),
        push=PushConfig(enabled=True, remote="origin", branch="main"),
    )
    save_repo_config(cfg)

    (hook_repo / "clean.txt").write_text("content\n")
    git("add", "clean.txt")
    git("commit", "-m", "feat: initial commit")

    pushed_args = []
    real_run = subprocess.run

    def mock_run(args, **kwargs):
        if isinstance(args, list) and len(args) > 1 and args[0] == "git" and args[1] == "push":
            pushed_args.append(list(args))
            return subprocess.CompletedProcess(args, 0, stdout="Everything up-to-date\n", stderr="")
        return real_run(args, **kwargs)

    monkeypatch.setattr(subprocess, "run", mock_run)

    result = runner.invoke(cli, ["hook", "run-post-commit"])
    assert result.exit_code == 0
    assert len(pushed_args) == 1
    assert pushed_args[0] == ["git", "push", "origin", "main"]
    assert "[hook:post-commit] [PUSH] Auto-pushed to origin main." in result.output


def test_run_post_commit_auto_push_bypassed_via_git_config(hook_repo, monkeypatch):
    runner = CliRunner()
    cfg = RepoConfig(
        path=repo_config_path(),
        whitelist=WhitelistConfig(enabled=True, allowed_emails=["test@example.com"]),
        hooks=HooksConfig(policy="strict", installed=True),
        push=PushConfig(enabled=True, remote="origin", branch="main"),
    )
    save_repo_config(cfg)

    (hook_repo / "clean.txt").write_text("content\n")
    git("add", "clean.txt")
    git("commit", "-m", "feat: initial commit")

    git("config", "agentkit.push", "false")

    pushed_args = []
    real_run = subprocess.run

    def mock_run(args, **kwargs):
        if isinstance(args, list) and len(args) > 1 and args[0] == "git" and args[1] == "push":
            pushed_args.append(list(args))
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        return real_run(args, **kwargs)

    monkeypatch.setattr(subprocess, "run", mock_run)

    result = runner.invoke(cli, ["hook", "run-post-commit", "--verbose"])
    assert result.exit_code == 0
    assert len(pushed_args) == 0
    assert "Auto-push bypassed via git config" in result.output


def test_run_post_commit_auto_push_failure_shows_error_and_hint(hook_repo, monkeypatch):
    runner = CliRunner()
    cfg = RepoConfig(
        path=repo_config_path(),
        whitelist=WhitelistConfig(enabled=True, allowed_emails=["test@example.com"]),
        hooks=HooksConfig(policy="strict", installed=True),
        push=PushConfig(enabled=True, remote="origin", branch="main"),
    )
    save_repo_config(cfg)

    (hook_repo / "clean.txt").write_text("content\n")
    git("add", "clean.txt")
    git("commit", "-m", "feat: initial commit")

    real_run = subprocess.run

    def mock_run(args, **kwargs):
        if isinstance(args, list) and len(args) > 1 and args[0] == "git" and args[1] == "push":
            return subprocess.CompletedProcess(args, 1, stdout="", stderr="fatal: remote rejected")
        return real_run(args, **kwargs)

    monkeypatch.setattr(subprocess, "run", mock_run)

    result = runner.invoke(cli, ["hook", "run-post-commit"])
    assert result.exit_code == 0
    assert "[hook:post-commit] [ERROR] Auto-push failed: fatal: remote rejected" in result.output
    assert "[hint] To push manually: git push origin main" in result.output


def test_commit_conventions_shows_auto_push_status(hook_repo):
    runner = CliRunner()
    # 1. When push is off
    result = runner.invoke(cli, ["commit", "conventions"])
    assert result.exit_code == 0
    assert "Auto-push: [OFF]" in result.output

    # 2. When push is on
    cfg = RepoConfig(
        path=repo_config_path(),
        whitelist=WhitelistConfig(enabled=True, allowed_emails=["test@example.com"]),
        hooks=HooksConfig(policy="strict", installed=True),
        push=PushConfig(enabled=True, remote="origin", branch="main"),
    )
    save_repo_config(cfg)

    result2 = runner.invoke(cli, ["commit", "conventions"])
    assert result2.exit_code == 0
    assert "Auto-push: [ON] (origin/main)" in result2.output
