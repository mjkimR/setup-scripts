from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from agentkit.commitsafe import checked_identity
from agentkit.errors import ExitCode, IdentityError


def test_whitelisted_identity_passes(safe_setup, repo: Path):
    config, email = checked_identity()

    assert email == "test@example.com"
    assert config.allows(email)


def test_foreign_identity_is_rejected(safe_setup, repo: Path):
    subprocess.run(
        ["git", "config", "user.email", "stranger@example.com"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )

    with pytest.raises(IdentityError) as caught:
        checked_identity()

    assert caught.value.exit_code == ExitCode.FAILED
    assert "stranger@example.com" in str(caught.value)


def test_repo_config_overrides_global_whitelist(safe_setup, repo: Path):
    from agentkit.repoconfig import RepoConfig, WhitelistConfig, save_repo_config

    # Set user.email to another email not in global config
    subprocess.run(
        ["git", "config", "user.email", "corp@company.com"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )

    # But repository config explicitly allows it
    cfg = RepoConfig(
        path=repo / ".git" / "agentkit-commit.json",
        whitelist=WhitelistConfig(enabled=True, allowed_emails=["corp@company.com"]),
    )
    save_repo_config(cfg, cwd=repo)

    config, email = checked_identity(cwd=repo)
    assert email == "corp@company.com"
    assert config.allows(email)


def test_repo_config_disabled_whitelist_permits_foreign_email(safe_setup, repo: Path):
    from agentkit.repoconfig import RepoConfig, WhitelistConfig, save_repo_config

    subprocess.run(
        ["git", "config", "user.email", "stranger@example.com"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )

    cfg = RepoConfig(
        path=repo / ".git" / "agentkit-commit.json",
        whitelist=WhitelistConfig(enabled=False, allowed_emails=[]),
    )
    save_repo_config(cfg, cwd=repo)

    config, email = checked_identity(cwd=repo)
    assert email == "stranger@example.com"
    assert config.allows(email)
