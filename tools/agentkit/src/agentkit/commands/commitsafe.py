"""`agentkit commit-safe` — identity whitelist and commit timestamps."""

from __future__ import annotations

import os
import subprocess

import click

from ..commitsafe import (
    checked_identity,
    config_path,
    git_email,
    resolve,
    write_default_config,
)


@click.group("commit-safe")
def commit_safe() -> None:
    """Whitelist the committing identity and control commit timestamps."""


@commit_safe.command()
@click.option("--force", is_flag=True, help="Overwrite an existing config file.")
def init(force: bool) -> None:
    """Write a starter config, seeded with the current git identity."""
    path = config_path()

    if path.is_file() and not force:
        click.echo(f"[INFO] Config already exists at: {path}")
        click.echo(path.read_text(encoding="utf-8"))
        click.echo("[INFO] Re-run with --force to overwrite it.")
        return

    write_default_config(path, git_email() or "user@example.com")
    click.echo(f"[SUCCESS] Wrote {path}")
    click.echo(path.read_text(encoding="utf-8"))
    click.echo("[INFO] Edit it to add more allowed emails or adjust the time range.")


@commit_safe.command()
def verify() -> None:
    """Pre-flight check. Never consumes a timestamp."""
    config, email = checked_identity()
    stamp = resolve(config, persist=False)

    if not stamp.enabled:
        session = "timeline disabled (using system clock)"
    elif stamp.first_of_day:
        session = "1st of the day (random point in range)"
    else:
        session = "subsequent (real elapsed time since the 1st)"

    click.echo("=== commit-safe pre-flight ===")
    click.echo(f"  Config:    {config.path}")
    click.echo(f"  Email:     {email} (allowed)")
    click.echo(f"  Session:   {session}")
    if stamp.enabled:
        click.echo(f"  Range:     {config.start} ~ {config.end} ({config.timezone})")
    click.echo(f"  Next time: {stamp.format()} (preview — not consumed)")
    click.echo("  Status:    passed")


@commit_safe.command()
def stamp() -> None:
    """Print the resolved timestamp for the next commit."""
    config, _ = checked_identity()
    click.echo(resolve(config).format())


@commit_safe.command()
def env() -> None:
    """Print shell exports for the next commit, for `eval`."""
    config, email = checked_identity()
    exports = resolve(config).as_env()
    exports["GIT_COMMIT_SAFE_EMAIL"] = email
    for key, value in exports.items():
        click.echo(f'export {key}="{value}"')


# Dates a caller already resolved and exported for us. A handoff runner stamps
# one unit in the parent and hands it down; resolving again here would consume
# a second stamp and pull the unit off the virtual timeline.
INHERITED_DATE_VARS = ("GIT_AUTHOR_DATE", "GIT_COMMITTER_DATE")


@commit_safe.command()
@click.option(
    "-m",
    "--message",
    "messages",
    multiple=True,
    required=True,
    help="Commit message paragraph, repeatable — same meaning as git's own -m.",
)
@click.option("--amend", is_flag=True, help="Amend the previous commit rather than creating one.")
@click.option(
    "--no-verify",
    "no_verify",
    is_flag=True,
    help="Skip git hooks. Only ever from the repository's hook policy, never on the agent's judgment.",
)
@click.pass_context
def commit(ctx: click.Context, messages: tuple[str, ...], amend: bool, no_verify: bool) -> None:
    """Check the identity, resolve the timestamp, and run `git commit`.

    One command replaces `eval "$(agentkit commit-safe env)" && git commit …`.
    The eval form cost an agent CLI a permission prompt on every commit: an
    allow-list matches a command prefix, and that line starts with a shell
    assignment rather than a permitted command. It also dropped this CLI's exit
    code unless the caller captured the exports first, so a whitelist rejection
    could fall through to the commit.

    The git argv is built here from named options. This never runs a command the
    caller names, so the one `command(agentkit)` grant that lets an agent reach
    this cannot also become a way to run arbitrary shell.
    """
    config, _ = checked_identity()

    inherited = [name for name in INHERITED_DATE_VARS if name in os.environ]
    if inherited:
        exports: dict[str, str] = {}
        click.echo(f"[INFO] Date: {os.environ[inherited[0]]} (inherited from {', '.join(inherited)})")
    else:
        stamp = resolve(config)
        exports = stamp.as_env()
        click.echo(f"[INFO] Date: {stamp.format()}")

    argv = ["git", "commit"]
    if amend:
        argv.append("--amend")
    if no_verify:
        argv.append("--no-verify")
    for message in messages:
        argv += ["-m", message]

    # -m is required, so git never falls through to an editor and hangs a
    # headless run. Output is inherited: a failing hook has to reach the caller
    # verbatim, not compressed into an advisory.
    result = subprocess.run(argv, env={**os.environ, **exports})
    ctx.exit(result.returncode)
