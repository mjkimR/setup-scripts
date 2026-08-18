"""`agentkit handoff` — delegate a job to another agent CLI."""

from __future__ import annotations

from pathlib import Path

import click

from ..agy import AgyClient
from ..agy.client import DEFAULT_EFFORT, DEFAULT_TIMEOUT
from ..errors import ConfigError
from ..handoff import TASKS, get_task, run_handoff
from ..handoff.runner import DEFAULT_MAX_UNITS
from ..handoff.work import (
    DEFAULT_TARGET,
    DEFAULT_WORK_EFFORT,
    DEFAULT_WORK_TIMEOUT,
    TARGETS,
    pickup_prompt,
    run_work,
)
from ..repoconfig import load_repo_config


@click.group()
def handoff() -> None:
    """Hand a job to `agy` and verify the outcome from git."""


@handoff.command("commit")
@click.option(
    "--safe/--plain",
    "safe",
    default=None,
    help="Explicitly enforce or disable timeline/whitelist safe mode. Defaults to repo config if omitted.",
)
@click.option(
    "--effort",
    default=DEFAULT_EFFORT,
    envvar="AGENTKIT_AGY_EFFORT",
    show_default=True,
    help="Reasoning effort to ask agy for: low, medium or high.",
)
@click.option(
    "--timeout",
    default=DEFAULT_TIMEOUT,
    envvar="AGENTKIT_AGY_TIMEOUT",
    show_default=True,
    help="Go duration passed to agy's --print-timeout.",
)
@click.option(
    "--max-units",
    default=DEFAULT_MAX_UNITS,
    envvar="AGENTKIT_MAX_UNITS",
    show_default=True,
    help="Loop guard for --safe; ignored otherwise.",
)
@click.option(
    "--verbose",
    is_flag=True,
    envvar="AGENTKIT_VERBOSE",
    help="Also print agy's own narration, which is dropped on success.",
)
@click.pass_context
def commit(
    ctx: click.Context,
    safe: bool | None,
    effort: str,
    timeout: str,
    max_units: int,
    verbose: bool,
) -> None:
    """Delegate committing the working tree.

    Exit codes: 0 committed (or nothing to commit), 1 no commit was created,
    2 commits were made but changes remain.
    """
    repo_cfg = load_repo_config()
    timeline_on = repo_cfg is not None and repo_cfg.timeline.enabled
    is_safe = timeline_on if safe is None else safe

    # An explicit --safe on a timeline-disabled repo would run the safe task
    # with an empty timestamp env while its prompt claims the dates are set —
    # every commit would silently land on the system clock.
    if safe and repo_cfg is not None and not repo_cfg.timeline.enabled:
        raise ConfigError(
            "--safe was requested, but this repository's timeline is disabled, so no timestamps would be injected.",
            fix="agentkit commit config --set timeline.enabled=true",
            what_to_report=(
                "Safe mode was requested but the repository timeline is disabled; commits would use the "
                "system clock. The user must choose: enable the timeline, or rerun without --safe."
            ),
            details=["Enable it with the fix command, or drop --safe to use plain mode deliberately."],
        )

    task = get_task("commit-safe" if is_safe else "commit")
    result = run_handoff(
        task,
        client=AgyClient(effort=effort, timeout=timeout),
        max_units=max_units,
        verbose=verbose,
    )
    ctx.exit(int(result.exit_code))


@handoff.command("work")
@click.option(
    "--to",
    type=click.Choice(TARGETS),
    default=DEFAULT_TARGET,
    show_default=True,
    help="Which agent CLI continues the work.",
)
@click.option(
    "--doc",
    required=True,
    type=click.Path(exists=False, dir_okay=False, path_type=Path),
    help="The handoff document the receiver picks up.",
)
@click.option(
    "--effort",
    default=DEFAULT_WORK_EFFORT,
    show_default=True,
    help="Reasoning effort for the receiver: low, medium or high. 'default' leaves it to the receiver's own config.",
)
@click.option("--model", default=None, help="Model override; omitted, the receiver's own configuration decides.")
@click.option(
    "--timeout",
    default=None,
    help=(
        "Hard lifetime cap for the receiver — it is cut off mid-work when this expires "
        f"(e.g. 45m, 1h). [default: {DEFAULT_WORK_TIMEOUT}]"
    ),
)
@click.pass_context
def work(
    ctx: click.Context,
    to: str,
    doc: Path,
    effort: str,
    model: str | None,
    timeout: str | None,
) -> None:
    """Have another agent CLI continue the work a handoff document describes.

    This runs the receiver and reports what it said; whether the work actually
    happened is yours to verify against the document's own checks. Exit codes:
    0 the receiver finished, 1 it failed outright, 2 it stopped part-way.
    """
    result = run_work(
        doc,
        to=to,
        effort=None if effort == "default" else effort,
        model=model,
        timeout=timeout,
    )
    ctx.exit(int(result.exit_code))


@handoff.command("prompt")
@click.option(
    "--doc",
    required=True,
    type=click.Path(exists=False, dir_okay=False, path_type=Path),
    help="The handoff document the receiver picks up.",
)
def prompt_cmd(doc: Path) -> None:
    """Print the paste-ready pickup prompt instead of executing.

    For handoffs too long or interactive for a headless `handoff work` run:
    paste this into an agy/codex/claude session yourself. It is the same prompt
    `handoff work` uses, including the instruction to write a completion report
    next to the document — so the outcome lands in a file either way.
    """
    click.echo(pickup_prompt(doc))


@handoff.command("tasks")
def list_tasks() -> None:
    """List the jobs that can be handed off."""
    for name, task in TASKS.items():
        mode = "one agy call per atomic unit" if task.per_unit else "a single agy call"
        click.echo(f"{name:12} {task.skill:16} {mode}")
