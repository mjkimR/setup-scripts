"""Exit codes, action modes, and advisory structures for agentkit."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntEnum


class ExitCode(IntEnum):
    OK = 0
    FAILED = 1
    INCOMPLETE = 2
    USAGE = 64


class Actor(str, Enum):
    """Who takes the next step."""

    TOOL = "TOOL"  # the agent itself, by running `fix` verbatim
    USER = "USER"  # a human — a decision, a credential, an install
    DEVELOPER = "DEVELOPER"  # the agent, but editing agentkit or a skill rather than running it
    NONE = "NONE"  # nobody, at least not now


class Retry(str, Enum):
    """Whether running the same command again is safe."""

    SAFE = "SAFE"  # yes, unchanged — the obstacle is time, not state
    AFTER_FIX = "AFTER_FIX"  # only once `fix` has been applied
    UNSAFE = "UNSAFE"  # no — work may be half-done, and a retry would duplicate it


class ActionMode(str, Enum):
    """Directive for the calling agent, derived by Advisory.mode."""

    AUTO = "AUTO"  # Run the fix command, retry once
    INTERACTION = "INTERACTION"  # Ask the user for confirmation/input before proceeding
    DEFER = "DEFER"  # Nothing to fix — wait, then retry
    BLOCKED = "BLOCKED"  # A guardrail refused; report it, never route around it
    HALT = "HALT"  # Do not retry or modify code; report status and stop
    MAINTENANCE = "MAINTENANCE"  # Tool or skill code defect; fix in this session, then verify & retry


class ErrorCode(str, Enum):
    """Machine-readable and self-describing error identifiers."""

    GENERAL_ERROR = "GENERAL_ERROR"
    PREFLIGHT_FAILED = "PREFLIGHT_FAILED"
    REPO_NOT_ONBOARDED = "REPO_NOT_ONBOARDED"
    CONFIG_INVALID = "CONFIG_INVALID"
    IDENTITY_REJECTED = "IDENTITY_REJECTED"
    NOT_A_GIT_REPO = "NOT_A_GIT_REPO"
    GIT_COMMAND_FAILED = "GIT_COMMAND_FAILED"
    GIT_LOCK_HELD = "GIT_LOCK_HELD"
    AGY_NOT_INSTALLED = "AGY_NOT_INSTALLED"
    AGY_PERMISSION_DENIED = "AGY_PERMISSION_DENIED"
    AGY_UNAUTHENTICATED = "AGY_UNAUTHENTICATED"
    AGY_TIMEOUT = "AGY_TIMEOUT"
    CODEX_NOT_INSTALLED = "CODEX_NOT_INSTALLED"
    CODEX_TIMEOUT = "CODEX_TIMEOUT"
    CODEX_FAILED = "CODEX_FAILED"
    NO_COMPLETION_REPORT = "NO_COMPLETION_REPORT"
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
    PARTIAL_COMMITS = "PARTIAL_COMMITS"
    NO_COMMITS_CREATED = "NO_COMMITS_CREATED"
    MAX_UNITS_EXCEEDED = "MAX_UNITS_EXCEEDED"
    SKILL_CONTRACT_MISMATCH = "SKILL_CONTRACT_MISMATCH"
    TOOL_INTERNAL_ERROR = "TOOL_INTERNAL_ERROR"


# Self-contained action messages displayed to calling agents for each mode.
_ACTION_TEXT: dict[ActionMode, str] = {
    ActionMode.AUTO: (
        "AUTO — Run the [FIX] command once, then retry the operation once.\n"
        "This is the only mode that authorizes a retry. Stop after it either way."
    ),
    ActionMode.INTERACTION: (
        "INTERACTION — Stop and ask the user. Do not retry, and do not\n"
        "improvise a way around this. [FIX], when present, is the command\n"
        "for once they agree."
    ),
    ActionMode.DEFER: (
        "DEFER — Nothing is broken and nothing here is yours to fix.\n"
        "Do not retry now. Report the cause and when it can be retried."
    ),
    ActionMode.BLOCKED: (
        "BLOCKED — A deliberate guardrail refused this. Report it and stop.\n"
        "Do not propose or apply a way around it; changing the rule is the\n"
        "user's decision, not a fix."
    ),
    ActionMode.HALT: (
        "HALT — Stop here. Do not retry, do not work around it, and do not\n"
        "finish the job by hand. Report what happened, including anything\n"
        "left half-done."
    ),
    ActionMode.MAINTENANCE: (
        "MAINTENANCE — agentkit or one of its skills is at fault here, not\n"
        "your input. Report it and stop; repairing the tool is a separate\n"
        "task the user starts. [TARGET] names the files, `./check.sh` verifies."
    ),
}

_CONTINUATION = " " * len("[ACTION] ")


@dataclass(frozen=True)
class Advisory:
    """Structured directive and metadata for the calling agent."""

    code: ErrorCode
    actor: Actor
    retry: Retry
    guardrail: bool = False
    retry_after: str | None = None
    fix: str | None = None
    what_to_report: str | None = None
    target_files: tuple[str, ...] = ()
    details: tuple[str, ...] = ()

    @property
    def mode(self) -> ActionMode:
        if self.guardrail:
            return ActionMode.BLOCKED
        if self.actor is Actor.DEVELOPER:
            return ActionMode.MAINTENANCE
        if self.retry is Retry.UNSAFE:
            # Half-done work outranks whoever could act: acting means retrying.
            return ActionMode.HALT
        if self.actor is Actor.TOOL:
            return ActionMode.AUTO
        if self.actor is Actor.USER:
            return ActionMode.INTERACTION
        return ActionMode.DEFER if self.retry is Retry.SAFE else ActionMode.HALT

    def lines(self, message: str | None = None) -> list[str]:
        """Render the advisory block as a list of lines."""
        rendered: list[str] = []
        if message is not None:
            rendered.append(f"[ERROR]  ({self.code.value}) {message}")

        head, *rest = _ACTION_TEXT[self.mode].splitlines()
        rendered.append(f"[ACTION] {head}")
        rendered.extend(f"{_CONTINUATION}{line}" for line in rest)
        if self.retry_after:
            rendered.append(f"[WHEN]   Not before: {self.retry_after}")

        if self.target_files:
            rendered.append(f"[TARGET] {', '.join(self.target_files)}")
        if self.fix:
            rendered.append(f"[FIX]    {self.fix}")
        if self.what_to_report:
            rendered.append(f"[REPORT] {self.what_to_report}")
        rendered.extend(f"[DETAIL] {detail}" for detail in self.details)
        return rendered


class AgentkitError(Exception):
    """Base error carrying structured guidance for humans and AI agents."""

    exit_code: ExitCode = ExitCode.FAILED
    code: ErrorCode = ErrorCode.GENERAL_ERROR
    actor: Actor = Actor.NONE
    retry: Retry = Retry.UNSAFE
    guardrail: bool = False

    def __init__(
        self,
        message: str,
        *hints: str,
        code: ErrorCode | None = None,
        actor: Actor | None = None,
        retry: Retry | None = None,
        guardrail: bool | None = None,
        retry_after: str | None = None,
        fix: str | None = None,
        what_to_report: str | None = None,
        target_files: list[str] | None = None,
        details: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code
        if actor is not None:
            self.actor = actor
        if retry is not None:
            self.retry = retry
        if guardrail is not None:
            self.guardrail = guardrail
        self.retry_after = retry_after
        self.fix = fix
        self.what_to_report = what_to_report
        self.target_files = list(target_files) if target_files else []
        self.details = list(details) if details else []
        self.hints = hints
        if hints and not self.details:
            self.details = list(hints)

    @property
    def advisory(self) -> Advisory:
        return Advisory(
            code=self.code,
            actor=self.actor,
            retry=self.retry,
            guardrail=self.guardrail,
            retry_after=self.retry_after,
            fix=self.fix,
            what_to_report=self.what_to_report,
            target_files=tuple(self.target_files),
            details=tuple(self.details),
        )

    @property
    def mode(self) -> ActionMode:
        return self.advisory.mode


class ConfigError(AgentkitError):
    """Configuration is missing or unusable."""

    exit_code = ExitCode.INCOMPLETE
    code = ErrorCode.CONFIG_INVALID
    actor = Actor.USER
    retry = Retry.AFTER_FIX


class NotOnboardedError(ConfigError):
    """Repository commit configuration has not been initialized."""

    code = ErrorCode.REPO_NOT_ONBOARDED


class IdentityError(AgentkitError):
    """The current git identity cannot be used to commit here."""

    exit_code = ExitCode.FAILED
    code = ErrorCode.IDENTITY_REJECTED
    actor = Actor.USER
    retry = Retry.AFTER_FIX


class WhitelistError(IdentityError):
    """The git identity is rejected by the whitelist guardrail."""

    guardrail = True
    retry = Retry.UNSAFE


class PreflightError(AgentkitError):
    """The environment cannot support the requested work."""

    exit_code = ExitCode.FAILED
    code = ErrorCode.PREFLIGHT_FAILED
    actor = Actor.NONE
    retry = Retry.UNSAFE


class NotAGitRepoError(PreflightError):
    """The working directory is not inside a git repository."""

    code = ErrorCode.NOT_A_GIT_REPO
    actor = Actor.USER
    retry = Retry.AFTER_FIX


class GitCommandError(PreflightError):
    """A git invocation failed for a reason we do not recognise."""

    code = ErrorCode.GIT_COMMAND_FAILED


class GitLockError(GitCommandError):
    """Another process holds the index lock — a queue, not a fault."""

    code = ErrorCode.GIT_LOCK_HELD
    actor = Actor.NONE
    retry = Retry.SAFE


class AgyNotInstalledError(PreflightError):
    """The Antigravity CLI is not on PATH."""

    code = ErrorCode.AGY_NOT_INSTALLED
    actor = Actor.USER
    retry = Retry.AFTER_FIX


class CodexNotInstalledError(PreflightError):
    """The Codex CLI is not available."""

    code = ErrorCode.CODEX_NOT_INSTALLED


class AgyPermissionError(PreflightError):
    """Antigravity CLI is missing required tool grants."""

    code = ErrorCode.AGY_PERMISSION_DENIED
    actor = Actor.TOOL
    retry = Retry.AFTER_FIX


class AgyAuthError(PreflightError):
    """Antigravity CLI credentials are missing or expired."""

    code = ErrorCode.AGY_UNAUTHENTICATED
    actor = Actor.USER
    retry = Retry.AFTER_FIX


class QuotaError(PreflightError):
    """A rolling usage limit is spent. Nothing is broken; the clock is the fix."""

    code = ErrorCode.QUOTA_EXHAUSTED
    actor = Actor.NONE
    retry = Retry.SAFE


class MaintenanceError(AgentkitError):
    """Tool or skill source code needs modification."""

    exit_code = ExitCode.FAILED
    code = ErrorCode.TOOL_INTERNAL_ERROR
    actor = Actor.DEVELOPER
    retry = Retry.AFTER_FIX


class SkillContractError(MaintenanceError):
    """Skill definition, arguments, or prompt contract mismatch."""

    code = ErrorCode.SKILL_CONTRACT_MISMATCH
