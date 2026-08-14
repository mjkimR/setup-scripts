"""The whitelist check.

Kept separate from the config that holds the list, because this is the part with
teeth: it is what refuses to commit, and both the skill and the safe handoff
route through it.
"""

from __future__ import annotations

from typing import Tuple

from .. import gitutil
from ..errors import IdentityError
from .config import Config, load_config


def git_email() -> str:
    return gitutil.config_value("user.email")


def checked_identity() -> Tuple[Config, str]:
    """Load the config and confirm the current git identity may commit."""
    config = load_config()
    email = git_email()

    if not email:
        raise IdentityError(
            "no git email configured ('git config user.email' is empty).",
            'Set one: git config user.email "your@email.com"',
        )

    if not config.allows(email):
        raise IdentityError(
            f"git email '{email}' is not in the whitelist: {config.path}",
            f"Allowed: {', '.join(config.allowed_emails)}",
        )

    return config, email
