"""Continue work from a handoff document via another agent CLI.

Unlike the commit tasks, a work handoff has no universal, git-verifiable
outcome — whether the work actually happened is judged by the calling agent
against the document's own verification steps. This module's job ends at
running the receiver faithfully and reporting what it said.

The receiver's narration is always printed: for open-ended work it IS the
deliverable (what was done, what remains), not noise to suppress.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .. import gitutil
from ..agy import AgyClient
from ..codex import CodexClient
from ..errors import (
    Actor,
    Advisory,
    AgyNotInstalledError,
    CodexNotInstalledError,
    ConfigError,
    ErrorCode,
    ExitCode,
    NotAGitRepoError,
    Retry,
)
from ..ui import Reporter

TARGETS = ("agy", "codex")
DEFAULT_TARGET = "agy"
DEFAULT_WORK_EFFORT = "high"
# Open-ended work runs far longer than a commit pass. The timeout is a hard
# lifetime cap — the receiver is killed (codex) or wound down (agy) when it
# expires — so it errs long rather than cutting work off mid-flight.
DEFAULT_WORK_TIMEOUT = "30m"


@dataclass
class WorkResult:
    exit_code: ExitCode
    output: str = ""


def result_path(doc: Path) -> Path:
    """Where the receiver reports back: next to the document, immutable original."""
    return doc.with_name(doc.stem + "-result.md")


def build_prompt(doc: Path, workdir: Path) -> str:
    return (
        f"Read the handoff document at {doc} and continue the work it describes.\n\n"
        f"Work in {workdir}. Follow the document's next steps in order, respect its\n"
        "decisions, and do not redo anything it lists as done. Treat the document\n"
        "itself as read-only.\n\n"
        f"When finished, write a completion report to {result_path(doc)} with four\n"
        "sections: what you completed, what remains, deviations from the document's\n"
        "plan, and the outcome of the document's verification commands.\n\n"
        "Reply exactly once, after the completion report is written, with the same\n"
        "summary. Never reply with a progress update — replying ends this session,\n"
        "and a run that ends before the report exists counts as not done."
    )


def _resolve_doc(doc: Path) -> Path:
    doc = doc.expanduser().resolve()
    if not doc.is_file():
        raise ConfigError(
            f"handoff document not found: {doc}",
            what_to_report="The handoff document does not exist; nothing was executed.",
            details=["Pass --doc with the path printed when the document was written."],
        )
    return doc


def _workdir() -> Path:
    try:
        return gitutil.repo_root()
    except NotAGitRepoError:
        return Path.cwd()


def pickup_prompt(doc: Path) -> str:
    """The paste-ready prompt for running a handoff in an interactive session."""
    return build_prompt(_resolve_doc(doc), _workdir())


def run_work(
    doc: Path,
    *,
    to: str = DEFAULT_TARGET,
    effort: str | None = DEFAULT_WORK_EFFORT,
    model: str | None = None,
    timeout: str | None = None,
    reporter: Reporter | None = None,
    client: AgyClient | CodexClient | None = None,
) -> WorkResult:
    out = reporter or Reporter("handoff-work")
    doc = _resolve_doc(doc)
    workdir = _workdir()

    if client is None:
        client = _build_client(to, effort=effort, model=model, timeout=timeout)
    _check_available(client)

    out.note(
        f"Handing {doc.name} to {to} "
        f"(effort={client.effort or 'receiver default'}, model={client.model or 'receiver default'}, "
        f"timeout={client.timeout})…"
    )

    if isinstance(client, CodexClient):
        return _run_codex(client, doc, workdir, out)
    return _run_agy(client, doc, workdir, out)


def _build_client(
    to: str, *, effort: str | None, model: str | None, timeout: str | None
) -> AgyClient | CodexClient:
    if to == "agy":
        client = AgyClient(effort=effort, model=model)
    elif to == "codex":
        client = CodexClient(effort=effort, model=model)
    else:
        raise ConfigError(
            f"unknown handoff target: {to!r}.",
            details=[f"Valid targets: {', '.join(TARGETS)}."],
        )
    client.timeout = timeout if timeout is not None else DEFAULT_WORK_TIMEOUT
    return client


def _check_available(client: AgyClient | CodexClient) -> None:
    if client.available:
        return
    if isinstance(client, CodexClient):
        raise CodexNotInstalledError(
            f"{client.executable} not found on PATH.",
            what_to_report="The Codex CLI is not installed; cannot run the work handoff.",
            details=[f"Install the Codex CLI and make sure `{client.executable}` is on PATH."],
        )
    raise AgyNotInstalledError(
        f"{client.executable} not found on PATH.",
        what_to_report="Antigravity CLI (agy) is not installed; cannot run the work handoff.",
        details=[f"Install the Antigravity CLI and make sure `{client.executable}` is on PATH."],
    )


def _advise(out: Reporter, advisory: Advisory, message: str) -> None:
    for line in advisory.lines(message):
        out.warn(line)


def _finish(receiver: str, doc: Path, out: Reporter, output: str) -> WorkResult:
    """The completion report is the outcome signal — no report, no OK.

    Same principle as the commit runner's HEAD check: trust what exists on
    disk, never the receiver's exit status or its parting words.
    """
    report = result_path(doc)
    if report.is_file():
        out.note(f"Completion report: {report}")
        out.note(f"{receiver} finished. Verify the outcome against the handoff document's checks.")
        return WorkResult(ExitCode.OK, output)

    _advise(
        out,
        Advisory(
            code=ErrorCode.NO_COMPLETION_REPORT,
            actor=Actor.NONE,
            retry=Retry.UNSAFE,
            what_to_report=(
                f"{receiver} returned without writing the completion report — the only "
                "completion signal for open-ended work — so treat the run as unfinished. "
                "Check the working tree against the handoff document before deciding anything."
            ),
            details=("A receiver that replies early ends its session; partial work may exist.",),
        ),
        "no completion report was written.",
    )
    return WorkResult(ExitCode.INCOMPLETE, output)


def _run_codex(client: CodexClient, doc: Path, workdir: Path, out: Reporter) -> WorkResult:
    run = client.run(build_prompt(doc, workdir), workdir=workdir)
    out.block("codex output", run.output)

    if run.timed_out:
        _advise(
            out,
            Advisory(
                code=ErrorCode.CODEX_TIMEOUT,
                actor=Actor.NONE,
                retry=Retry.UNSAFE,
                what_to_report=(
                    "codex hit the timeout mid-work; some of the work may exist. "
                    "Check the working tree against the handoff document before deciding anything."
                ),
                details=("A larger --timeout, or a smaller handoff, is the usual answer.",),
            ),
            f"codex timed out after {client.timeout}.",
        )
        return WorkResult(ExitCode.INCOMPLETE, run.output)

    if run.exit_code != 0:
        _advise(
            out,
            Advisory(
                code=ErrorCode.CODEX_FAILED,
                actor=Actor.NONE,
                retry=Retry.UNSAFE,
                what_to_report=(
                    f"codex exited with code {run.exit_code}. Partial work may exist; "
                    "check the working tree against the handoff document."
                ),
                details=("See the codex output above for the cause.",),
            ),
            f"codex exited with code {run.exit_code}.",
        )
        return WorkResult(ExitCode.FAILED, run.output)

    return _finish("codex", doc, out, run.output)


def _run_agy(client: AgyClient, doc: Path, workdir: Path, out: Reporter) -> WorkResult:
    run = client.run(build_prompt(doc, workdir), add_dir=workdir)
    out.block("agy output", run.output)

    # agy's exit code carries no signal (see agy/client.py); read the markers.
    if run.hit_permission_wall:
        denied = tuple(f"Denied: {cmd}" for cmd in run.denied_commands() or ["(agy's log named none)"])
        _advise(
            out,
            Advisory(
                code=ErrorCode.AGY_PERMISSION_DENIED,
                actor=Actor.USER,
                retry=Retry.AFTER_FIX,
                fix="agentkit agy grant",
                what_to_report=(
                    "agy auto-denied commands it needed, so the work is likely incomplete. "
                    "Open-ended work may need grants beyond the commit set — ask the user."
                ),
                details=(*denied, "Partial work may exist; check against the handoff document."),
            ),
            "agy hit a permission wall.",
        )
        return WorkResult(ExitCode.INCOMPLETE, run.output)
    if run.looks_quota_limited:
        _advise(
            out,
            Advisory(
                code=ErrorCode.QUOTA_EXHAUSTED,
                actor=Actor.NONE,
                retry=Retry.UNSAFE,
                retry_after="the Antigravity rolling quota window resets (up to 5h)",
                what_to_report="Antigravity quota is exhausted; the work handoff did not complete.",
                details=("Partial work may exist; check against the handoff document.",),
            ),
            "agy reported a usage limit.",
        )
        return WorkResult(ExitCode.INCOMPLETE, run.output)
    if run.looks_unauthenticated:
        _advise(
            out,
            Advisory(
                code=ErrorCode.AGY_UNAUTHENTICATED,
                actor=Actor.USER,
                retry=Retry.AFTER_FIX,
                what_to_report="agy authentication appears to have expired; please refresh the login.",
                details=("Run `agy` interactively once to refresh the login.",),
            ),
            "looks like an authentication failure.",
        )
        return WorkResult(ExitCode.FAILED, run.output)
    if run.looks_timed_out:
        _advise(
            out,
            Advisory(
                code=ErrorCode.AGY_TIMEOUT,
                actor=Actor.NONE,
                retry=Retry.UNSAFE,
                what_to_report=(
                    "agy timed out mid-work; some of the work may exist. "
                    "Check the working tree against the handoff document before deciding anything."
                ),
                details=("A larger --timeout, or a smaller handoff, is the usual answer.",),
            ),
            "agy timed out before finishing.",
        )
        return WorkResult(ExitCode.INCOMPLETE, run.output)

    return _finish("agy", doc, out, run.output)
