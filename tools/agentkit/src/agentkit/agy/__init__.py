"""Adapter for the Antigravity CLI (`agy`).

Everything this package knows about `agy`'s quirks lives here, so the handoff
runner can stay a plain "ask, then check what actually happened" loop.
"""

from .client import AgyClient, AgyRun
from .permissions import (
    CONFIG_PATH,
    SETTINGS_PATH,
    granted_rules,
    grant,
    missing_rules,
)

__all__ = [
    "AgyClient",
    "AgyRun",
    "CONFIG_PATH",
    "SETTINGS_PATH",
    "granted_rules",
    "grant",
    "missing_rules",
]
