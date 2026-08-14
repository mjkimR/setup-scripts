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
from ..errors import ConfigError, ExitCode, PreflightError
from ..repoconfig import load_repo_config, repo_config_path
from ..ui import Reporter
from .tasks import HandoffTask

DEFAULT_MAX_UNITS = 10


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
    prompt = task.prompt(root)

    while True:
        result.units += 1
        if task.per_unit and result.units > max_units:
            out.error(f"stopped after {max_units} units with changes still pending.")
            out.warn("Raise --max-units if the split is legitimately this large.")
            result.remaining = gitutil.pending(cwd=root)
            out.detail(result.remaining, stream=sys.stderr)
            result.exit_code = ExitCode.INCOMPLETE
            return result

        # Resolving the environment can fail — a rejected identity, a missing
        # config — and doing it here means that failure costs no quota.
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
            result.exit_code = ExitCode.FAILED
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
        out.note("WARNING: uncommitted changes remain:")
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
        raise PreflightError(
            f"{client.executable} not found on PATH.",
            "Install the Antigravity CLI first.",
        )

    root = repo or gitutil.repo_root()

    # Refuse to start commit handoff if repository is not onboarded
    if task.name in ("commit", "commit-safe"):
        repo_cfg = load_repo_config(cwd=root)
        if repo_cfg is None:
            raise ConfigError(
                f"repository is not onboarded: {repo_config_path(cwd=root)} not found.",
                "Run `agentkit commit onboard` to initialize configuration with auto-detected settings.",
                "Or ask the user for preferences: whitelist, timeline, language (ko/en), style.",
            )

    # Refuse to start without the grants rather than discovering it after a
    # wasted agy round trip. Headless agy soft-denies and reports success, so a
    # missing grant otherwise looks like "the model decided not to commit".
    missing = missing_rules(task.grants)
    if missing:
        raise PreflightError(
            "agy is missing required permission grants: " + ", ".join(missing),
            "Headless agy cannot prompt, so it would silently commit nothing.",
            "Fix: agentkit agy grant",
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

    if run.hit_permission_wall:
        out.warn("Cause: a command was auto-denied for lack of permission:")
        out.detail(run.denied_commands() or ["(agy's log named none)"], stream=sys.stderr)
        out.warn("Fix:   agentkit agy grant")
    elif run.looks_unauthenticated:
        out.warn("Cause: looks like an authentication failure.")
        out.warn("Fix:   run `agy` interactively once to refresh the login.")
    else:
        out.warn("See the agy output above for the cause.")

    if result.commits:
        out.warn(f"{len(result.commits)} commit(s) were already created and are left in place.")
    else:
        out.warn("The working tree was left untouched.")
    out.warn("No retry was attempted.")
