"""`agentkit agy` — inspect and extend the Antigravity CLI's allow-list."""

from __future__ import annotations

import click

from ..agy import SETTINGS_PATH, missing_rules
from ..agy import grant as grant_rules
from ..errors import ExitCode
from ..handoff.polish import POLISH_GRANTS
from ..handoff.tasks import TASKS

# What the handoff tasks collectively need; the default for check and grant.
# Aggregated from the task registry so a new task's declared grants become
# visible here without editing this file. (The polish runner is not a
# registry task; its grants ride along explicitly.)
HANDOFF_GRANTS: tuple[str, ...] = tuple(
    dict.fromkeys([rule for task in TASKS.values() for rule in task.grants] + list(POLISH_GRANTS))
)


@click.group()
def agy() -> None:
    """Manage what headless `agy` is allowed to run."""


@agy.command()
@click.pass_context
def check(ctx: click.Context) -> None:
    """Report which required grants are missing. Exits 1 if any are."""
    missing = missing_rules(HANDOFF_GRANTS)
    if not missing:
        click.echo("[OK] All grants required by the handoff tasks are present.")
        return

    click.echo("[ERROR] Missing grants:", err=True)
    for rule in missing:
        click.echo(f"  {rule}", err=True)
    click.echo("[INFO] Add them with: agentkit agy grant", err=True)
    ctx.exit(int(ExitCode.FAILED))


@agy.command()
@click.option("--yes", is_flag=True, help="Skip the confirmation prompt.")
@click.option(
    "--rule",
    "rules",
    multiple=True,
    help=(
        "Grant this rule instead of the handoff set (repeatable), e.g. "
        "'command(uv run pytest)'. Rules are prefixes — keep them as long as "
        "the narrowest command that should pass."
    ),
)
def grant(yes: bool, rules: tuple[str, ...]) -> None:
    """Grant command rules to headless agy — the handoff set by default.

    Preferred over --dangerously-skip-permissions, which would auto-approve
    every tool call including arbitrary shell commands.
    """
    to_grant = rules or HANDOFF_GRANTS
    click.echo(f"[INFO] Settings file: {SETTINGS_PATH}")
    click.echo("[INFO] Rules to grant:")
    for rule in to_grant:
        click.echo(f"         {rule}")
    click.echo("")
    click.echo("[WARN] Grants apply to ANY headless agy run in any repository you")
    click.echo("[WARN] launch it from, not just the handoff skills.")
    click.echo("")

    if not yes and not click.confirm("Grant these permissions?", default=False):
        click.echo("[INFO] Aborted. No changes made.")
        return

    added = grant_rules(to_grant)
    if added:
        click.echo(f"[INFO] Backup written to: {SETTINGS_PATH}.bak")
        click.echo("[SUCCESS] Added: " + ", ".join(added))
    else:
        click.echo("[INFO] All rules were already present. Nothing changed.")
