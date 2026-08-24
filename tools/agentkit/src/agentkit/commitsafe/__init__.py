"""Identity whitelisting and commit timestamp control."""

from .config import Config, config_path, load_config, write_default_config
from .guards import check as check_guards
from .guards import load_guards, scan_staged
from .identity import checked_identity, git_email
from .timeline import Stamp, resolve, state_path

__all__ = [
    "Config",
    "Stamp",
    "check_guards",
    "checked_identity",
    "config_path",
    "git_email",
    "load_config",
    "load_guards",
    "resolve",
    "scan_staged",
    "state_path",
    "write_default_config",
]
