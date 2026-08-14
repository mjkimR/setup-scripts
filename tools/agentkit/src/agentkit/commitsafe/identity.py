"""Git identity verification against configured commit whitelists."""

from __future__ import annotations

from pathlib import Path

from .. import gitutil
from ..errors import IdentityError, WhitelistError
from ..repoconfig import load_repo_config
from .config import Config, load_config


def git_email(cwd: Path | None = None) -> str:
    return gitutil.config_value("user.email", cwd=cwd)


def checked_identity(cwd: Path | None = None) -> tuple[Config, str]:
    """Load the config and confirm the current git identity may commit.

    Checks repository config (.git/agentkit-commit.json) first:
      - If repo config exists and whitelist is enabled: verifies email is allowed.
      - If repo config exists and whitelist is disabled: permits email unconditionally.
      - If no repo config exists: falls back to global config (~/.config/git-commit-safe/config.yaml).
    """
    email = git_email(cwd=cwd)

    if not email:
        raise IdentityError(
            "no git email configured ('git config user.email' is empty).",
            fix='git config user.email "your@email.com"',
            what_to_report="git user.email is not configured. Please specify which email address to set.",
            details=["Ask the user which address to use; do not invent one."],
        )

    repo_cfg = load_repo_config(cwd=cwd)
    if repo_cfg is not None:
        if not repo_cfg.whitelist.allows(email):
            raise WhitelistError(
                f"git email '{email}' is not in repository whitelist: {repo_cfg.path}",
                what_to_report=(
                    f"Current git email ('{email}') is not in this repository's commit whitelist. "
                    "The user must decide whether to update the whitelist."
                ),
                details=[
                    f"Allowed: {', '.join(repo_cfg.whitelist.allowed_emails)}",
                    f"Whitelist file: {repo_cfg.path}",
                ],
            )
        cfg = Config(
            path=repo_cfg.path,
            allowed_emails=repo_cfg.whitelist.allowed_emails,
            timezone=repo_cfg.timeline.timezone,
            start=repo_cfg.timeline.start,
            end=repo_cfg.timeline.end,
            min_gap_seconds=repo_cfg.timeline.min_gap_seconds,
            whitelist_enabled=repo_cfg.whitelist.enabled,
        )
        return cfg, email

    config = load_config()
    if not config.allows(email):
        raise WhitelistError(
            f"git email '{email}' is not in the whitelist: {config.path}",
            what_to_report=(
                f"Current git email ('{email}') is not in the global commit whitelist. "
                "The user must decide whether to update the whitelist."
            ),
            details=[
                f"Allowed: {', '.join(config.allowed_emails)}",
                f"Whitelist file: {config.path}",
            ],
        )

    return config, email
