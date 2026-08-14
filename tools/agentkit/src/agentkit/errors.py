"""Exit codes and the exception types that carry them.

The numbers are a contract: skills tell the calling agent what each one means,
so they are chosen for the caller's benefit rather than for internal tidiness.

    0   what was asked for happened
    1   nothing happened — no commit was created, or the identity was rejected
    2   something happened but the job is unfinished — commits were made with
        files left over, a loop guard tripped, or the config is unusable
    64  the command line itself was wrong (sysexits.h EX_USAGE)
"""

from __future__ import annotations

from enum import IntEnum


class ExitCode(IntEnum):
    OK = 0
    FAILED = 1
    INCOMPLETE = 2
    USAGE = 64


class AgentkitError(Exception):
    """An expected failure with a message meant for a human or an agent."""

    exit_code = ExitCode.FAILED

    def __init__(self, message: str, *hints: str) -> None:
        super().__init__(message)
        self.hints = hints


class ConfigError(AgentkitError):
    """Configuration is missing or unusable.

    Deliberately code 2, not 1: skills distinguish "you are not allowed to
    commit" (1) from "nothing is set up yet" (2), and that split predates this
    package.
    """

    exit_code = ExitCode.INCOMPLETE


class IdentityError(AgentkitError):
    """The current git identity is not allowed to commit here."""

    exit_code = ExitCode.FAILED


class PreflightError(AgentkitError):
    """The environment cannot support the requested work."""

    exit_code = ExitCode.FAILED
