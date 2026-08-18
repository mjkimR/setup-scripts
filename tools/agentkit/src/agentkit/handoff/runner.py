"""Ask another agent to do the work, then check whether it actually happened.

Two rules shape everything here:

*Trust the outcome, never the exit code.* Headless `agy` reports success with an
empty response when every tool call was denied, so the only trustworthy result
is whether HEAD moved between a snapshot taken before and after.

*Never retry.* A failed handoff may have committed part of the work, and a blind
retry risks duplicate or polluted commits. The runner stops, leaves what exists
in place, and reports. Deciding whether to retry belongs to the user.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

from .. import gitutil
from ..agy import AgyClient, AgyRun, missing_rules
from ..commitsafe import checked_identity
from ..errors import (
    Actor,
    Advisory,
    AgyNotInstalledError,
    AgyPermissionError,
    ErrorCode,
    ExitCode,
    NotOnboardedError,
    Retry,
)
from ..repoconfig import load_repo_config, repo_config_path
from ..ui import Reporter
from .tasks import HandoffTask

DEFAULT_MAX_UNITS = 10


def _advise(out: Reporter, advisory: Advisory, message: str | None = None) -> None:
    """Print an advisory block for operations that report instead of raising."""
    for line in advisory.lines(message):
        out.warn(line)


@dataclass
class HandoffResult:
    exit_code: ExitCode
    units: int = 0
    commits: list[str] = field(default_factory=list)
    remaining: list[str] = field(default_factory=list)


def run_handoff(
    task: HandoffTask,
    *,
    client: AgyClient,
    reporter: Reporter | None = None,
    repo: Path | None = None,
    max_units: int = DEFAULT_MAX_UNITS,
    verbose: bool = False,
    hints: tuple[str, ...] = (),
    tests: str | None = None,
) -> HandoffResult:
    out = reporter or Reporter(task.tag)
    root = _preflight(task, client=client, repo=repo)

    pending = gitutil.pending(cwd=root)
    if not pending:
        out.note("Working tree is clean — nothing to commit. Skipping handoff.")
        return HandoffResult(ExitCode.OK)

    if task.per_unit:
        out.note(f"Delegating {len(pending)} pending file(s) to agy, one atomic unit per call…")
    else:
        out.note(
            f"Delegating {len(pending)} pending file(s) to agy (effort={client.effort}, timeout={client.timeout})…"
        )

    result = HandoffResult(ExitCode.OK)
    prompt = task.prompt(root, hints=hints, tests=tests)

    while True:
        result.units += 1
        if task.per_unit and result.units > max_units:
            result.remaining = gitutil.pending(cwd=root)
            _advise(
                out,
                Advisory(
                    code=ErrorCode.MAX_UNITS_EXCEEDED,
                    actor=Actor.USER,
                    retry=Retry.UNSAFE,
                    what_to_report=(
                        f"Loop guard halted handoff at {max_units} units. "
                        f"{len(result.commits)} commit(s) were created; the files below remain uncommitted."
                    ),
                    details=("Raise --max-units only if the split is legitimately this large.",),
                ),
                f"stopped after {max_units} units with changes still pending.",
            )
            out.detail(result.remaining, stream=sys.stderr)
            result.exit_code = ExitCode.INCOMPLETE
            return result

        # Resolve environment variables before executing handoff.
        env, label = ({}, "")
        if task.env_factory is not None:
            env, label = task.env_factory()

        if task.per_unit:
            suffix = f" ({label})" if label else ""
            out.note(f"Unit {result.units} — delegating to agy{suffix}…")

        before = gitutil.head_sha(cwd=root)
        run = client.run(prompt, add_dir=root, env=env)
        after = gitutil.head_sha(cwd=root)

        if verbose:
            out.block("agy output", run.output)

        if before == after:
            _report_nothing_happened(out, run, result, task, verbose=verbose)
            # FAILED promises "nothing was committed"; once earlier units have
            # committed, that number would invite a duplicate whole-handoff re-run.
            result.exit_code = ExitCode.INCOMPLETE if result.commits else ExitCode.FAILED
            return result

        rev_range = gitutil.commit_range(before, after)
        lines = gitutil.log(rev_range, task.log_format, date_format=task.date_format, cwd=root)
        result.commits.extend(lines)

        if task.per_unit:
            out.detail(lines)
        else:
            out.note(f"Created {gitutil.count(rev_range, cwd=root)} commit(s):")
            out.detail(lines)

        result.remaining = gitutil.pending(cwd=root)

        if not task.per_unit:
            break
        if not result.remaining:
            break

    if result.remaining:
        # A partial commit is an anomaly the caller has to act on, so the reason
        # agy gave for stopping short is worth the tokens here.
        if not verbose:
            out.block("agy output", run.output)
        _advise(
            out,
            Advisory(
                code=ErrorCode.PARTIAL_COMMITS,
                actor=Actor.NONE,
                retry=Retry.UNSAFE,
                what_to_report=(
                    f"{len(result.commits)} commit(s) were created, but the files below remain uncommitted."
                ),
            ),
            "uncommitted changes remain after the handoff.",
        )
        out.detail(result.remaining)
        result.exit_code = ExitCode.INCOMPLETE
        return result

    if task.per_unit:
        out.note(f"Created {len(result.commits)} commit(s) across {result.units} unit(s). Working tree is clean.")
    else:
        out.note("Working tree is clean.")
    return result


def _preflight(task: HandoffTask, *, client: AgyClient, repo: Path | None) -> Path:
    if not client.available:
        # No `fix`: installing the CLI is not a command this tool can hand the
        # agent to run. `fix` is a runnable command or nothing.
        raise AgyNotInstalledError(
            f"{client.executable} not found on PATH.",
            what_to_report="Antigravity CLI (agy) is not installed; cannot run handoff.",
            details=[f"Install the Antigravity CLI and make sure `{client.executable}` is on PATH."],
        )

    root = repo or gitutil.repo_root()

    # Refuse to start commit handoff if repository is not onboarded
    if task.name in ("commit", "commit-safe"):
        repo_cfg = load_repo_config(cwd=root)
        if repo_cfg is None:
            raise NotOnboardedError(
                f"repository is not onboarded: {repo_config_path(cwd=root)} not found.",
                fix="agentkit commit onboard",
                what_to_report="Repository commit configuration is required. Proceed with onboarding using default settings?",
                details=[
                    "Run `agentkit commit onboard` to initialize configuration with auto-detected settings.",
                    "Or ask the user for preferences: whitelist, timeline, language (ko/en), style.",
                ],
            )
        # The whitelist is a guardrail of its own, not a timeline feature: it
        # must hold for the plain task too, or disabling the timeline would
        # silently disable identity checking with it.
        checked_identity(cwd=root)

    # Check required permission grants before invoking agy.
    missing = missing_rules(task.grants)
    if missing:
        raise AgyPermissionError(
            "agy is missing required permission grants: " + ", ".join(missing),
            fix="agentkit agy grant",
            what_to_report="agy execution permissions are missing; authorization is required.",
            details=[
                "Headless agy cannot prompt, so it would silently commit nothing.",
                f"Missing grants: {', '.join(missing)}",
            ],
        )

    return root


def _report_nothing_happened(
    out: Reporter,
    run: AgyRun,
    result: HandoffResult,
    task: HandoffTask,
    *,
    verbose: bool,
) -> None:
    if not verbose:
        out.block("agy output", run.output)

    where = f"unit {result.units}" if task.per_unit else "agy"
    out.error(f"{where} produced no commit — HEAD did not move.")

    if result.commits:
        left = f"{len(result.commits)} commit(s) were already created and are left in place."
    else:
        left = "The working tree was left untouched."

    # Determine retry safety based on whether prior units already committed.
    after_fix = Retry.UNSAFE if result.commits else Retry.AFTER_FIX
    wait_it_out = Retry.UNSAFE if result.commits else Retry.SAFE

    if run.hit_permission_wall:
        denied = tuple(f"Denied: {cmd}" for cmd in run.denied_commands() or ["(agy's log named none)"])
        cause = "a command was auto-denied for lack of permission."
        advisory = Advisory(
            code=ErrorCode.AGY_PERMISSION_DENIED,
            actor=Actor.TOOL,
            retry=after_fix,
            fix="agentkit agy grant",
            what_to_report="agy execution permission was denied; no commits were created.",
            details=(*denied, left, "No retry was attempted."),
        )
    elif run.looks_quota_limited:
        # Before the auth check: a spent-quota message routinely says "token".
        cause = "agy reported a usage limit."
        advisory = Advisory(
            code=ErrorCode.QUOTA_EXHAUSTED,
            actor=Actor.NONE,
            retry=wait_it_out,
            retry_after="the Antigravity rolling quota window resets (up to 5h)",
            what_to_report="Antigravity quota is exhausted; no commits were created. It will reset over time.",
            details=("Nothing is misconfigured — the limit is time-based.", left, "No retry was attempted."),
        )
    elif run.looks_unauthenticated:
        cause = "looks like an authentication failure."
        advisory = Advisory(
            code=ErrorCode.AGY_UNAUTHENTICATED,
            actor=Actor.USER,
            retry=after_fix,
            what_to_report="agy authentication appears to have expired; please refresh the login.",
            details=("Run `agy` interactively once to refresh the login.", left, "No retry was attempted."),
        )
    elif run.looks_timed_out:
        # Last of the recognizers: "timed out" is the phrase most likely to turn
        # up inside a message whose real cause is one of the ones above.
        cause = "agy timed out before it committed."
        advisory = Advisory(
            code=ErrorCode.AGY_TIMEOUT,
            actor=Actor.NONE,
            retry=wait_it_out,
            what_to_report="agy timed out before completing. If the changes are too large, split them and try again.",
            details=(
                "A larger --timeout, or a smaller change set, is the usual answer.",
                left,
                "No retry was attempted.",
            ),
        )
    else:
        cause = "agy gave no recognizable reason."
        advisory = Advisory(
            code=ErrorCode.NO_COMMITS_CREATED,
            actor=Actor.NONE,
            retry=Retry.UNSAFE,
            what_to_report="agy failed to create commits. See the agy output above for the cause.",
            details=("See the agy output above for the cause.", left, "No retry was attempted."),
        )

    _advise(out, advisory, cause)
