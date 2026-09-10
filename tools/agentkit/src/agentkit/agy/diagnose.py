"""Turn a no-outcome agy run into a cause line and an Advisory.

Shared by the handoff runners so the cause recognizers, their ordering, and
the advisory texts live in one place. The ordering is load-bearing:

- The permission wall goes first: it is the only cause with a positive marker.
- Quota before auth: a spent-quota message routinely says "token".
- Timeout last: "timed out" is the phrase most likely to turn up inside a
  message whose real cause is one of the ones above.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..errors import Actor, Advisory, ErrorCode, Retry
from .client import AgyRun


@dataclass(frozen=True)
class FailureTexts:
    """The task-specific halves of the shared failure advisories."""

    nothing_happened: str  # e.g. "no commits were created" / "no files were polished"
    timeout_cause: str
    timeout_report: str
    timeout_hint: str
    unknown_cause: str  # what to say when no recognizer matches...
    unknown: Advisory  # ...and the advisory that goes with it


_CHAIN = re.compile(r"\s*(?:\|\||&&|\||;)\s*")


def segments(cmd: str) -> list[str]:
    """The simple commands of a shell line: agy checks each one, so one denied segment denies the line."""
    return [part.strip() for part in _CHAIN.split(cmd) if part.strip()]


def outside_scope(denied: list[str], permitted: tuple[str, ...]) -> list[str]:
    """The denied commands the task's own prompt never authorizes.

    A pipeline or chain counts as out of scope when any of its segments is: seen
    live (2026-09-10), `git diff <file> | grep -E ...` was denied on the `grep`
    half although `git diff` itself is permitted."""

    def is_permitted(cmd: str) -> bool:
        return any(cmd == prefix or cmd.startswith(prefix + " ") for prefix in permitted)

    return [cmd for cmd in denied if not all(is_permitted(seg) for seg in segments(cmd))]


def diagnose_failure(
    run: AgyRun,
    *,
    permitted: tuple[str, ...],
    texts: FailureTexts,
    left: str,
    after_fix: Retry,
    wait_it_out: Retry,
    fix: str = "agentkit agy grant",
) -> tuple[str, Advisory]:
    """Name the cause of a run that produced nothing, and how to act on it.

    `left` states what the failed run leaves behind; `after_fix`/`wait_it_out`
    let a caller with earlier partial work downgrade the retryable causes to
    UNSAFE, since retrying would duplicate that work.
    """
    if run.hit_permission_wall:
        denied_commands = run.denied_commands()
        out_of_scope = outside_scope(denied_commands, permitted)
        if out_of_scope:
            # `agentkit agy grant` cannot help here: the denied command is one
            # this task never authorizes, so the prompt steered agy somewhere
            # the allow-list is *supposed* to block. Suggesting the grant fix
            # sends the user into a retry loop against the same wall.
            return (
                "agy reached for a command outside the task's permitted set.",
                Advisory(
                    code=ErrorCode.AGY_PERMISSION_DENIED,
                    actor=Actor.TOOL,
                    retry=Retry.UNSAFE,
                    what_to_report=(
                        "agy was denied a command this task never permits — granting more permissions is "
                        "not the fix. This is a bug in the handoff prompt; report it, including the "
                        "denied command below."
                    ),
                    details=(
                        *(f"Out of scope: {cmd}" for cmd in out_of_scope),
                        "A pipe or chain is denied as a whole when any segment is outside the set."
                        if any(len(segments(cmd)) > 1 for cmd in out_of_scope)
                        else "The prompt steered agy to this command; the allow-list is right to block it.",
                        *run.evidence(),
                        left,
                        "No retry was attempted.",
                    ),
                ),
            )
        denied = tuple(
            f"Denied: {cmd}"
            for cmd in denied_commands or ["(neither agy's log nor its conversation record named the command)"]
        )
        return (
            "a command was auto-denied for lack of permission.",
            Advisory(
                code=ErrorCode.AGY_PERMISSION_DENIED,
                actor=Actor.TOOL,
                retry=after_fix,
                fix=fix,
                what_to_report=f"agy execution permission was denied; {texts.nothing_happened}.",
                details=(*denied, *run.evidence(), left, "No retry was attempted."),
            ),
        )
    if run.looks_quota_limited:
        return (
            "agy reported a usage limit.",
            Advisory(
                code=ErrorCode.QUOTA_EXHAUSTED,
                actor=Actor.NONE,
                retry=wait_it_out,
                retry_after="the Antigravity rolling quota window resets (up to 5h)",
                what_to_report=f"Antigravity quota is exhausted; {texts.nothing_happened}. It will reset over time.",
                details=("Nothing is misconfigured — the limit is time-based.", left, "No retry was attempted."),
            ),
        )
    if run.looks_unauthenticated:
        return (
            "looks like an authentication failure.",
            Advisory(
                code=ErrorCode.AGY_UNAUTHENTICATED,
                actor=Actor.USER,
                retry=after_fix,
                what_to_report="agy authentication appears to have expired; please refresh the login.",
                details=("Run `agy` interactively once to refresh the login.", left, "No retry was attempted."),
            ),
        )
    if run.looks_timed_out:
        return (
            texts.timeout_cause,
            Advisory(
                code=ErrorCode.AGY_TIMEOUT,
                actor=Actor.NONE,
                retry=wait_it_out,
                what_to_report=texts.timeout_report,
                details=(texts.timeout_hint, left, "No retry was attempted."),
            ),
        )
    return (texts.unknown_cause, texts.unknown)
