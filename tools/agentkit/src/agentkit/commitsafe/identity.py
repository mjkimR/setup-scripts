"""The whitelist check.

Kept separate from the config that holds the list, because this is the part with
teeth: it is what refuses to commit, and both the skill and the safe handoff
route through it.
"""

from __future__ import annotations

from pathlib import Path

from .. import gitutil
from ..errors import IdentityError
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
            'Set one: git config user.email "your@email.com"',
        )

    repo_cfg = load_repo_config(cwd=cwd)
    if repo_cfg is not None:
        if not repo_cfg.whitelist.allows(email):
            raise IdentityError(
                f"git email '{email}' is not in repository whitelist: {repo_cfg.path}",
                f"Allowed: {', '.join(repo_cfg.whitelist.allowed_emails)}",
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
        raise IdentityError(
            f"git email '{email}' is not in the whitelist: {config.path}",
            f"Allowed: {', '.join(config.allowed_emails)}",
        )

    return config, email
