"""`agentkit commit-safe` — identity whitelist and commit timestamps."""

from __future__ import annotations

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

    session = (
        "1st of the day (random point in range)"
        if stamp.first_of_day
        else "subsequent (real elapsed time since the 1st)"
    )

    click.echo("=== commit-safe pre-flight ===")
    click.echo(f"  Config:    {config.path}")
    click.echo(f"  Email:     {email} (whitelisted)")
    click.echo(f"  Session:   {session}")
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
