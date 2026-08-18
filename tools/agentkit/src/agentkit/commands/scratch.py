"""`agentkit scratch` — per-repo scratch space for agent working files."""

from __future__ import annotations

import click

from .. import gitutil
from ..scratch import (
    DEFAULT_CLEAN_OLDER_THAN,
    DEFAULT_ROOT,
    MECHANISM_GITIGNORE,
    ScratchConfig,
    clean_scratch,
    ensure_ignored,
    load_scratch_config,
    parse_duration,
    resolve_scratch,
    save_scratch_config,
    validate_relative_dir,
)


@click.group()
def scratch() -> None:
    """Per-repo scratch space for agent working files."""


@scratch.command("path")
@click.argument("subdir", required=False)
def path_cmd(subdir: str | None) -> None:
    """Print the absolute scratch directory, creating it if needed.

    First use in a repository adopts `.agents/tmp` and keeps it out of
    `git status` via `.git/info/exclude`. Outside a git repository the
    directory falls back under `~/.agents/tmp/`. Only the path goes to stdout.
    """
    resolution = resolve_scratch(subdir=subdir)
    if resolution.onboarded:
        click.echo(
            f"[SETUP]  scratch root initialized at {resolution.root} ({resolution.mechanism}); "
            "run `agentkit scratch onboard --force --root <dir>` to change it.",
            err=True,
        )
    click.echo(str(resolution.path))


@scratch.command("onboard")
@click.option("--root", "root_option", default=None, help=f"Repo-relative scratch root. [default: {DEFAULT_ROOT}]")
@click.option(
    "--shared",
    is_flag=True,
    help="Ignore via the committed .gitignore instead of the repo-local .git/info/exclude.",
)
@click.option("--force", is_flag=True, help="Replace an existing configuration.")
def onboard(root_option: str | None, shared: bool, force: bool) -> None:
    """Choose where this repository's scratch space lives.

    Optional: `agentkit scratch path` self-onboards with the default. Use this
    to pick a different root or to share the ignore entry with the team.
    """
    repo_root = gitutil.repo_root()
    existing = load_scratch_config(cwd=repo_root)
    if existing is not None and not force:
        click.echo(f"Already configured: root={existing.root} mechanism={existing.mechanism}")
        click.echo("Pass --force to change it.")
        return

    root_rel = validate_relative_dir(root_option or DEFAULT_ROOT, what="scratch root")
    mechanism = ensure_ignored(root_rel, repo_root, shared=shared)
    config = ScratchConfig(root=root_rel, mechanism=mechanism)
    config_path = save_scratch_config(config, cwd=repo_root)
    (repo_root / root_rel).mkdir(parents=True, exist_ok=True)

    click.echo(f"Scratch root: {repo_root / root_rel}")
    click.echo(f"Ignored via:  {mechanism}")
    click.echo(f"Config:       {config_path}")
    if mechanism == MECHANISM_GITIGNORE:
        click.echo("Note: .gitignore was modified — that change is part of the tree and needs a commit.")


@scratch.command("clean")
@click.option(
    "--older-than",
    "older_than",
    default=DEFAULT_CLEAN_OLDER_THAN,
    show_default=True,
    help="Remove files older than this duration (e.g. 30d, 24h, 60m, 300s).",
)
@click.option(
    "--yes",
    "yes",
    is_flag=True,
    help="Actually delete files. Defaults to a dry run.",
)
def clean(older_than: str, yes: bool) -> None:
    """Remove old files from this repository's scratch space.

    Dry-run by default: lists files that would be removed without touching them.
    Pass --yes to delete.
    """
    max_age_seconds = parse_duration(older_than)
    resolution = resolve_scratch()
    affected = clean_scratch(max_age_seconds, delete=yes)

    for path in affected:
        click.echo(str(path.relative_to(resolution.root)))

    count = len(affected)
    unit = "file" if count == 1 else "files"
    if yes:
        click.echo(f"Removed {count} {unit}.")
    else:
        click.echo(f"Would remove {count} {unit} (dry run; pass --yes to delete).")
