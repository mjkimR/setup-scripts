"""`agentkit handoff` — delegate a job to the Antigravity CLI."""

from __future__ import annotations

import click

from ..agy import AgyClient
from ..agy.client import DEFAULT_EFFORT, DEFAULT_TIMEOUT
from ..handoff import TASKS, get_task, run_handoff
from ..handoff.runner import DEFAULT_MAX_UNITS
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
    if safe is None:
        repo_cfg = load_repo_config()
        is_safe = repo_cfg.timeline.enabled if repo_cfg is not None else False
    else:
        is_safe = safe

    task = get_task("commit-safe" if is_safe else "commit")
    result = run_handoff(
        task,
        client=AgyClient(effort=effort, timeout=timeout),
        max_units=max_units,
        verbose=verbose,
    )
    ctx.exit(int(result.exit_code))


@handoff.command("tasks")
def list_tasks() -> None:
    """List the jobs that can be handed off."""
    for name, task in TASKS.items():
        mode = "one agy call per atomic unit" if task.per_unit else "a single agy call"
        click.echo(f"{name:12} {task.skill:16} {mode}")
