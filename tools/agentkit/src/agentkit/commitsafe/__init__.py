"""Identity whitelisting and commit timestamp control."""

from .config import Config, config_path, load_config, write_default_config
from .identity import checked_identity, git_email
from .timeline import Stamp, resolve, state_path

__all__ = [
    "Config",
    "Stamp",
    "checked_identity",
    "config_path",
    "git_email",
    "load_config",
    "resolve",
    "state_path",
    "write_default_config",
]
